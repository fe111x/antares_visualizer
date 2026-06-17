from __future__ import annotations

from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor
import hashlib
import pickle
import os
from typing import Optional
from pathlib import Path
from typing import Any

import pandas as pd
import logging

logger = logging.getLogger(__name__)

from .config import (
    BASE_DIR,
    DATETIME_FORMAT_HINT,
    FILE_SOURCE_COLUMN,
    MAX_OPTION_VALUES,
    RUN_KEY_COLUMN,
    SUPPORTED_EXTENSIONS,
    TECHNOLOGY_SOURCE_COLUMN,
    UNIT_NAME_COLUMN,
)
from .settings import get_run_data_dir, get_runs_root, list_run_ids

SELECTOR_DIMENSION_COLS = ("Sample", "BZ", "WS", "Property", TECHNOLOGY_SOURCE_COLUMN, FILE_SOURCE_COLUMN, RUN_KEY_COLUMN)
PLOT_DEFAULT_COLUMNS = (
    "Datetime",
    "Sample",
    "BZ",
    "WS",
    "Property",
    TECHNOLOGY_SOURCE_COLUMN,
    "Value",
    RUN_KEY_COLUMN,
    FILE_SOURCE_COLUMN,
)
_NUMERIC_ARROW_TYPES = frozenset(
    {
        "int8", "int16", "int32", "int64",
        "uint8", "uint16", "uint32", "uint64",
        "float16", "float32", "float64",
        "halffloat", "float", "double",
    }
)


# --- Metadata-only fast loader -------------------------------------------------
def _read_metadata_slice(entry: tuple[str, str, int]) -> pd.DataFrame:
    file_key, file_path, _mtime_ns = entry
    desired = ["Sample", "BZ", "WS", "Property", TECHNOLOGY_SOURCE_COLUMN, "Unit Name"]
    p = Path(file_path)
    try:
        try:
            import pyarrow.parquet as pq

            pf = pq.ParquetFile(str(p))
            available = set(pf.schema.names)
            cols = [c for c in desired if c in available]
            if cols:
                table = pq.read_table(str(p), columns=cols)
                df = table.to_pandas()
            else:
                df = pd.DataFrame()
        except Exception:
            # Fallback to pandas full read then select subset
            base = _load_table_cached(str(p), p.stat().st_mtime_ns)
            cols = [c for c in desired if c in base.columns]
            df = base[cols].copy() if cols else pd.DataFrame()
    except Exception:
        df = pd.DataFrame()

    if not df.empty:
        df[FILE_SOURCE_COLUMN] = file_key
        df[RUN_KEY_COLUMN] = file_key_to_run_key(file_key)
        # Reduce intermediate size before cross-file concat.
        df = df.drop_duplicates(ignore_index=True)
    return df


@lru_cache(maxsize=24)
def _load_selected_tables_metadata(selection_signature: tuple[tuple[str, str, int], ...]) -> pd.DataFrame:
    """Read only the small set of columns required to populate UI filter options.

    This uses pyarrow if available to read just the requested columns (fast),
    and falls back to reading the full table and selecting the columns when
    pyarrow isn't present or the parquet file doesn't contain the desired
    columns.
    """
    frames: list[pd.DataFrame] = []

    if len(selection_signature) <= 1:
        for entry in selection_signature:
            df = _read_metadata_slice(entry)
            if not df.empty:
                frames.append(df)
    else:
        max_workers = min(6, len(selection_signature))
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            for df in pool.map(_read_metadata_slice, selection_signature):
                if not df.empty:
                    frames.append(df)

    if frames:
        return pd.concat(frames, ignore_index=True, copy=False)
    # return empty frame with expected columns
    return pd.DataFrame(columns=["Sample", "BZ", "WS", "Property", TECHNOLOGY_SOURCE_COLUMN, FILE_SOURCE_COLUMN])


def load_selected_tables_metadata(file_value: str | list[str] | None) -> tuple[pd.DataFrame, list[str]]:
    selected_keys = normalize_file_keys(file_value)
    if not selected_keys:
        raise ValueError("Keine Datei ausgewaehlt")

    selection_signature = _build_selection_signature(selected_keys)
    df = _load_selected_tables_metadata(selection_signature)
    return df, selected_keys


def _compact_trace_selector_frame(df: pd.DataFrame) -> pd.DataFrame:
    cols = [
        c
        for c in (
            FILE_SOURCE_COLUMN,
            RUN_KEY_COLUMN,
            "Sample",
            "BZ",
            "WS",
            "Property",
            TECHNOLOGY_SOURCE_COLUMN,
            UNIT_NAME_COLUMN,
        )
        if c in df.columns
    ]
    if not cols:
        return pd.DataFrame(columns=[RUN_KEY_COLUMN, "Sample", "BZ", "WS", "Property", TECHNOLOGY_SOURCE_COLUMN, FILE_SOURCE_COLUMN])

    compact = df[cols].copy()
    # Remove exact duplicate selector combinations to drastically reduce dropdown work.
    compact = compact.drop_duplicates(ignore_index=True)
    return compact


@lru_cache(maxsize=24)
def _load_trace_selector_index_cached(selection_signature: tuple[tuple[str, str, int], ...]) -> pd.DataFrame:
    metadata_df = _load_selected_tables_metadata(selection_signature)
    return _compact_trace_selector_frame(metadata_df)


def load_trace_selector_index(file_value: str | list[str] | None) -> tuple[pd.DataFrame, list[str]]:
    selected_keys = normalize_file_keys(file_value)
    if not selected_keys:
        raise ValueError("Keine Datei ausgewaehlt")

    selection_signature = _build_selection_signature(selected_keys)
    df = _load_trace_selector_index_cached(selection_signature)
    return df, selected_keys


def _to_option(value: Any) -> dict[str, Any]:
    if hasattr(value, "item"):
        try:
            value = value.item()
        except (ValueError, TypeError):
            pass
    return {"label": str(value), "value": value}


def _sorted_options(values: set[Any]) -> list[dict[str, Any]]:
    options = [_to_option(value) for value in values]
    options.sort(key=lambda item: item["label"])
    if len(options) > MAX_OPTION_VALUES:
        return options[:MAX_OPTION_VALUES]
    return options


def file_key_to_run_key(file_key: str) -> str:
    if file_key.startswith("@"):
        marker = "/runs/"
        if marker in file_key:
            return file_key.split(marker, 1)[1].split("/", 1)[0]
        return "."
    path = Path(file_key)
    if path.parts:
        runs_root_name = get_runs_root().name
        if len(path.parts) >= 2 and path.parts[0] == runs_root_name:
            return path.parts[1]
    resolved = resolve_file_path(file_key)
    run_id = _path_run_id(resolved)
    return run_id if run_id else "."


def _is_meaningful_selector_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, float) and pd.isna(value):
        return False
    if isinstance(value, str) and not value.strip():
        return False
    return True


def _dataframe_to_selector_hierarchy(df: pd.DataFrame) -> dict[str, Any]:
    """Build run-wide selector tree: run -> ws -> market -> properties/technologies."""
    if df.empty:
        return {"runs": [], "tree": {}}

    run_col = RUN_KEY_COLUMN if RUN_KEY_COLUMN in df.columns else None
    if run_col is None:
        return {"runs": [], "tree": {}}

    market_col = "BZ" if "BZ" in df.columns else None
    ws_col = "WS" if "WS" in df.columns else None
    property_col = "Property" if "Property" in df.columns else None
    tech_col = TECHNOLOGY_SOURCE_COLUMN if TECHNOLOGY_SOURCE_COLUMN in df.columns else None

    if not (market_col and ws_col):
        return {"runs": [], "tree": {}}

    tree: dict[Any, dict[Any, dict[Any, dict[str, set[Any]]]]] = {}
    runs: set[Any] = set()
    column_names = list(df.columns)
    for row in df.itertuples(index=False, name=None):
        row_map = dict(zip(column_names, row))
        run = row_map.get(run_col)
        market = row_map.get(market_col)
        ws = row_map.get(ws_col)
        if run is None or market is None or ws is None:
            continue
        runs.add(run)
        leaf = tree.setdefault(run, {}).setdefault(ws, {}).setdefault(
            market,
            {"standalone_properties": set(), "property_technologies": {}},
        )
        prop = row_map.get(property_col) if property_col else None
        tech = row_map.get(tech_col) if tech_col else None
        has_tech = _is_meaningful_selector_value(tech)
        if _is_meaningful_selector_value(prop) and not has_tech:
            leaf["standalone_properties"].add(prop)
        if _is_meaningful_selector_value(prop) and has_tech:
            leaf["property_technologies"].setdefault(prop, set()).add(tech)

    return {"runs": _sorted_options(runs), "tree": tree}


def get_trace_selector_leaf(hierarchy: dict[str, Any], run: Any, ws: Any, market: Any) -> dict[str, Any]:
    default: dict[str, Any] = {"standalone_properties": set(), "property_technologies": {}}
    return hierarchy.get("tree", {}).get(run, {}).get(ws, {}).get(market, default)


def property_requires_technology(leaf: dict[str, Any], property_value: Any) -> bool:
    if property_value is None:
        return False
    return property_value in leaf.get("property_technologies", {})


def get_unit_options_for_context(
    file_value: str | list[str] | None,
    run: Any,
    ws: Any,
    market: Any,
    property_value: Any,
    technology_value: Any,
) -> list[dict[str, object]]:
    selected_keys = normalize_file_keys(file_value)
    if not selected_keys or property_value is None:
        return []

    df, _ = load_trace_selector_index(selected_keys)
    if df.empty or UNIT_NAME_COLUMN not in df.columns:
        return []

    frame = df
    if RUN_KEY_COLUMN in frame.columns and run is not None:
        frame = frame[frame[RUN_KEY_COLUMN].astype(str) == str(run)]
    if "BZ" in frame.columns and market is not None:
        frame = frame[frame["BZ"].astype(str) == str(market)]
    if "WS" in frame.columns and ws is not None:
        try:
            ws_numeric = pd.to_numeric(frame["WS"], errors="coerce")
            frame = frame[ws_numeric == float(ws)]
        except (ValueError, TypeError):
            frame = frame[frame["WS"].astype(str) == str(ws)]
    if "Property" in frame.columns:
        frame = frame[frame["Property"].astype(str) == str(property_value)]
    if technology_value is not None and TECHNOLOGY_SOURCE_COLUMN in frame.columns:
        frame = frame[frame[TECHNOLOGY_SOURCE_COLUMN].astype(str) == str(technology_value)]

    if frame.empty:
        return []
    units = {
        value
        for value in frame[UNIT_NAME_COLUMN].dropna().unique()
        if _is_meaningful_selector_value(value)
    }
    return _sorted_options(units)


@lru_cache(maxsize=24)
def _load_selector_hierarchy_cached(selection_signature: tuple[tuple[str, str, int], ...]) -> dict[str, Any]:
    metadata_df = _load_trace_selector_index_cached(selection_signature)
    return _dataframe_to_selector_hierarchy(metadata_df)


def get_selector_hierarchy(file_value: str | list[str] | None) -> dict[str, Any]:
    selected_keys = normalize_file_keys(file_value)
    if not selected_keys:
        return {"runs": [], "tree": {}}
    selection_signature = _build_selection_signature(selected_keys)
    return _load_selector_hierarchy_cached(selection_signature)


def file_keys_for_run(run_key: str, loaded_keys: list[str] | None = None) -> list[str]:
    keys = normalize_file_keys(loaded_keys) if loaded_keys else [opt["value"] for opt in build_file_options(run_key)]
    return [key for key in keys if file_key_to_run_key(key) == run_key]


# Set by app_factory during app initialization if Flask-Caching is configured.
CACHE: Optional[object] = None


def _make_selection_cache_key(prefix: str, selection_signature: tuple[tuple[str, str, int], ...]) -> str:
    # Use a sha256 of the pickled signature for stable keys
    blob = pickle.dumps(selection_signature)
    h = hashlib.sha256(blob).hexdigest()
    return f"{prefix}:{h}"


def _cache_get(key: str):
    if CACHE is None:
        return None
    try:
        raw = CACHE.get(key)
    except Exception:
        return None
    if raw is None:
        return None
    try:
        return pickle.loads(raw)
    except Exception:
        return None


def _cache_set(key: str, value, timeout: int | None = None):
    if CACHE is None:
        return
    try:
        raw = pickle.dumps(value)
        if timeout is None:
            CACHE.set(key, raw)
        else:
            CACHE.set(key, raw, timeout=timeout)
    except Exception:
        return


@lru_cache(maxsize=1)
def discover_input_files() -> list[Path]:
    files: list[Path] = []
    for run_id in list_run_ids():
        data_dir = get_run_data_dir(run_id)
        if not data_dir.is_dir():
            continue
        for path in data_dir.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            files.append(path.resolve())
    return sorted(set(files))


def _path_run_id(path: Path) -> str | None:
    resolved = path.resolve()
    for run_id in list_run_ids():
        data_dir = get_run_data_dir(run_id)
        try:
            resolved.relative_to(data_dir.resolve())
            return run_id
        except ValueError:
            continue
    return None


def path_to_key(path: Path) -> str:
    try:
        return path.relative_to(BASE_DIR).as_posix()
    except ValueError:
        return path.as_posix()


def _extract_run_key(path: Path) -> str:
    run_id = _path_run_id(path)
    if run_id:
        return run_id
    relative = path.resolve()
    try:
        relative = path.resolve().relative_to(get_runs_root().resolve())
        if relative.parts:
            return relative.parts[0]
    except ValueError:
        pass
    return "."


def build_run_options() -> list[dict[str, str]]:
    """List every run folder under runs_root, not only runs with discovered files."""
    run_keys = list_run_ids()
    if not run_keys:
        run_keys = sorted({_extract_run_key(path) for path in discover_input_files()})
    options: list[dict[str, str]] = []
    for run_key in run_keys:
        label = "(data root)" if run_key == "." else run_key
        options.append({"label": label, "value": run_key})
    return options


def build_file_options(run_key: str | list[str] | None = None) -> list[dict[str, str]]:
    """
    Build file options optionally filtered by a run key or list of run keys.
    """
    paths = discover_input_files()
    if run_key is not None:
        if isinstance(run_key, list):
            allowed = set(run_key)
            paths = [path for path in paths if _extract_run_key(path) in allowed]
        else:
            paths = [path for path in paths if _extract_run_key(path) == run_key]
    return [{"label": path_to_key(path), "value": path_to_key(path)} for path in paths]


@lru_cache(maxsize=32)
def _read_parquet_schema_cached(file_path: str, mtime_ns: int) -> tuple[str, ...]:
    import pyarrow.parquet as pq

    pf = pq.ParquetFile(file_path)
    return tuple(pf.schema.names)


def _schema_numeric_columns(column_names: tuple[str, ...], file_path: str, mtime_ns: int) -> list[str]:
    suffix = Path(file_path).suffix.lower()
    if suffix == ".parquet":
        try:
            import pyarrow.parquet as pq

            schema = pq.ParquetFile(file_path).schema_arrow
            numeric: list[str] = []
            for name in column_names:
                try:
                    arrow_type = str(schema.field(name).type).lower()
                except (KeyError, AttributeError):
                    continue
                if any(token in arrow_type for token in _NUMERIC_ARROW_TYPES):
                    numeric.append(name)
            return numeric
        except Exception:
            pass
    return [name for name in column_names if name not in SELECTOR_DIMENSION_COLS]


@lru_cache(maxsize=32)
def _infer_schema_profile_cached(file_path: str, mtime_ns: int) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        columns = _read_parquet_schema_cached(file_path, mtime_ns)
    elif suffix == ".csv":
        header = pd.read_csv(path, nrows=0)
        columns = tuple(str(col).strip() for col in header.columns)
    else:
        raise ValueError(f"Nicht unterstuetztes Dateiformat: {suffix}")

    column_list = list(columns)
    time_columns = tuple(col for col in column_list if looks_like_time_column_name(col))
    numeric_columns = tuple(_schema_numeric_columns(columns, file_path, mtime_ns))
    return columns, time_columns, numeric_columns


def infer_schema_profile(file_key: str) -> dict[str, list[str]]:
    path = resolve_file_path(file_key)
    columns, time_columns, numeric_columns = _infer_schema_profile_cached(str(path), path.stat().st_mtime_ns)
    return {
        "columns": list(columns),
        "time_columns": list(time_columns),
        "numeric_columns": list(numeric_columns),
    }


def _read_datetime_bounds_slice(entry: tuple[str, str, int], time_column: str) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    _file_key, file_path, _mtime_ns = entry
    path = Path(file_path)
    try:
        import pyarrow.parquet as pq

        pf = pq.ParquetFile(str(path))
        if time_column not in pf.schema.names:
            return None, None

        col_idx = pf.schema.names.index(time_column)
        min_raw: Any | None = None
        max_raw: Any | None = None
        for row_group_idx in range(pf.num_row_groups):
            column_stats = pf.metadata.row_group(row_group_idx).column(col_idx).statistics
            if column_stats is None or not column_stats.has_min_max:
                min_raw = None
                max_raw = None
                break
            min_raw = column_stats.min if min_raw is None else min(min_raw, column_stats.min)
            max_raw = column_stats.max if max_raw is None else max(max_raw, column_stats.max)

        if min_raw is not None and max_raw is not None:
            parsed = parse_datetime(pd.Series([min_raw, max_raw]))
            parsed = parsed[parsed.notna()]
            if len(parsed) == 2:
                return parsed.iloc[0], parsed.iloc[1]

        table = pq.read_table(str(path), columns=[time_column])
        series = table.column(0).to_pandas()
    except Exception:
        try:
            df = pd.read_parquet(path, columns=[time_column])
            series = df[time_column]
        except Exception:
            try:
                df = pd.read_csv(path, usecols=[time_column], low_memory=False)
                series = df[time_column]
            except Exception:
                return None, None

    parsed = parse_datetime(series)
    parsed = parsed[parsed.notna()]
    if parsed.empty:
        return None, None
    return parsed.min(), parsed.max()


@lru_cache(maxsize=24)
def _load_datetime_bounds_cached(
    selection_signature: tuple[tuple[str, str, int], ...],
    time_column: str,
) -> tuple[str | None, str | None]:
    if not selection_signature:
        return None, None

    mins: list[pd.Timestamp] = []
    maxs: list[pd.Timestamp] = []
    if len(selection_signature) == 1:
        min_val, max_val = _read_datetime_bounds_slice(selection_signature[0], time_column)
        if min_val is not None:
            mins.append(min_val)
        if max_val is not None:
            maxs.append(max_val)
    else:
        max_workers = min(8, len(selection_signature))
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            for min_val, max_val in pool.map(
                lambda entry: _read_datetime_bounds_slice(entry, time_column),
                selection_signature,
            ):
                if min_val is not None:
                    mins.append(min_val)
                if max_val is not None:
                    maxs.append(max_val)

    if not mins or not maxs:
        return None, None
    return pd.Timestamp(min(mins)).date().isoformat(), pd.Timestamp(max(maxs)).date().isoformat()


def read_datetime_bounds(file_value: str | list[str] | None, time_column: str) -> tuple[str | None, str | None]:
    selected_keys = normalize_file_keys(file_value)
    if not selected_keys or not time_column:
        return None, None
    selection_signature = _build_selection_signature(selected_keys)
    return _load_datetime_bounds_cached(selection_signature, time_column)


def resolve_file_path(file_key: str) -> Path:
    if file_key.startswith("@"):
        path = Path(file_key[1:]).expanduser().resolve()
    else:
        path = (BASE_DIR / file_key).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Datei nicht gefunden: {file_key}")
    return path


@lru_cache(maxsize=24)
def _load_table_columns_cached(file_path: str, mtime_ns: int, columns: tuple[str, ...], file_key: str) -> pd.DataFrame:
    path = Path(file_path)
    suffix = path.suffix.lower()
    column_list = [col for col in columns if col]
    if suffix == ".parquet":
        try:
            import pyarrow.parquet as pq

            available = set(pq.ParquetFile(str(path)).schema.names)
            read_cols = [col for col in column_list if col in available]
            if read_cols:
                df = pq.read_table(str(path), columns=read_cols).to_pandas()
            else:
                df = pd.DataFrame()
        except Exception:
            df = pd.read_parquet(path, columns=column_list or None)
    elif suffix == ".csv":
        df = pd.read_csv(path, usecols=column_list or None, low_memory=False)
    else:
        raise ValueError(f"Nicht unterstuetztes Dateiformat: {suffix}")

    df.columns = [str(col).strip() for col in df.columns]
    if FILE_SOURCE_COLUMN not in df.columns:
        df[FILE_SOURCE_COLUMN] = file_key
    if RUN_KEY_COLUMN not in df.columns:
        df[RUN_KEY_COLUMN] = file_key_to_run_key(file_key)
    return df


def _resolve_plot_columns(selection_signature: tuple[tuple[str, str, int], ...], columns: tuple[str, ...] | None) -> tuple[str, ...]:
    if columns:
        requested = list(columns)
    else:
        requested = list(PLOT_DEFAULT_COLUMNS)

    available: set[str] = set()
    for _file_key, file_path, mtime_ns in selection_signature:
        profile = _infer_schema_profile_cached(file_path, mtime_ns)
        available.update(profile[0])

    resolved = [col for col in requested if col in available]
    if FILE_SOURCE_COLUMN not in resolved and FILE_SOURCE_COLUMN in available:
        resolved.append(FILE_SOURCE_COLUMN)
    return tuple(resolved)


@lru_cache(maxsize=12)
def _load_selected_tables_projected_cached(
    selection_signature: tuple[tuple[str, str, int], ...],
    columns: tuple[str, ...],
) -> pd.DataFrame:
    if not selection_signature:
        raise ValueError("Keine Datei ausgewaehlt")

    resolved_columns = _resolve_plot_columns(selection_signature, columns)
    if len(selection_signature) == 1:
        file_key, file_path, mtime_ns = selection_signature[0]
        return _load_table_columns_cached(file_path, mtime_ns, resolved_columns, file_key)

    frames: list[pd.DataFrame] = []
    max_workers = min(8, len(selection_signature))

    def _load_one(entry: tuple[str, str, int]) -> pd.DataFrame:
        file_key, file_path, mtime_ns = entry
        return _load_table_columns_cached(file_path, mtime_ns, resolved_columns, file_key)

    if max_workers <= 1:
        for entry in selection_signature:
            frames.append(_load_one(entry))
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            frames.extend(pool.map(_load_one, selection_signature))

    return pd.concat(frames, ignore_index=True, copy=False)


@lru_cache(maxsize=12)
def _load_table_cached(file_path: str, mtime_ns: int) -> pd.DataFrame:
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        df = pd.read_parquet(path)
    elif suffix == ".csv":
        df = pd.read_csv(path, low_memory=False)
    else:
        raise ValueError(f"Nicht unterstuetztes Dateiformat: {suffix}")

    # Ensure column names are clean and stable for filtering.
    df.columns = [str(col).strip() for col in df.columns]

    return df


def load_table(file_key: str) -> pd.DataFrame:
    path = resolve_file_path(file_key)
    return _load_table_cached(str(path), path.stat().st_mtime_ns)


@lru_cache(maxsize=24)
def _load_table_with_source_cached(file_path: str, mtime_ns: int, file_key: str) -> pd.DataFrame:
    base = _load_table_cached(file_path, mtime_ns)
    with_source = base.copy()
    with_source[FILE_SOURCE_COLUMN] = file_key
    with_source[RUN_KEY_COLUMN] = file_key_to_run_key(file_key)
    return with_source


def normalize_file_keys(file_value: str | list[str] | None) -> list[str]:
    if file_value is None:
        return []
    if isinstance(file_value, list):
        return [str(value) for value in file_value if value]
    return [str(file_value)]


def _build_selection_signature(selected_keys: list[str]) -> tuple[tuple[str, str, int], ...]:
    signature: list[tuple[str, str, int]] = []
    for file_key in selected_keys:
        path = resolve_file_path(file_key)
        signature.append((file_key, str(path), path.stat().st_mtime_ns))
    return tuple(signature)


@lru_cache(maxsize=10)
def _load_selected_tables_cached(selection_signature: tuple[tuple[str, str, int], ...]) -> pd.DataFrame:
    if not selection_signature:
        raise ValueError("Keine Datei ausgewaehlt")

    if len(selection_signature) == 1:
        file_key, file_path, mtime_ns = selection_signature[0]
        return _load_table_with_source_cached(file_path, mtime_ns, file_key)

    frames: list[pd.DataFrame] = []
    max_workers = min(8, len(selection_signature))

    def _load_one(entry: tuple[str, str, int]) -> pd.DataFrame:
        file_key, file_path, mtime_ns = entry
        return _load_table_with_source_cached(file_path, mtime_ns, file_key)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        frames.extend(pool.map(_load_one, selection_signature))

    return pd.concat(frames, ignore_index=True, copy=False)


@lru_cache(maxsize=10)
def _load_selected_tables_tech_aggregated_cached(
    selection_signature: tuple[tuple[str, str, int], ...]
) -> pd.DataFrame:
    base_df = _load_selected_tables_cached(selection_signature)
    if base_df.empty:
        return base_df

    # Only aggregate if we can safely collapse unit-level detail into technology-level values.
    if TECHNOLOGY_SOURCE_COLUMN not in base_df.columns or "Unit Name" not in base_df.columns:
        return base_df

    # Exclude any group columns from numeric_columns to avoid conflicts
    # when pandas attempts to re-insert group keys during `.reset_index()`.
    numeric_columns = [col for col in base_df.columns if pd.api.types.is_numeric_dtype(base_df[col])]
    if not numeric_columns:
        return base_df

    group_columns = [
        col for col in base_df.columns if col not in numeric_columns and col != "Unit Name"
    ]
    if not group_columns:
        return base_df

    # If any of the numeric columns accidentally overlap with group columns (e.g. 'WS'),
    # remove them from the aggregation target to prevent pandas from raising
    # "cannot insert <col>, already exists" on reset_index.
    agg_targets = [c for c in numeric_columns if c not in group_columns]
    # Debugging output to trace duplicate insertion issues.
    logger.debug("DEBUG: group_columns=%s", group_columns)
    logger.debug("DEBUG: numeric_columns=%s", numeric_columns)
    logger.debug("DEBUG: agg_targets=%s", agg_targets)
    if not agg_targets:
        return base_df

    aggregated_df = (
        base_df.groupby(group_columns, observed=True, dropna=False, sort=False)[agg_targets]
        .sum()
        .reset_index()
    )
    return aggregated_df


@lru_cache(maxsize=10)
def _load_selected_tables_pemmdb_type_aggregated_cached(
    selection_signature: tuple[tuple[str, str, int], ...]
) -> pd.DataFrame:
    """Aggregate data by PEMMDB_TYPE: sum numeric columns but preserve Property, BZ, Sample, WS (only remove Unit Name)."""
    base_df = _load_selected_tables_cached(selection_signature)
    if base_df.empty:
        return base_df

    # Only aggregate if PEMMDB_TYPE column exists.
    if TECHNOLOGY_SOURCE_COLUMN not in base_df.columns:
        return base_df

    numeric_columns = [col for col in base_df.columns if pd.api.types.is_numeric_dtype(base_df[col])]
    if not numeric_columns:
        return base_df

    # Detect time columns to preserve them in aggregation.
    time_columns = detect_time_columns(base_df)
    time_cols_in_df = [col for col in time_columns if col in base_df.columns]
    
    # Group by PEMMDB_TYPE, Property, BZ, Sample, WS, and time columns.
    # This preserves all dimension info except Unit Name.
    group_columns = [TECHNOLOGY_SOURCE_COLUMN]
    for col in ["Property", "BZ", "Sample", "WS"]:
        if col in base_df.columns:
            group_columns.append(col)
    group_columns.extend(time_cols_in_df)

    # Exclude any numeric columns that overlap with group columns to avoid
    # pandas inserting a column that already exists during reset_index().
    agg_targets = [c for c in numeric_columns if c not in group_columns]
    logger.debug("DEBUG: group_columns=%s", group_columns)
    logger.debug("DEBUG: numeric_columns=%s", numeric_columns)
    logger.debug("DEBUG: agg_targets=%s", agg_targets)
    if not agg_targets:
        return base_df

    aggregated_df = (
        base_df.groupby(group_columns, observed=True, dropna=False, sort=False)[agg_targets]
        .sum()
        .reset_index()
    )
    return aggregated_df


@lru_cache(maxsize=10)
def _load_selected_tables_with_persistent_cache(selection_signature: tuple[tuple[str, str, int], ...]) -> pd.DataFrame:
    cache_key = _make_selection_cache_key("raw", selection_signature)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    df = _load_selected_tables_cached(selection_signature)
    _cache_set(cache_key, df)
    return df


@lru_cache(maxsize=10)
def _load_selected_tables_tech_with_persistent_cache(selection_signature: tuple[tuple[str, str, int], ...]) -> pd.DataFrame:
    cache_key = _make_selection_cache_key("tech_agg", selection_signature)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    df = _load_selected_tables_tech_aggregated_cached(selection_signature)
    _cache_set(cache_key, df)
    return df


@lru_cache(maxsize=10)
def _load_selected_tables_pemmdb_with_persistent_cache(selection_signature: tuple[tuple[str, str, int], ...]) -> pd.DataFrame:
    cache_key = _make_selection_cache_key("pemmdb_agg", selection_signature)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    df = _load_selected_tables_pemmdb_type_aggregated_cached(selection_signature)
    _cache_set(cache_key, df)
    return df


def load_selected_tables(
    file_value: str | list[str] | None,
    columns: tuple[str, ...] | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    selected_keys = normalize_file_keys(file_value)
    if not selected_keys:
        raise ValueError("Keine Datei ausgewaehlt")

    selection_signature = _build_selection_signature(selected_keys)
    if columns:
        df = _load_selected_tables_projected_cached(selection_signature, columns)
    else:
        df = _load_selected_tables_with_persistent_cache(selection_signature)
    return df, selected_keys


def load_selected_tables_technology_aggregated(
    file_value: str | list[str] | None,
) -> tuple[pd.DataFrame, list[str]]:
    selected_keys = normalize_file_keys(file_value)
    if not selected_keys:
        raise ValueError("Keine Datei ausgewaehlt")

    selection_signature = _build_selection_signature(selected_keys)
    df = _load_selected_tables_tech_with_persistent_cache(selection_signature)
    return df, selected_keys


def load_selected_tables_pemmdb_type_aggregated(
    file_value: str | list[str] | None,
) -> tuple[pd.DataFrame, list[str]]:
    """Load and aggregate selected files by PEMMDB_TYPE only (sum across all other dimensions)."""
    selected_keys = normalize_file_keys(file_value)
    if not selected_keys:
        raise ValueError("Keine Datei ausgewaehlt")

    selection_signature = _build_selection_signature(selected_keys)
    df = _load_selected_tables_pemmdb_with_persistent_cache(selection_signature)
    return df, selected_keys


def looks_like_time_column_name(column_name: str) -> bool:
    lowered = column_name.lower()
    return any(token in lowered for token in ("datetime", "date", "time", "hour", "timestamp"))


def parse_datetime(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, format=DATETIME_FORMAT_HINT, errors="coerce")
    if parsed.notna().mean() < 0.8:
        parsed = pd.to_datetime(series, errors="coerce")
    return parsed


def detect_time_columns(df: pd.DataFrame) -> list[str]:
    candidates = [col for col in df.columns if looks_like_time_column_name(col)]
    checked = set(candidates)

    object_columns = [
        col
        for col in df.columns
        if col not in checked and (pd.api.types.is_object_dtype(df[col]) or pd.api.types.is_string_dtype(df[col]))
    ]

    for col in object_columns[:8]:
        sample = df[col].dropna().head(1_500)
        if sample.empty:
            continue
        parsed = parse_datetime(sample)
        if parsed.notna().mean() > 0.9:
            candidates.append(col)

    # Preserve order and remove duplicates.
    seen: set[str] = set()
    result: list[str] = []
    for col in candidates:
        if col not in seen:
            result.append(col)
            seen.add(col)
    return result


def _to_python_scalar(value: Any) -> Any:
    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, TypeError):
            return value
    return value


def build_value_options(series: pd.Series, max_items: int = MAX_OPTION_VALUES) -> list[dict[str, Any]]:
    unique_values = pd.Series(series.dropna().unique())
    if unique_values.empty:
        return []

    try:
        unique_values = unique_values.sort_values(ignore_index=True)
    except TypeError:
        unique_values = unique_values.astype(str).sort_values(ignore_index=True)

    if len(unique_values) > max_items:
        unique_values = unique_values.iloc[:max_items]

    options: list[dict[str, Any]] = []
    for raw_value in unique_values.tolist():
        value = _to_python_scalar(raw_value)
        if pd.isna(value):
            continue
        options.append({"label": str(value), "value": value})
    return options


def apply_filter(df: pd.DataFrame, column: str, selected_values: list[Any] | None) -> pd.DataFrame:
    if column not in df.columns:
        return df
    if not selected_values:
        return df
    return df[df[column].isin(selected_values)]
