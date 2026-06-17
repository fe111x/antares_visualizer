from __future__ import annotations

from typing import Any

import logging

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, State, ctx, html, no_update as dash_no_update

try:
    import polars as pl
except ImportError:  # pragma: no cover
    pl = None

from .config import (
    FILE_SOURCE_COLUMN,
    LOADING_BAR_HIDDEN_STYLE,
    LOADING_BAR_VISIBLE_STYLE,
    MAX_OPTION_VALUES,
    MAX_RAW_POINTS,
    RUN_KEY_COLUMN,
    READINESS_STAGE_ACTIVE,
    READINESS_STAGE_DONE,
    READINESS_STAGE_PENDING,
    TECHNOLOGY_SOURCE_COLUMN,
    UNIT_NAME_COLUMN,
)
from .data_access import (
    _sorted_options,
    build_file_options,
    build_run_options,
    detect_time_columns,
    file_key_to_run_key,
    get_selector_hierarchy,
    get_trace_selector_leaf,
    get_unit_options_for_context,
    infer_schema_profile,
    load_selected_tables,
    load_selected_tables_pemmdb_type_aggregated,
    load_trace_selector_index,
    normalize_file_keys,
    parse_datetime,
    property_requires_technology,
    read_datetime_bounds,
)
from .plotting import empty_figure
from .prefetch import get_load_progress, is_prefetch_in_progress, start_prefetch

TIME_RESOLUTION_OPTIONS = [
    {"label": "Native (per timestamp)", "value": "native"},
    {"label": "Hourly buckets", "value": "hour"},
    {"label": "Daily buckets", "value": "day"},
    {"label": "Weekly buckets", "value": "week"},
    {"label": "Monthly buckets", "value": "month"},
]


def _default_readiness() -> dict[str, Any]:
    return {
        "phase": "idle",
        "detail": "Ready.",
        "files": 0,
        "filters_ready": False,
        "plot_ready": False,
    }


def render_readiness_banner(readiness: dict[str, Any] | None):
    state = readiness or _default_readiness()
    filters_ready = bool(state.get("filters_ready"))
    plot_ready = bool(state.get("plot_ready"))
    phase = str(state.get("phase", "idle"))
    detail = str(state.get("detail", ""))

    def stage_style(done: bool, active: bool) -> dict[str, str]:
        if done:
            return READINESS_STAGE_DONE
        if active:
            return READINESS_STAGE_ACTIVE
        return READINESS_STAGE_PENDING

    files_label = f"{state.get('files', 0)} file(s)" if state.get("files") else "No files"
    return html.Div(
        [
            html.Div(
                [
                    html.Span("1. Runs", style=stage_style(True, phase == "loading")),
                    html.Span(" → ", style=READINESS_STAGE_PENDING),
                    html.Span(
                        "2. Trace builder",
                        style=stage_style(filters_ready, phase in {"loading", "filters_ready"}),
                    ),
                    html.Span(" → ", style=READINESS_STAGE_PENDING),
                    html.Span(
                        "3. Visualization",
                        style=stage_style(plot_ready, phase in {"filters_ready", "ready"} and not plot_ready),
                    ),
                ],
                style={"fontWeight": 600, "marginBottom": "4px"},
            ),
            html.Div(detail or files_label, style={"fontSize": "0.84rem", "color": "#475569"}),
        ]
    )


def prepare_loaded_files(loaded_file_keys: list[str] | None) -> dict[str, Any]:
    selected_file_keys = normalize_file_keys(loaded_file_keys)
    if not selected_file_keys:
        return _default_readiness()

    try:
        load_trace_selector_index(selected_file_keys)
        get_selector_hierarchy(selected_file_keys)
    except Exception as exc:
        logger.exception("Failed to prepare filter index")
        return {
            "phase": "error",
            "detail": f"Could not prepare filters: {exc}",
            "files": len(selected_file_keys),
            "filters_ready": False,
            "plot_ready": False,
        }

    try:
        start_prefetch(selected_file_keys, warm_plot_cache=True)
    except Exception:
        logger.exception("Could not start plot prefetch")

    return {
        "phase": "filters_ready",
        "detail": f"{len(selected_file_keys)} file(s) loaded. Trace builder ready — warming plot cache in background.",
        "files": len(selected_file_keys),
        "filters_ready": True,
        "plot_ready": False,
    }


def sync_readiness_from_prefetch(_n_intervals: int, readiness: dict[str, Any] | None) -> dict[str, Any]:
    state = dict(readiness or _default_readiness())
    progress = get_load_progress()
    state["files"] = progress.get("files", state.get("files", 0))
    if progress.get("filters_ready"):
        state["filters_ready"] = True
    if progress.get("plot_ready"):
        state["plot_ready"] = True
        state["phase"] = "ready"
        state["detail"] = progress.get("detail", "Dashboard ready.")
    elif progress.get("phase") == "filters_ready":
        state["phase"] = "filters_ready"
        state["detail"] = progress.get("detail", state.get("detail", ""))
    elif progress.get("phase") == "loading" and not state.get("filters_ready"):
        state["phase"] = "loading"
        state["detail"] = progress.get("detail", state.get("detail", ""))
    elif progress.get("phase") == "error":
        state["phase"] = "error"
        state["detail"] = progress.get("detail", state.get("detail", ""))
    return state


logger = logging.getLogger(__name__)

_LOAD_RUNNING = [
    (Output("loading-indicator", "style"), LOADING_BAR_VISIBLE_STYLE, LOADING_BAR_HIDDEN_STYLE),
    (Output("load-data", "disabled"), True, False),
]

_VISUALIZE_RUNNING = [
    (Output("loading-indicator", "style"), LOADING_BAR_VISIBLE_STYLE, LOADING_BAR_HIDDEN_STYLE),
    (Output("visualize-data", "disabled"), True, False),
]


def _retain_single_selection(current_value: Any, valid_values: list[Any], preferred_value: Any = None) -> Any:
    if current_value in valid_values:
        return current_value
    current_text = str(current_value)
    for value in valid_values:
        if str(value) == current_text:
            return value
    if preferred_value in valid_values:
        return preferred_value
    preferred_text = str(preferred_value)
    for value in valid_values:
        if str(value) == preferred_text:
            return value
    return valid_values[0] if valid_values else None


def _trace_columns(df: pd.DataFrame) -> dict[str, str | None]:
    # Prefer file-level selector to keep scenario cardinality low and stable.
    if FILE_SOURCE_COLUMN in df.columns and not df[FILE_SOURCE_COLUMN].dropna().empty:
        scenario_col = FILE_SOURCE_COLUMN
    else:
        scenario_col = None
        for candidate in ("Scenario", "Sample"):
            if candidate not in df.columns:
                continue
            if df[candidate].dropna().empty:
                continue
            scenario_col = candidate
            break

        # Fallback when Scenario/Sample are empty.
        if scenario_col is None and FILE_SOURCE_COLUMN in df.columns:
            scenario_col = FILE_SOURCE_COLUMN
    return {
        "scenario": scenario_col,
        "market_area": "BZ" if "BZ" in df.columns else None,
        "ws": "WS" if "WS" in df.columns else None,
        "property": "Property" if "Property" in df.columns else None,
        "technology": "PEMMDB_TECHNOLOGY" if "PEMMDB_TECHNOLOGY" in df.columns else None,
        "unit": UNIT_NAME_COLUMN if UNIT_NAME_COLUMN in df.columns else None,
    }


def build_value_options(series: pd.Series) -> list[dict[str, object]]:
    """Create dropdown options from a pandas Series.

    Returns a list of dicts with keys `label` and `value`. Handles numpy scalars
    and other array-backed types by converting to native Python types where
    possible and skipping NaN/None values.
    """
    if series is None:
        return []
    try:
        # dropna then get unique values
        vals = pd.Series(series).dropna().unique()
    except Exception:
        try:
            vals = pd.Series(list(series)).dropna().unique()
        except Exception:
            return []

    def to_py(v):
        # numpy scalar
        try:
            if hasattr(v, "item"):
                return v.item()
        except Exception:
            pass
        return v

    # convert and build options
    options = []
    for v in vals:
        pv = to_py(v)
        options.append({"label": str(pv), "value": pv})

    # sort deterministically by label
    try:
        options.sort(key=lambda o: o["label"])
    except Exception:
        pass

    if len(options) > MAX_OPTION_VALUES:
        options = options[:MAX_OPTION_VALUES]

    return options


def _build_trace_label(trace_item: dict[str, Any]) -> str:
    run_label = trace_item.get("run") or trace_item.get("scenario") or "?"
    base = f"{run_label} | WS {trace_item.get('ws')} | {trace_item.get('market_area')}"
    technology = trace_item.get("technology")
    if trace_item.get("is_technology") and technology is None:
        label = f"{base} | {trace_item.get('property')}"
    else:
        property_value = trace_item.get("property")
        if property_value is not None and technology is not None:
            label = f"{base} | {property_value} | {technology}"
        elif property_value is not None:
            label = f"{base} | {property_value}"
        else:
            label = base
    unit_name = trace_item.get("unit_name")
    if unit_name:
        label = f"{label} | {unit_name}"
    aggregation = trace_item.get("aggregation")
    time_resolution = trace_item.get("time_resolution") or "native"
    if aggregation and aggregation != "none":
        label = f"{label} [{aggregation}/{time_resolution}]"
    elif aggregation == "none":
        label = f"{label} [raw]"
    return label


def refresh_run_options(_n_clicks: int, current_run: str | list[str] | None) -> tuple[list[dict[str, str]], list[str]]:
    # If user requested a refresh, clear file discovery cache so new files appear.
    try:
        if (_n_clicks or 0) > 0:
            from .settings import invalidate_path_caches

            try:
                invalidate_path_caches()
            except Exception:
                pass
            try:
                from .data_access import discover_input_files

                discover_input_files.cache_clear()
            except Exception:
                pass
    except Exception:
        pass

    options = build_run_options()
    if not options:
        return [], []
    option_values = [option["value"] for option in options]
    selected_runs = set(normalize_file_keys(current_run))
    next_run = [value for value in option_values if value in selected_runs]
    if not next_run:
        next_run = option_values
    return options, next_run


def sync_files_for_run(
    run_key: str | list[str] | None,
    _n_clicks: int,
    current_value: str | list[str] | None,
) -> tuple[list[dict[str, str]], list[str], str]:
    if not run_key:
        return [], [], "Select one or more runs, then click Load Data."

    options = build_file_options(run_key)
    if not options:
        return [], [], "No files found for the selected run."

    option_values = [option["value"] for option in options]
    selected_values = set(normalize_file_keys(current_value))
    next_values = [value for value in option_values if value in selected_values]
    if not next_values:
        next_values = option_values

    run_values = normalize_file_keys(run_key)
    run_count = len(run_values)
    if run_count == 1:
        run_label = run_values[0]
        status = f"{len(next_values)} file(s) in '{run_label}' — click Load Data."
    elif run_count > 1:
        status = f"{len(next_values)} file(s) across {run_count} runs — click Load Data."
    else:
        status = f"{len(next_values)} file(s) — click Load Data."
    return options, next_values, status


def update_controls(
    _n_clicks: int,
    file_key: str | list[str] | None,
    run_key: str | list[str] | None,
    current_time_column: str | None,
    current_value_column: str | None,
):
    empty_fig = empty_figure("Loading data automatically."), "Initializing..."

    selected_file_keys = normalize_file_keys(file_key)
    if not selected_file_keys:
        selected_file_keys = [opt["value"] for opt in build_file_options(run_key)]
    if not selected_file_keys:
        return ([], None, [], None, "Select one or more runs, then click Load Data.", [], [], empty_fig[0], empty_fig[1], [], [])

    try:
        profile = infer_schema_profile(selected_file_keys[0])
    except Exception as exc:  # pragma: no cover
        return ([], None, [], None, f"Load error: {exc}", [], [], empty_fig[0], empty_fig[1], [], [])

    time_columns = profile.get("time_columns") or []
    numeric_columns = profile.get("numeric_columns") or []
    if not time_columns:
        time_columns = [col for col in profile.get("columns", []) if col in {"Datetime"}]
    if not numeric_columns:
        numeric_columns = [col for col in profile.get("columns", []) if col == "Value"]

    time_options = [{"label": col, "value": col} for col in time_columns]
    value_options = [{"label": col, "value": col} for col in numeric_columns]
    time_default = _retain_single_selection(current_time_column, time_columns, preferred_value="Datetime")
    value_default = _retain_single_selection(current_value_column, numeric_columns, preferred_value="Value")

    status = f"{len(selected_file_keys)} file(s) selected. Preparing filters..."
    loaded_dropdown_options = [{"label": k, "value": k} for k in selected_file_keys]
    return (
        time_options,
        time_default,
        value_options,
        value_default,
        status,
        selected_file_keys,
        [],
        empty_figure("Preparing trace builder..."),
        "Waiting for filter index...",
        loaded_dropdown_options,
        selected_file_keys,
    )


def update_trace_selector_options(
    _load_n_clicks: int | None,
    loaded_file_keys: list[str] | None,
    readiness: dict[str, Any] | None,
    aggregation_mode_store: dict[str, Any] | None,
    selected_top_run: Any,
    selected_run: Any,
    selected_ws: Any,
    selected_market: Any,
    selected_property: Any,
    selected_technology: Any,
    selected_unit: Any,
):
    empty = ([], None, [], None, [], None, [], None, [], None, [], None, True, True, True, {"display": "none"})
    selected_file_keys = normalize_file_keys(loaded_file_keys)
    if not selected_file_keys:
        return empty

    unit_detail_mode = bool((aggregation_mode_store or {}).get("unit_detail_mode", False))

    try:
        hierarchy = get_selector_hierarchy(selected_file_keys)
    except Exception as exc:
        logger.exception("Failed to build trace selector hierarchy")
        detail = (readiness or {}).get("detail") or str(exc)
        if not bool((readiness or {}).get("filters_ready")):
            return empty
        return empty

    run_options = hierarchy.get("runs", [])
    if not run_options:
        return empty

    tree = hierarchy.get("tree", {})
    run_values = [item["value"] for item in run_options]
    run_value = _retain_single_selection(selected_run, run_values)
    if run_value is None:
        top_runs = normalize_file_keys(selected_top_run)
        for candidate in top_runs:
            if candidate in run_values:
                run_value = candidate
                break
    if run_value is None and run_values:
        run_value = run_values[0]

    ws_map = tree.get(run_value, {})
    ws_options = _sorted_options(set(ws_map.keys()))
    ws_values = [item["value"] for item in ws_options]
    ws_value = _retain_single_selection(selected_ws, ws_values)

    market_map = ws_map.get(ws_value, {})
    market_options = _sorted_options(set(market_map.keys()))
    market_values = [item["value"] for item in market_options]
    market_value = _retain_single_selection(selected_market, market_values)

    leaf = get_trace_selector_leaf(hierarchy, run_value, ws_value, market_value)
    standalone_properties = leaf.get("standalone_properties", set())
    property_technologies = leaf.get("property_technologies", {})
    all_properties = standalone_properties | set(property_technologies.keys())
    property_options = build_value_options(pd.Series(list(all_properties)))
    property_values = [item["value"] for item in property_options]
    property_value = _retain_single_selection(selected_property, property_values) if property_values else None

    requires_technology = property_requires_technology(leaf, property_value)
    if requires_technology:
        technology_options = build_value_options(pd.Series(list(property_technologies[property_value])))
        technology_values = [item["value"] for item in technology_options]
        technology_value = _retain_single_selection(selected_technology, technology_values) if technology_options else None
    else:
        technology_options = []
        technology_value = None

    triggered = None
    try:
        triggered = ctx.triggered_id
    except Exception:
        pass
    if triggered == "property-select" and not requires_technology:
        technology_value = None

    property_disabled = not property_options
    technology_disabled = not requires_technology or not technology_options

    unit_container_style = {"display": "block"} if unit_detail_mode else {"display": "none"}
    if unit_detail_mode and property_value is not None:
        unit_options = get_unit_options_for_context(
            selected_file_keys,
            run_value,
            ws_value,
            market_value,
            property_value,
            technology_value,
        )
        unit_values = [item["value"] for item in unit_options]
        unit_value = _retain_single_selection(selected_unit, unit_values) if unit_options else None
        unit_disabled = not unit_options
    else:
        unit_options = []
        unit_value = None
        unit_disabled = True

    return (
        run_options,
        run_value,
        ws_options,
        ws_value,
        market_options,
        market_value,
        property_options,
        property_value,
        technology_options,
        technology_value,
        unit_options,
        unit_value,
        property_disabled,
        technology_disabled,
        unit_disabled,
        unit_container_style,
    )


def add_remove_trace(
    _add_clicks: int,
    _remove_clicks: int,
    traces: list[dict[str, Any]] | None,
    loaded_file_keys: list[str] | None,
    selected_scenario: Any,
    selected_market: Any,
    selected_ws: Any,
    selected_property: Any,
    selected_technology: Any,
    selected_unit: Any,
    selected_aggregation: str | None,
    selected_time_resolution: str | None,
    aggregation_mode_store: dict[str, Any] | None,
    remove_trace_labels: Any,
):
    traces = list(traces or [])

    triggered = None
    try:
        triggered = ctx.triggered_id
    except Exception:
        pass

    selected_run = selected_scenario
    unit_detail_mode = bool((aggregation_mode_store or {}).get("unit_detail_mode", False))

    if triggered == "add-trace":
        if None in (selected_run, selected_market, selected_ws) or selected_property is None:
            return traces, "Trace not added: select run, WS, market area, and property."

        hierarchy = get_selector_hierarchy(loaded_file_keys)
        leaf = get_trace_selector_leaf(hierarchy, selected_run, selected_ws, selected_market)
        requires_technology = property_requires_technology(leaf, selected_property)

        if requires_technology and selected_technology is None:
            return traces, f"Trace not added: '{selected_property}' requires a PEMMDB technology."
        if not requires_technology and selected_technology is not None:
            return traces, f"Trace not added: '{selected_property}' has no PEMMDB technology."
        if unit_detail_mode and not requires_technology:
            return traces, "Trace not added: unit-level detail requires a generator property with PEMMDB technology."
        if unit_detail_mode and selected_unit is None:
            return traces, "Trace not added: select a unit for unit-level detail."
        if not unit_detail_mode and selected_unit is not None:
            return traces, "Trace not added: enable unit-level detail above to plot a single unit."

        aggregation = selected_aggregation or "sum"
        time_resolution = selected_time_resolution or "native"
        if aggregation == "none":
            time_resolution = "native"

        candidate = {
            "run": selected_run,
            "market_area": selected_market,
            "ws": selected_ws,
            "property": selected_property,
            "technology": selected_technology if requires_technology else None,
            "unit_name": selected_unit if unit_detail_mode else None,
            "is_technology": False,
            "aggregation": aggregation,
            "time_resolution": time_resolution,
        }
        candidate_label = _build_trace_label(candidate)
        if any(_build_trace_label(item) == candidate_label for item in traces):
            return traces, f"Trace already exists: {candidate_label}"

        traces.append(candidate)
        return traces, f"Trace added: {candidate_label}"

    if triggered == "remove-trace":
        labels_to_remove = remove_trace_labels
        if isinstance(labels_to_remove, str):
            labels_to_remove = [labels_to_remove]
        labels_to_remove = list(labels_to_remove or [])
        if not labels_to_remove:
            return traces, "Select one or more traces to remove first."
        labels_set = set(labels_to_remove)
        remaining = [item for item in traces if _build_trace_label(item) not in labels_set]
        removed_count = len(traces) - len(remaining)
        return remaining, f"Removed {removed_count} trace(s)."

    return traces, ""


def render_trace_list(traces: list[dict[str, Any]] | None):
    traces = list(traces or [])
    if not traces:
        return html.Div("No traces added yet."), [], None

    labels = [_build_trace_label(item) for item in traces]
    options = [{"label": label, "value": label} for label in labels]
    return html.Ul([html.Li(label) for label in labels], style={"margin": "0", "paddingLeft": "18px"}), options, None


def describe_file_selection(
    file_key: str | list[str] | None,
    run_key: str | list[str] | None,
    loaded_file_keys: list[str] | None,
) -> str:
    selected_file_keys = normalize_file_keys(file_key)
    if not selected_file_keys:
        return "No files selected."

    run_values = normalize_file_keys(run_key)
    run_count = len(run_values)
    loaded_keys = normalize_file_keys(loaded_file_keys)
    if selected_file_keys == loaded_keys:
        if run_count == 1:
            return f"{len(selected_file_keys)} file(s) from '{run_values[0]}' loaded."
        if run_count > 1:
            return f"{len(selected_file_keys)} file(s) from {run_count} runs loaded."
        return f"{len(selected_file_keys)} file(s) loaded."
    if run_count == 1:
        return f"{len(selected_file_keys)} file(s) from '{run_values[0]}' — updating..."
    if run_count > 1:
        return f"{len(selected_file_keys)} file(s) from {run_count} runs — updating..."
    return f"{len(selected_file_keys)} file(s) — updating..."


def set_load_status(_n_clicks: int, file_key: str | list[str] | None, run_key: str | list[str] | None) -> str:
    selected_file_keys = normalize_file_keys(file_key)
    if not selected_file_keys:
        return "No files selected."
    run_values = normalize_file_keys(run_key)
    run_count = len(run_values)
    if run_count == 1:
        return f"Loading {len(selected_file_keys)} file(s) from '{run_values[0]}' ..."
    if run_count > 1:
        return f"Loading {len(selected_file_keys)} file(s) from {run_count} runs ..."
    return f"Loading {len(selected_file_keys)} file(s) ..."


def set_visualize_status(_n_clicks: int, trace_store: list[dict[str, Any]] | None) -> str:
    traces = list(trace_store or [])
    if not traces:
        return "No traces defined. Use Add trace first."
    return f"Updating visualization ({len(traces)} trace(s)) ..."


def toggle_unit_detail_mode(
    n_clicks: int,
    store: dict[str, Any] | None,
    loaded_file_keys: list[str] | None,
) -> tuple[dict[str, bool], str]:
    current = store or {"unit_detail_mode": False, "pemmdb_type_active": True}
    if not n_clicks:
        unit_mode = bool(current.get("unit_detail_mode", False))
    else:
        unit_mode = not bool(current.get("unit_detail_mode", False))
    new_store = {"unit_detail_mode": unit_mode, "pemmdb_type_active": not unit_mode}
    label = "Unit-level detail: On" if unit_mode else "Unit-level detail: Off"
    try:
        keys = normalize_file_keys(loaded_file_keys)
        if keys:
            start_prefetch(keys, warm_plot_cache=True, unit_detail_mode=unit_mode)
    except Exception:
        pass
    return new_store, label


def update_date_range(
    file_key: str | list[str] | None,
    time_column: str | None,
    reset_clicks: int | None,
):
    selected_file_keys = normalize_file_keys(file_key)
    if not selected_file_keys or not time_column:
        return None, None, None, None

    min_date, max_date = read_datetime_bounds(selected_file_keys, time_column)
    if not min_date or not max_date:
        return None, None, None, None

    triggered_id = None
    try:
        triggered_id = ctx.triggered_id
    except Exception:
        pass

    if triggered_id == "reset-date-range" and (reset_clicks or 0) > 0:
        return min_date, max_date, None, None
    return min_date, max_date, min_date, max_date


def _filter_trace_frame(
    df: pd.DataFrame,
    trace: dict[str, Any],
    trace_cols: dict[str, str | None],
    time_column: str,
    value_column: str,
    start_date: str | None,
    end_date: str | None,
) -> pd.DataFrame:
    frame = df
    run_key = trace.get("run")
    if run_key and RUN_KEY_COLUMN in frame.columns:
        frame = frame[frame[RUN_KEY_COLUMN].astype(str) == str(run_key)]
        logger.debug("_filter_trace_frame: run filter -> %d rows", len(frame))
    elif trace_cols["scenario"]:
        trace_scenario_val = trace.get("scenario")
        # If the stored scenario looks like a file key (path or parquet filename), prefer
        # to filter by the file-source column which holds the file key.
        if isinstance(trace_scenario_val, str) and (
            trace_scenario_val.endswith('.parquet') or '/' in trace_scenario_val or '\\' in trace_scenario_val
        ) and FILE_SOURCE_COLUMN in frame.columns:
            frame = frame[frame[FILE_SOURCE_COLUMN].astype(str) == trace_scenario_val]
            logger.debug("_filter_trace_frame: source scenario filter -> %d rows", len(frame))
        else:
            frame = frame[frame[trace_cols["scenario"]].astype(str) == str(trace_scenario_val)]
            logger.debug("_filter_trace_frame: scenario filter -> %d rows", len(frame))
    if trace_cols["market_area"]:
        frame = frame[frame[trace_cols["market_area"]].astype(str) == str(trace["market_area"])]
        logger.debug("_filter_trace_frame: market_area filter -> %d rows", len(frame))
    if trace_cols["ws"]:
        # WS is numeric (float), but trace["ws"] may be int or float
        # Convert to numeric for comparison to avoid "4.0" != "4" string issue
        try:
            ws_numeric = pd.to_numeric(frame[trace_cols["ws"]], errors="coerce")
            trace_ws_numeric = float(trace["ws"])
            frame = frame[ws_numeric == trace_ws_numeric]
            logger.debug("_filter_trace_frame: ws filter -> %d rows", len(frame))
        except (ValueError, TypeError) as e:
            # If numeric conversion fails, fall back to string comparison
            logger.debug("_filter_trace_frame: ws numeric conversion failed (%s), fallback to string", e)
            frame = frame[frame[trace_cols["ws"]].astype(str) == str(trace["ws"])]
    if trace.get("is_technology") and trace_cols.get("technology") and trace_cols["technology"] in frame.columns:
        frame = frame[frame[trace_cols["technology"]].astype(str) == str(trace["property"])]
        logger.debug("_filter_trace_frame: technology filter -> %d rows", len(frame))
    else:
        if trace_cols.get("property") and trace_cols["property"] in frame.columns and trace.get("property") is not None:
            frame = frame[frame[trace_cols["property"]].astype(str) == str(trace["property"])]
            logger.debug("_filter_trace_frame: property filter -> %d rows", len(frame))
        technology_value = trace.get("technology")
        if (
            technology_value is not None
            and trace_cols.get("technology")
            and trace_cols["technology"] in frame.columns
        ):
            frame = frame[frame[trace_cols["technology"]].astype(str) == str(technology_value)]
            logger.debug("_filter_trace_frame: technology filter -> %d rows", len(frame))

    unit_name = trace.get("unit_name")
    unit_col = trace_cols.get("unit")
    if unit_name is not None and unit_col and unit_col in frame.columns:
        frame = frame[frame[unit_col].astype(str) == str(unit_name)]
        logger.debug("_filter_trace_frame: unit filter -> %d rows", len(frame))

    if frame.empty:
        return frame

    ts = parse_datetime(frame[time_column])
    valid = ts.notna()
    if not valid.any():
        return frame.iloc[0:0]
    frame = frame.loc[valid].copy()
    frame["__time"] = ts.loc[valid]

    start_ts = pd.to_datetime(start_date, errors="coerce") if start_date else pd.NaT
    end_ts = pd.to_datetime(end_date, errors="coerce") if end_date else pd.NaT
    if pd.notna(start_ts):
        frame = frame[frame["__time"] >= start_ts]
    if pd.notna(end_ts):
        end_inclusive = end_ts + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
        frame = frame[frame["__time"] <= end_inclusive]

    if frame.empty:
        return frame

    if not pd.api.types.is_numeric_dtype(frame[value_column]):
        numeric = pd.to_numeric(frame[value_column], errors="coerce")
        valid_num = numeric.notna()
        frame = frame.loc[valid_num].copy()
        frame[value_column] = numeric.loc[valid_num]

    return frame


def _period_bounds(period_start: pd.Timestamp, time_resolution: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    if time_resolution == "hour":
        end = period_start + pd.Timedelta(hours=1) - pd.Timedelta(microseconds=1)
    elif time_resolution == "day":
        end = period_start + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
    elif time_resolution == "week":
        end = period_start + pd.Timedelta(days=7) - pd.Timedelta(microseconds=1)
    elif time_resolution == "month":
        end = (period_start + pd.offsets.MonthBegin(1)) - pd.Timedelta(microseconds=1)
    else:
        end = period_start
    return period_start, end


def _bucket_series(frame: pd.DataFrame, time_resolution: str) -> pd.Series:
    ts = frame["__time"]
    if time_resolution == "hour":
        return ts.dt.floor("h")
    if time_resolution == "day":
        return ts.dt.floor("D")
    if time_resolution == "week":
        return ts.dt.to_period("W-MON").dt.start_time
    if time_resolution == "month":
        return ts.dt.to_period("M").dt.start_time
    return ts


def _aggregate_trace(
    frame: pd.DataFrame,
    value_column: str,
    aggregation: str,
    time_resolution: str = "native",
) -> pd.DataFrame:
    if aggregation == "none":
        return frame[["__time", value_column]].copy().sort_values("__time")

    agg_func = aggregation if aggregation in {"sum", "mean", "min", "max"} else "sum"
    if time_resolution in (None, "native", "raw"):
        return (
            frame.groupby("__time", observed=True, dropna=False, sort=False)[value_column]
            .agg(agg_func)
            .reset_index()
            .sort_values("__time")
        )

    bucketed = frame.copy()
    bucketed["__period"] = _bucket_series(bucketed, time_resolution)
    grouped = (
        bucketed.groupby("__period", observed=True, dropna=False, sort=True)[value_column]
        .agg(agg_func)
        .reset_index()
        .rename(columns={"__period": "__time"})
    )
    if grouped.empty:
        return grouped

    step_times: list[pd.Timestamp] = []
    step_values: list[Any] = []
    for _, row in grouped.iterrows():
        period_start = pd.Timestamp(row["__time"])
        _, period_end = _period_bounds(period_start, time_resolution)
        value = row[value_column]
        step_times.extend([period_start, period_end])
        step_values.extend([value, value])

    return pd.DataFrame({"__time": step_times, value_column: step_values})


def update_timeseries(
    _visualize_clicks: int,
    plot_mode: str,
    file_key: str | list[str] | None,
    time_column: str | None,
    value_column: str | None,
    start_date: str | None,
    end_date: str | None,
    trace_store: list[dict[str, Any]] | None,
    aggregation_mode_store: dict | None,
):
    traces = list(trace_store or [])
    selected_file_keys = normalize_file_keys(file_key)
    if not selected_file_keys or not time_column or not value_column:
        return empty_figure("Load data and select time/value columns."), ""
    if not traces:
        return empty_figure("Add at least one trace."), ""

    pemmdb_type_active = (aggregation_mode_store or {}).get("pemmdb_type_active", True)
    unit_detail_mode = (aggregation_mode_store or {}).get("unit_detail_mode", False)

    trace_runs = {trace.get("run") for trace in traces if trace.get("run")}
    if trace_runs:
        effective_file_keys = sorted(
            {key for key in selected_file_keys if any(file_key_to_run_key(key) == str(run) for run in trace_runs)}
        )
    else:
        trace_file_keys = [
            trace.get("scenario")
            for trace in traces
            if isinstance(trace.get("scenario"), str) and trace.get("scenario") in set(selected_file_keys)
        ]
        effective_file_keys = sorted(set(trace_file_keys)) if trace_file_keys else selected_file_keys

    try:
        plot_columns = tuple(
            dict.fromkeys(
                [
                    time_column,
                    value_column,
                    "BZ",
                    "WS",
                    "Property",
                    TECHNOLOGY_SOURCE_COLUMN,
                    UNIT_NAME_COLUMN,
                    RUN_KEY_COLUMN,
                    FILE_SOURCE_COLUMN,
                    "Sample",
                ]
            )
        )
        if unit_detail_mode or pemmdb_type_active is False:
            df, _ = load_selected_tables(effective_file_keys, columns=plot_columns)
        else:
            df, _ = load_selected_tables_pemmdb_type_aggregated(effective_file_keys)
    except Exception as exc:  # pragma: no cover
        return empty_figure("Could not load data."), str(exc)

    if time_column not in df.columns or value_column not in df.columns:
        return empty_figure("Selected columns are not available."), ""

    trace_cols = _trace_columns(df)
    if not (trace_cols.get("market_area") and trace_cols.get("ws")):
        return empty_figure("Trace builder requires market area (BZ) and WS."), ""

    figure = go.Figure()
    missing_labels: list[str] = []
    total_points = 0

    for trace in traces:
        frame = _filter_trace_frame(df, trace, trace_cols, time_column, value_column, start_date, end_date)
        if frame.empty:
            missing_labels.append(_build_trace_label(trace))
            continue

        trace_aggregation = str(trace.get("aggregation") or "sum")
        trace_resolution = str(trace.get("time_resolution") or "native")
        if trace_aggregation == "none" and len(frame) > MAX_RAW_POINTS:
            return empty_figure(f"Trace '{_build_trace_label(trace)}' is too large for raw data. Use aggregation."), ""

        agg_df = _aggregate_trace(frame, value_column, trace_aggregation, trace_resolution)
        if agg_df.empty:
            missing_labels.append(_build_trace_label(trace))
            continue

        label = _build_trace_label(trace)
        total_points += len(agg_df)
        use_step_shape = (
            plot_mode in {"line", "stacked_area"}
            and trace_aggregation != "none"
            and trace_resolution not in {"native", "raw"}
        )
        line_shape = "hv" if use_step_shape else None

        if plot_mode == "duration_curve":
            sorted_values = agg_df[value_column].sort_values(ascending=False).reset_index(drop=True)
            n = len(sorted_values)
            x = (np.arange(1, n + 1) / n) * 100.0
            figure.add_trace(
                go.Scatter(
                    x=x,
                    y=sorted_values,
                    mode="lines",
                    name=label,
                    hovertemplate=f"<b>{label}</b> | Share: %{{x:.2f}}% | Value: %{{y:,.2f}} <extra></extra>",
                )
            )
        elif plot_mode == "density":
            vals = agg_df[value_column].dropna().astype(float).values
            if vals.size == 0:
                missing_labels.append(label)
                continue
            bins = 100 if vals.size >= 100 else max(10, vals.size)
            hist, edges = np.histogram(vals, bins=bins, density=True)
            centers = (edges[:-1] + edges[1:]) / 2.0
            figure.add_trace(
                go.Scatter(
                    x=centers,
                    y=hist,
                    mode="lines",
                    name=label,
                    hovertemplate=f"<b>{label}</b> | Value: %{{x:,.2f}} | Density: %{{y:.6f}} <extra></extra>",
                )
            )
        else:
            stackgroup = "one" if plot_mode == "stacked_area" else None
            figure.add_trace(
                go.Scatter(
                    x=agg_df["__time"],
                    y=agg_df[value_column],
                    mode="lines",
                    stackgroup=stackgroup,
                    line={"shape": line_shape} if line_shape else None,
                    name=label,
                    hovertemplate=f"<b>{label}</b> | Time: %{{x|%d.%m %H:%M}} | Value: %{{y:,.2f}} <extra></extra>",
                )
            )

    if not figure.data:
        return empty_figure("No data for the selected traces."), ""

    figure.update_layout(
        template="plotly_white",
        hovermode="x unified" if plot_mode in {"line", "stacked_area"} else "closest",
        margin={"l": 30, "r": 20, "t": 40, "b": 30},
        legend={"font": {"size": 10}},
        hoverlabel={"font_size": 10},
    )

    if plot_mode == "duration_curve":
        figure.update_xaxes(title_text="Share of time [%]", range=[0, 100])
        figure.update_yaxes(title_text=value_column)
    elif plot_mode == "density":
        figure.update_xaxes(title_text=value_column)
        figure.update_yaxes(title_text="Density")
    else:
        figure.update_xaxes(title_text=time_column)
        figure.update_yaxes(title_text=value_column)

    notes = [
        f"Trace(s): {len(traces)}",
        f"Plot points: {total_points:,}",
        f"Plot type: {plot_mode}",
        "Aggregation: per trace",
    ]
    if missing_labels:
        notes.append("No data for: " + "; ".join(missing_labels[:5]))
    return figure, " | ".join(notes)


def handle_prefetch(file_select_value, run_select_value, _n_intervals):
    try:
        triggered = ctx.triggered_id
    except Exception:
        triggered = None

    if triggered in {"file-select", "run-select"}:
        selected_file_keys = normalize_file_keys(file_select_value)
        if not selected_file_keys:
            return {"loading": False}, True
        if not is_prefetch_in_progress():
            try:
                start_prefetch(selected_file_keys, warm_plot_cache=True)
            except Exception:
                return {"loading": False}, True
        return {"loading": True}, False

    if triggered == "prefetch-interval":
        in_progress = is_prefetch_in_progress()
        progress = get_load_progress()
        still_warming = in_progress or (
            bool(progress.get("filters_ready")) and not bool(progress.get("plot_ready"))
        )
        return {"loading": still_warming, **progress}, not still_warming

    return {"loading": False}, True


def status_from_readiness(readiness: dict[str, Any] | None, loaded_file_keys: list[str] | None) -> str:
    state = readiness or _default_readiness()
    keys = normalize_file_keys(loaded_file_keys)
    if not keys:
        return "No files selected."
    if state.get("plot_ready"):
        return f"{len(keys)} file(s) loaded. Dashboard ready."
    if state.get("filters_ready"):
        return f"{len(keys)} file(s) loaded. Trace builder ready — preparing visualization..."
    return state.get("detail") or f"Preparing {len(keys)} file(s)..."


def disable_time_resolution_dropdown(aggregation_value: str | None, readiness: dict[str, Any] | None) -> bool:
    if not bool((readiness or {}).get("filters_ready")):
        return True
    return aggregation_value == "none"


def controls_disabled_from_readiness(readiness: dict[str, Any] | None) -> tuple[bool, ...]:
    filters_ready = bool((readiness or {}).get("filters_ready"))
    disabled = not filters_ready
    return (
        disabled,
        disabled,
        disabled,
        disabled,
        disabled,
        disabled,
        disabled,
        disabled,
        disabled,
        disabled,
        disabled,
        disabled,
        disabled,
    )


def keep_run_controls_enabled(_readiness: dict[str, Any] | None) -> tuple[bool, bool, bool, bool]:
    """Run selection and load actions stay interactive while caches warm."""
    return False, False, False, False


def disable_aggregate_button(prefetch_status):
    return False


def disable_controls_during_loading(prefetch_status):
    # Keep UI interactive while background prefetch warms caches.
    disabled = False
    return (
        disabled,
        disabled,
        disabled,
        disabled,
        disabled,
        disabled,
        disabled,
        disabled,
        disabled,
        disabled,
        disabled,
        disabled,
        disabled,
    )


def lock_file_select(loaded_file_keys: list[str] | None, run_key: str | list[str] | None, current_value: str | list[str] | None) -> bool:
    """Disable the `file-select` when the currently loaded files match the selection for the active run.

    This prevents the user from changing file selection inside a loaded run. When the run changes or
    no files are loaded, the control is enabled.
    """
    if not run_key:
        return False

    loaded = set(normalize_file_keys(loaded_file_keys))
    current = set(normalize_file_keys(current_value))
    if loaded and current and loaded == current:
        return True
    return False


def update_global_overlay(loading_style: dict | None) -> dict:
    """Return a style dict for the global overlay based on the loading-indicator style."""
    visible = False
    try:
        visible = bool(loading_style and loading_style.get("display") and loading_style.get("display") != "none")
    except Exception:
        visible = False

    if not visible:
        return {"display": "none"}

    return {
        "position": "fixed",
        "inset": "0",
        "background": "rgba(11,60,93,0.45)",
        "display": "flex",
        "justifyContent": "center",
        "alignItems": "center",
        "zIndex": 9999,
        "pointerEvents": "auto",
    }


def show_loaded_files(loaded_file_selection: list[str] | None):
    keys = normalize_file_keys(loaded_file_selection)
    if not keys:
        return ""
    # Render each key on its own line for readability
    return html.Div([html.Div(k) for k in keys])


def register_callbacks(app: Dash) -> None:
    app.callback(
        Output("run-select", "options"),
        Output("run-select", "value"),
        Input("refresh-files", "n_clicks"),
        State("run-select", "value"),
    )(refresh_run_options)

    app.callback(
        Output("file-select", "options"),
        Output("file-select", "value"),
        Output("status-text", "children", allow_duplicate=True),
        Input("run-select", "value"),
        Input("refresh-files", "n_clicks"),
        State("file-select", "value"),
        prevent_initial_call="initial_duplicate",
    )(sync_files_for_run)

    app.callback(
        Output("time-column", "options"),
        Output("time-column", "value"),
        Output("value-column", "options"),
        Output("value-column", "value"),
        Output("status-text", "children"),
        Output("loaded-file-selection", "data"),
        Output("trace-store", "data"),
        Output("timeseries-graph", "figure", allow_duplicate=True),
        Output("plot-note", "children", allow_duplicate=True),
        Output("loaded-files-dropdown", "options"),
        Output("loaded-files-dropdown", "value"),
        Input("load-data", "n_clicks"),
        State("file-select", "value"),
        State("run-select", "value"),
        State("time-column", "value"),
        State("value-column", "value"),
        prevent_initial_call=True,
        allow_duplicate=True,
        running=_LOAD_RUNNING,
    )(update_controls)

    app.callback(
        Output("trace-run-select", "options"),
        Output("trace-run-select", "value"),
        Output("ws-select", "options"),
        Output("ws-select", "value"),
        Output("market-area-select", "options"),
        Output("market-area-select", "value"),
        Output("property-select", "options"),
        Output("property-select", "value"),
        Output("technology-select", "options"),
        Output("technology-select", "value"),
        Output("unit-select", "options"),
        Output("unit-select", "value"),
        Output("property-select", "disabled", allow_duplicate=True),
        Output("technology-select", "disabled", allow_duplicate=True),
        Output("unit-select", "disabled", allow_duplicate=True),
        Output("unit-select-container", "style"),
        Input("load-data", "n_clicks"),
        Input("loaded-file-selection", "data"),
        Input("readiness-store", "data"),
        Input("aggregation-mode-store", "data"),
        Input("run-select", "value"),
        Input("trace-run-select", "value"),
        Input("ws-select", "value"),
        Input("market-area-select", "value"),
        Input("property-select", "value"),
        Input("technology-select", "value"),
        State("unit-select", "value"),
        prevent_initial_call="initial_duplicate",
    )(update_trace_selector_options)

    app.callback(
        Output("file-select", "disabled"),
        Input("loaded-file-selection", "data"),
        Input("run-select", "value"),
        State("file-select", "value"),
    )(lock_file_select)

    # Select All / Deselect All handlers for file-select
    def _file_select_all_handler(select_all_clicks: int, deselect_all_clicks: int, options: list[dict] | None):
        try:
            triggered = ctx.triggered_id
        except Exception:
            triggered = None
        opts = options or []
        values = [o["value"] for o in opts]
        if triggered == "file-select-all":
            return values
        if triggered == "file-deselect-all":
            return []
        return dash_no_update

    app.callback(
        Output("file-select", "value"),
        Input("file-select-all", "n_clicks"),
        Input("file-deselect-all", "n_clicks"),
        State("file-select", "options"),
        prevent_initial_call=True,
    )(_file_select_all_handler)

    # Global overlay driven by the same loading-indicator style used in running callbacks
    app.callback(
        Output("global-loading-overlay", "style"),
        Input("loading-indicator", "style"),
    )(update_global_overlay)

    app.callback(
        Output("readiness-banner", "children"),
        Input("readiness-store", "data"),
    )(render_readiness_banner)

    app.callback(
        Output("readiness-store", "data"),
        Input("loaded-file-selection", "data"),
        prevent_initial_call=False,
    )(prepare_loaded_files)

    app.callback(
        Output("readiness-store", "data", allow_duplicate=True),
        Input("prefetch-interval", "n_intervals"),
        State("readiness-store", "data"),
        prevent_initial_call=True,
    )(sync_readiness_from_prefetch)

    app.callback(
        Output("loaded-files-display", "children"),
        Input("loaded-file-selection", "data"),
    )(show_loaded_files)

    app.callback(
        Output("trace-store", "data"),
        Output("status-text", "children", allow_duplicate=True),
        Input("add-trace", "n_clicks"),
        Input("remove-trace", "n_clicks"),
        State("trace-store", "data"),
        State("loaded-file-selection", "data"),
        State("trace-run-select", "value"),
        State("market-area-select", "value"),
        State("ws-select", "value"),
        State("property-select", "value"),
        State("technology-select", "value"),
        State("unit-select", "value"),
        State("aggregation", "value"),
        State("time-resolution", "value"),
        State("aggregation-mode-store", "data"),
        State("remove-trace-select", "value"),
        prevent_initial_call=True,
        allow_duplicate=True,
    )(add_remove_trace)

    app.callback(
        Output("trace-list", "children"),
        Output("remove-trace-select", "options"),
        Output("remove-trace-select", "value"),
        Input("trace-store", "data"),
    )(render_trace_list)

    app.callback(
        Output("aggregation-mode-store", "data"),
        Output("aggregate-pemmdb-type", "children"),
        Input("aggregate-pemmdb-type", "n_clicks"),
        State("aggregation-mode-store", "data"),
        State("loaded-file-selection", "data"),
    )(toggle_unit_detail_mode)

    app.callback(
        Output("date-range", "min_date_allowed"),
        Output("date-range", "max_date_allowed"),
        Output("date-range", "start_date"),
        Output("date-range", "end_date"),
        Input("loaded-file-selection", "data"),
        Input("time-column", "value"),
        Input("reset-date-range", "n_clicks"),
    )(update_date_range)

    app.callback(
        Output("timeseries-graph", "figure"),
        Output("plot-note", "children"),
        Input("visualize-data", "n_clicks"),
        Input("plot-mode", "value"),
        State("loaded-file-selection", "data"),
        State("time-column", "value"),
        State("value-column", "value"),
        State("date-range", "start_date"),
        State("date-range", "end_date"),
        State("trace-store", "data"),
        State("aggregation-mode-store", "data"),
        prevent_initial_call=True,
        running=_VISUALIZE_RUNNING,
    )(update_timeseries)

    app.callback(
        Output("status-text", "children", allow_duplicate=True),
        Input("readiness-store", "data"),
        State("loaded-file-selection", "data"),
        prevent_initial_call="initial_duplicate",
    )(status_from_readiness)

    app.callback(
        Output("prefetch-interval", "disabled", allow_duplicate=True),
        Input("loaded-file-selection", "data"),
        Input("readiness-store", "data"),
        prevent_initial_call="initial_duplicate",
    )(
        lambda loaded, readiness: not bool(normalize_file_keys(loaded))
        or bool((readiness or {}).get("plot_ready")),
    )

    app.callback(
        Output("status-text", "children", allow_duplicate=True),
        Input("file-select", "value"),
        Input("run-select", "value"),
        State("loaded-file-selection", "data"),
        prevent_initial_call=True,
    )(describe_file_selection)

    app.callback(
        Output("status-text", "children", allow_duplicate=True),
        Input("load-data", "n_clicks"),
        State("file-select", "value"),
        State("run-select", "value"),
        prevent_initial_call=True,
    )(set_load_status)

    app.callback(
        Output("status-text", "children", allow_duplicate=True),
        Input("visualize-data", "n_clicks"),
        State("trace-store", "data"),
        prevent_initial_call=True,
    )(set_visualize_status)

    app.callback(
        Output("prefetch-status", "data"),
        Output("prefetch-interval", "disabled"),
        Input("file-select", "value"),
        Input("run-select", "value"),
        Input("prefetch-interval", "n_intervals"),
        prevent_initial_call=True,
    )(handle_prefetch)

    # Enable trace/plot controls only after files are fully loaded
    app.callback(
        Output("run-select", "disabled", allow_duplicate=True),
        Output("refresh-files", "disabled", allow_duplicate=True),
        Output("load-data", "disabled", allow_duplicate=True),
        Output("aggregate-pemmdb-type", "disabled", allow_duplicate=True),
        Input("readiness-store", "data"),
        prevent_initial_call="initial_duplicate",
    )(keep_run_controls_enabled)

    app.callback(
        Output("trace-run-select", "disabled", allow_duplicate=True),
        Output("market-area-select", "disabled", allow_duplicate=True),
        Output("ws-select", "disabled", allow_duplicate=True),
        Output("add-trace", "disabled", allow_duplicate=True),
        Output("remove-trace-select", "disabled", allow_duplicate=True),
        Output("remove-trace", "disabled", allow_duplicate=True),
        Output("visualize-data", "disabled", allow_duplicate=True),
        Output("aggregation", "disabled", allow_duplicate=True),
        Output("time-resolution", "disabled", allow_duplicate=True),
        Output("plot-mode", "disabled", allow_duplicate=True),
        Output("date-range", "disabled", allow_duplicate=True),
        Output("reset-date-range", "disabled", allow_duplicate=True),
        Output("value-column", "disabled", allow_duplicate=True),
        Input("readiness-store", "data"),
        prevent_initial_call="initial_duplicate",
    )(controls_disabled_from_readiness)

    app.callback(
        Output("time-resolution", "disabled", allow_duplicate=True),
        Input("aggregation", "value"),
        State("readiness-store", "data"),
        prevent_initial_call="initial_duplicate",
    )(disable_time_resolution_dropdown)

    app.callback(
        Output("aggregate-pemmdb-type", "disabled", allow_duplicate=True),
        Input("prefetch-status", "data"),
        prevent_initial_call=True,
    )(disable_aggregate_button)

    app.callback(
        Output("visualize-data", "disabled", allow_duplicate=True),
        Output("time-column", "disabled", allow_duplicate=True),
        Output("value-column", "disabled", allow_duplicate=True),
        Output("date-range", "disabled", allow_duplicate=True),
        Output("reset-date-range", "disabled", allow_duplicate=True),
        Output("aggregation", "disabled", allow_duplicate=True),
        Output("time-resolution", "disabled", allow_duplicate=True),
        Output("plot-mode", "disabled", allow_duplicate=True),
        Output("trace-run-select", "disabled", allow_duplicate=True),
        Output("market-area-select", "disabled", allow_duplicate=True),
        Output("ws-select", "disabled", allow_duplicate=True),
        Output("add-trace", "disabled", allow_duplicate=True),
        Output("remove-trace-select", "disabled", allow_duplicate=True),
        Output("remove-trace", "disabled", allow_duplicate=True),
        Input("prefetch-status", "data"),
        prevent_initial_call=True,
    )(disable_controls_during_loading)
