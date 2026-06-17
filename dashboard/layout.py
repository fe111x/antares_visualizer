from __future__ import annotations

from dash import dcc, html

from .config import (
    ACTION_COLUMN_STYLE,
    APP_STYLE,
    CONTROL_GRID_STYLE,
    CONTROL_ITEM_STYLE,
    CONTROL_LABEL_STYLE,
    FILE_PICKER_STYLE,
    FILE_ROW_STYLE,
    FILE_SUMMARY_STYLE,
    GRAPH_CARD_STYLE,
    HEADER_CARD_STYLE,
    HEADER_SUBTITLE_STYLE,
    HEADER_TITLE_STYLE,
    LOADING_BAR_HIDDEN_STYLE,
    PRIMARY_ACTION_BUTTON_STYLE,
    PLOT_GRAPH_STYLE,
    PLOT_NOTE_STYLE,
    READINESS_BANNER_STYLE,
    SECONDARY_ACTION_BUTTON_STYLE,
    SECTION_ACTION_HINT_STYLE,
    SECTION_ACTION_ROW_STYLE,
    STATUS_STYLE,
    TRACE_ACTION_ROW_STYLE,
)
from .plotting import empty_figure

_HIDDEN = {"display": "none"}


def build_layout(
    initial_run_options: list[dict[str, str]],
    initial_run_value: str | list[str] | None,
    initial_file_options: list[dict[str, str]],
    initial_file_values: list[str],
) -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Img(src="/assets/vamos_logo.png", style={"height": "44px", "marginRight": "12px"}),
                            html.Div(
                                [
                                    html.H1(
                                        "VAMOS Analyzer - Adequacy Data Prototype V1",
                                        style={"margin": 0, "color": "#ffffff", "fontSize": "1.25rem"},
                                    ),
                                ],
                                style={"display": "flex", "flexDirection": "column", "justifyContent": "center"},
                            ),
                        ],
                        style={"display": "flex", "alignItems": "center"},
                    )
                ],
                style={
                    "background": "#0b3c5d",
                    "padding": "12px 18px",
                    "borderRadius": "8px",
                    "marginBottom": "12px",
                    "display": "flex",
                    "alignItems": "center",
                },
            ),
            html.Div(
                id="global-loading-overlay",
                style={"display": "none"},
                children=[
                    html.Div(
                        [
                            html.Span(className="loading-spinner"),
                            html.Span("Loading data...", style={"marginLeft": "10px", "fontSize": "16px", "fontWeight": 600}),
                        ],
                        style={"display": "flex", "alignItems": "center", "color": "#ffffff"},
                    )
                ],
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Label("Runs", style=CONTROL_LABEL_STYLE),
                            dcc.Dropdown(
                                id="run-select",
                                options=initial_run_options,
                                value=initial_run_value,
                                multi=True,
                                placeholder="Select one or more runs",
                            ),
                        ],
                        style=CONTROL_ITEM_STYLE,
                    ),
                    html.Div(
                        [
                            html.Button(
                                "Refresh file list",
                                id="refresh-files",
                                n_clicks=0,
                                className="action-button action-button-secondary",
                                style=SECONDARY_ACTION_BUTTON_STYLE,
                            ),
                            html.Button(
                                "Unit-level detail: Off",
                                id="aggregate-pemmdb-type",
                                n_clicks=0,
                                className="action-button action-button-secondary",
                                style=SECONDARY_ACTION_BUTTON_STYLE,
                            ),
                            html.Button(
                                "Load Data",
                                id="load-data",
                                n_clicks=0,
                                className="action-button action-button-primary",
                                style=PRIMARY_ACTION_BUTTON_STYLE,
                            ),
                        ],
                        style=ACTION_COLUMN_STYLE,
                    ),
                    html.Div(
                        id="hidden-file-controls",
                        style=_HIDDEN,
                        children=[
                            dcc.Dropdown(
                                id="file-select",
                                options=initial_file_options,
                                value=initial_file_values,
                                multi=True,
                            ),
                            html.Button("Select All", id="file-select-all", n_clicks=0),
                            html.Button("Deselect All", id="file-deselect-all", n_clicks=0),
                        ],
                    ),
                ],
                style=FILE_ROW_STYLE,
            ),
            html.Div(
                [
                    html.Div(id="status-text", style=STATUS_STYLE),
                    html.Div(id="readiness-banner", style=READINESS_BANNER_STYLE),
                    dcc.Dropdown(id="loaded-files-dropdown", multi=True, disabled=True, style=_HIDDEN),
                    html.Div(id="loaded-files-display", style=_HIDDEN),
                ],
            ),
            html.Div(
                id="loading-indicator",
                style=LOADING_BAR_HIDDEN_STYLE,
                children=[
                    html.Div(
                        [
                            html.Span(className="loading-spinner"),
                            html.Span("Loading data..."),
                        ],
                        style={
                            "display": "flex",
                            "alignItems": "center",
                            "gap": "8px",
                            "fontSize": "12px",
                            "color": "#64748b",
                            "marginBottom": "6px",
                        },
                    ),
                    html.Div(
                        className="loading-progress-track",
                        children=[html.Div(className="loading-progress-bar")],
                    ),
                ],
            ),
            html.Div(
                [
                    html.Div(
                        [
                            dcc.Dropdown(
                                id="time-column",
                                options=[{"label": "Datetime", "value": "Datetime"}],
                                value="Datetime",
                                clearable=False,
                                style=_HIDDEN,
                            ),
                        ],
                        style=_HIDDEN,
                    ),
                    html.Div(
                        [
                            html.Label("Time range", style=CONTROL_LABEL_STYLE),
                            html.Div(
                                [
                                    dcc.DatePickerRange(
                                        id="date-range",
                                        minimum_nights=0,
                                        clearable=True,
                                        display_format="DD.MM.YY",
                                        start_date_placeholder_text="From",
                                        end_date_placeholder_text="To",
                                        className="compact-date-range",
                                        disabled=True,
                                    ),
                                    html.Button(
                                        "Reset",
                                        id="reset-date-range",
                                        n_clicks=0,
                                        disabled=True,
                                        className="action-button action-button-secondary",
                                        style={**SECONDARY_ACTION_BUTTON_STYLE, "width": "auto", "minWidth": "88px", "height": "36px"},
                                    ),
                                ],
                                className="date-range-row",
                            ),
                        ],
                        style=CONTROL_ITEM_STYLE,
                    ),
                    html.Div(
                        [
                            html.Label("Value column", style=CONTROL_LABEL_STYLE),
                            dcc.Dropdown(id="value-column", clearable=False, disabled=True),
                        ],
                        style=CONTROL_ITEM_STYLE,
                    ),
                    html.Div(
                        [
                            html.Label("Run", style=CONTROL_LABEL_STYLE),
                            dcc.Dropdown(id="trace-run-select", clearable=False, placeholder="Select run", disabled=True),
                        ],
                        style=CONTROL_ITEM_STYLE,
                    ),
                    html.Div(
                        [
                            html.Label("Weather scenario (WS)", style=CONTROL_LABEL_STYLE),
                            dcc.Dropdown(id="ws-select", clearable=False, placeholder="Select WS", disabled=True),
                        ],
                        style=CONTROL_ITEM_STYLE,
                    ),
                    html.Div(
                        [
                            html.Label("Market area", style=CONTROL_LABEL_STYLE),
                            dcc.Dropdown(id="market-area-select", clearable=False, placeholder="Select market area", disabled=True),
                        ],
                        style=CONTROL_ITEM_STYLE,
                    ),
                    html.Div(
                        [
                            html.Label("Property", style=CONTROL_LABEL_STYLE),
                            dcc.Dropdown(id="property-select", clearable=True, placeholder="Select property", disabled=True),
                        ],
                        style=CONTROL_ITEM_STYLE,
                    ),
                    html.Div(
                        [
                            html.Label("PEMMDB technology", style=CONTROL_LABEL_STYLE),
                            dcc.Dropdown(id="technology-select", clearable=True, placeholder="Select technology", disabled=True),
                        ],
                        style=CONTROL_ITEM_STYLE,
                    ),
                    html.Div(
                        [
                            html.Label("Unit", style=CONTROL_LABEL_STYLE),
                            dcc.Dropdown(
                                id="unit-select",
                                clearable=True,
                                placeholder="Select unit",
                                disabled=True,
                            ),
                        ],
                        id="unit-select-container",
                        style=CONTROL_ITEM_STYLE,
                    ),
                    html.Div(
                        [
                            html.Label("Aggregation (next trace)", style=CONTROL_LABEL_STYLE),
                            dcc.Dropdown(
                                id="aggregation",
                                clearable=False,
                                value="sum",
                                disabled=True,
                                options=[
                                    {"label": "Sum", "value": "sum"},
                                    {"label": "Mean", "value": "mean"},
                                    {"label": "Minimum", "value": "min"},
                                    {"label": "Maximum", "value": "max"},
                                    {"label": "None (raw data)", "value": "none"},
                                ],
                            ),
                        ],
                        style=CONTROL_ITEM_STYLE,
                    ),
                    html.Div(
                        [
                            html.Label("Time buckets (next trace)", style=CONTROL_LABEL_STYLE),
                            dcc.Dropdown(
                                id="time-resolution",
                                clearable=False,
                                value="native",
                                disabled=True,
                                options=[
                                    {"label": "Native (per timestamp)", "value": "native"},
                                    {"label": "Hourly buckets", "value": "hour"},
                                    {"label": "Daily buckets", "value": "day"},
                                    {"label": "Weekly buckets", "value": "week"},
                                    {"label": "Monthly buckets", "value": "month"},
                                ],
                            ),
                        ],
                        style=CONTROL_ITEM_STYLE,
                    ),
                    html.Div(
                        [
                            html.Button(
                                "Add trace",
                                id="add-trace",
                                n_clicks=0,
                                disabled=True,
                                className="action-button action-button-primary",
                                style=PRIMARY_ACTION_BUTTON_STYLE,
                            ),
                        ],
                        style=TRACE_ACTION_ROW_STYLE,
                    ),
                    html.Div(
                        [
                            html.Label("Active traces", style=CONTROL_LABEL_STYLE),
                            html.Div(id="trace-list", style={"fontSize": "0.9rem", "color": "#334155"}),
                        ],
                        style={**CONTROL_ITEM_STYLE, "gridColumn": "1 / -1"},
                    ),
                    html.Div(
                        [
                            dcc.Dropdown(
                                id="remove-trace-select",
                                multi=True,
                                clearable=True,
                                placeholder="Select traces to remove",
                                style={"width": "320px"},
                                disabled=True,
                            ),
                            html.Button(
                                "Remove selected",
                                id="remove-trace",
                                n_clicks=0,
                                disabled=True,
                                className="action-button action-button-secondary",
                                style=SECONDARY_ACTION_BUTTON_STYLE,
                            ),
                        ],
                        style={**TRACE_ACTION_ROW_STYLE, "flexDirection": "row", "alignItems": "flex-end", "gap": "10px"},
                    ),
                    html.Div(
                        [
                            html.Div(
                                "Technology-level by default. Enable unit-level detail above for single-unit traces.",
                                style={**SECTION_ACTION_HINT_STYLE, "textAlign": "right", "maxWidth": "520px"},
                            ),
                            html.Button(
                                "Visualize",
                                id="visualize-data",
                                n_clicks=0,
                                disabled=True,
                                className="action-button action-button-primary",
                                style=PRIMARY_ACTION_BUTTON_STYLE,
                            ),
                        ],
                        style={**SECTION_ACTION_ROW_STYLE, "gridColumn": "1 / -1"},
                    ),
                ],
                style=CONTROL_GRID_STYLE,
                id="control-section",
            ),
            html.Div(
                [
                    dcc.Loading(
                        id="timeseries-loading",
                        type="default",
                        children=dcc.Graph(
                            id="timeseries-graph",
                            figure=empty_figure("Initializing..."),
                            style=PLOT_GRAPH_STYLE,
                            config={"displaylogo": False},
                        ),
                    ),
                    html.Div(
                        [
                            html.Label("Plot type", style=CONTROL_LABEL_STYLE),
                            dcc.Dropdown(
                                id="plot-mode",
                                clearable=False,
                                value="line",
                                disabled=True,
                                options=[
                                    {"label": "Line plot comparison", "value": "line"},
                                    {"label": "Stacked area", "value": "stacked_area"},
                                    {"label": "Duration curve", "value": "duration_curve"},
                                    {"label": "Density", "value": "density"},
                                ],
                            ),
                        ],
                        style={"padding": "6px 8px 2px 8px"},
                    ),
                    html.Div(id="plot-note", style=PLOT_NOTE_STYLE),
                ],
                style=GRAPH_CARD_STYLE,
            ),
            dcc.Store(id="aggregation-mode-store", data={"unit_detail_mode": False, "pemmdb_type_active": True}),
            dcc.Store(id="loaded-file-selection", data=[]),
            dcc.Store(
                id="readiness-store",
                data={
                    "phase": "idle",
                    "detail": "Select a run and click Load Data.",
                    "files": 0,
                    "filters_ready": False,
                    "plot_ready": False,
                },
            ),
            dcc.Store(id="trace-store", data=[]),
            dcc.Store(id="prefetch-status", data={"loading": False}),
            dcc.Interval(id="prefetch-interval", interval=500, n_intervals=0, disabled=True),
        ],
        style=APP_STYLE,
    )
