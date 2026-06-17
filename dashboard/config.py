from __future__ import annotations

import colorsys
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
SUPPORTED_EXTENSIONS = {".parquet", ".csv"}
DATETIME_FORMAT_HINT = "%Y-%m-%d %H.%M"

# Guardrails for large Antares outputs to keep UI responsive.
MAX_RAW_POINTS = 300_000
MAX_OPTION_VALUES = 500

APP_STYLE = {
    "padding": "18px clamp(14px, 2vw, 28px)",
    "fontFamily": "'Segoe UI', 'Nirmala UI', sans-serif",
    "background": "#eff3f9",
    "minHeight": "100vh",
    "color": "#1f2937",
}
CARD_STYLE = {
    "background": "#ffffff",
    "border": "none",
    "borderRadius": "14px",
    "boxShadow": "none",
}
HEADER_CARD_STYLE = {
    **CARD_STYLE,
    "padding": "14px 16px",
    "marginBottom": "12px",
}
HEADER_TITLE_STYLE = {
    "margin": "0 0 4px 0",
    "fontSize": "clamp(1.25rem, 1.8vw, 1.7rem)",
    "letterSpacing": "0.01em",
}
HEADER_SUBTITLE_STYLE = {
    "margin": "0",
    "color": "#5b6776",
    "fontSize": "0.95rem",
}
FILE_ROW_STYLE = {
    **CARD_STYLE,
    "display": "grid",
    "gridTemplateColumns": "minmax(0, 1fr) auto",
    "gap": "16px",
    "alignItems": "start",
    "padding": "12px 14px",
    "marginBottom": "10px",
}
FILE_PICKER_STYLE = {
    "border": "1px solid #d5dde8",
    "borderRadius": "10px",
    "background": "#f8fafc",
    "overflow": "hidden",
}
FILE_SUMMARY_STYLE = {
    "cursor": "pointer",
    "padding": "10px 12px",
    "fontWeight": 600,
    "fontSize": "0.92rem",
    "color": "#334155",
    "background": "#eef3f8",
}
FILE_CHECKLIST_STYLE = {
    "maxHeight": "220px",
    "overflowY": "auto",
    "padding": "10px 12px",
    "background": "#ffffff",
}
REFRESH_BUTTON_STYLE = {
    "height": "40px",
    "padding": "0 14px",
    "border": "1px solid #c7d3e0",
    "borderRadius": "10px",
    "background": "#edf2f7",
    "color": "#334155",
    "fontWeight": 600,
    "cursor": "pointer",
}
LOAD_BUTTON_STYLE = {
    **REFRESH_BUTTON_STYLE,
    "height": "44px",
    "minWidth": "188px",
    "background": "linear-gradient(135deg, #0b3c5d 0%, #0f5f86 100%)",
    "border": "1px solid #0b3c5d",
    "color": "#ffffff",
    "boxShadow": "0 10px 18px rgba(11, 60, 93, 0.18)",
}
VISUALIZE_BUTTON_STYLE = {
    **REFRESH_BUTTON_STYLE,
    "height": "44px",
    "minWidth": "188px",
    "background": "linear-gradient(135deg, #0b3c5d 0%, #14668a 100%)",
    "border": "1px solid #0b3c5d",
    "color": "#ffffff",
    "boxShadow": "0 10px 18px rgba(11, 60, 93, 0.18)",
}
AGGREGATION_STATUS_STYLE = {
    "height": "40px",
    "padding": "0 12px",
    "borderRadius": "10px",
    "fontSize": "0.85rem",
    "fontWeight": 600,
    "display": "flex",
    "alignItems": "center",
    "justifyContent": "center",
    "boxSizing": "border-box",
    "border": "1px solid transparent",
}
SECTION_ACTION_ROW_STYLE = {
    "display": "grid",
    "gridTemplateColumns": "minmax(0, 1fr) auto",
    "alignItems": "center",
    "gap": "12px",
    "marginTop": "14px",
    "paddingTop": "12px",
    "borderTop": "1px solid #e2e8f0",
}
SECTION_ACTION_HINT_STYLE = {
    "fontSize": "0.82rem",
    "lineHeight": "1.35",
    "color": "#64748b",
    "textAlign": "right",
}
STATUS_STYLE = {
    "marginBottom": "12px",
    "color": "#334155",
    "fontSize": "0.92rem",
    "background": "#f8fafc",
    "border": "1px solid #dbe4ee",
    "borderRadius": "10px",
    "padding": "8px 10px",
}
LOADING_BAR_HIDDEN_STYLE = {"display": "none"}
LOADING_BAR_VISIBLE_STYLE = {
    "display": "block",
    "marginTop": "4px",
    "marginBottom": "10px",
    "background": "#f8fafc",
    "border": "1px solid #dbe4ee",
    "borderRadius": "10px",
    "padding": "8px 10px",
}
READINESS_BANNER_STYLE = {
    "marginBottom": "10px",
    "padding": "10px 14px",
    "borderRadius": "10px",
    "border": "1px solid #dbe4ee",
    "background": "#f8fafc",
    "fontSize": "0.88rem",
    "color": "#334155",
}
READINESS_STAGE_PENDING = {"color": "#94a3b8"}
READINESS_STAGE_ACTIVE = {"color": "#0b3c5d", "fontWeight": 600}
READINESS_STAGE_DONE = {"color": "#15803d", "fontWeight": 600}
CONTROL_GRID_STYLE = {
    **CARD_STYLE,
    "display": "grid",
    "gridTemplateColumns": "repeat(auto-fit, minmax(250px, 1fr))",
    "gap": "12px",
    "padding": "12px 14px",
    "marginBottom": "10px",
}
CONTROL_ITEM_STYLE = {"minWidth": 0}
CONTROL_LABEL_STYLE = {
    "display": "block",
    "marginBottom": "5px",
    "fontWeight": 600,
    "fontSize": "0.84rem",
    "lineHeight": "1.2",
    "whiteSpace": "nowrap",
    "color": "#334155",
}
GRAPH_CARD_STYLE = {
    **CARD_STYLE,
    "padding": "6px 8px 10px 8px",
}
PLOT_GRAPH_STYLE = {"height": "70vh", "minHeight": "440px"}
PLOT_NOTE_STYLE = {
    "marginTop": "8px",
    "padding": "0 4px",
    "color": "#475569",
    "fontSize": "0.9rem",
}

TECHNOLOGY_SOURCE_COLUMN = "PEMMDB_TECHNOLOGY"
FILE_SOURCE_COLUMN = "__source_file"
FILE_SOURCE_LABEL = "File"
RUN_KEY_COLUMN = "__run_key"
UNIT_NAME_COLUMN = "Unit Name"

ACTION_BUTTON_STYLE = {
    "width": "188px",
    "height": "44px",
    "minWidth": "188px",
    "padding": "0 14px",
    "borderRadius": "10px",
    "fontWeight": 600,
    "cursor": "pointer",
    "boxSizing": "border-box",
}
SECONDARY_ACTION_BUTTON_STYLE = {
    **ACTION_BUTTON_STYLE,
    "border": "1px solid #c7d3e0",
    "background": "#edf2f7",
    "color": "#334155",
}
PRIMARY_ACTION_BUTTON_STYLE = {
    **ACTION_BUTTON_STYLE,
    "border": "1px solid #0b3c5d",
    "background": "linear-gradient(135deg, #0b3c5d 0%, #0f5f86 100%)",
    "color": "#ffffff",
    "boxShadow": "0 10px 18px rgba(11, 60, 93, 0.18)",
}
ACTION_COLUMN_STYLE = {
    "display": "flex",
    "flexDirection": "column",
    "alignItems": "flex-end",
    "gap": "8px",
    "minWidth": "188px",
}
TRACE_ACTION_ROW_STYLE = {
    "display": "flex",
    "flexDirection": "column",
    "alignItems": "flex-end",
    "gap": "8px",
    "gridColumn": "1 / -1",
    "paddingTop": "4px",
}

TECHNOLOGY_DEFINITIONS: dict[str, dict[str, Any]] = {
    "Battery": {
        "aliases": ["Battery", "Battery residential", "Battery utility scale"],
        "color": "#B22222",
    },
    "Biofuel": {
        "aliases": ["Biofuel"],
        "color": "#8B4513",
    },
    "Biomass": {
        "aliases": ["Biomass"],
        "color": "#228B22",
    },
    "Coal": {
        "aliases": [
            "Coal",
            "Hard coal/New",
            "Hard coal/Old 1",
            "Hard coal/Old 2",
            "Lignite/New",
            "Lignite/Old 1",
            "Lignite/Old 2",
            "OtherNon-RES/Hard coal/Old 1",
            "OtherNon-RES/Lignite/Old 1",
        ],
        "color": "#2F4F4F",
    },
    "Fuel_Cell": {
        "aliases": ["Fuel Cell"],
        "color": "#777777",
    },
    "Gas": {
        "aliases": [
            "Gas",
            "Gas/CCGT new",
            "Gas/CCGT old 1",
            "Gas/CCGT old 2",
            "Gas/CCGT present 1",
            "Gas/CCGT present 2",
            "Gas/Conventional old 1",
            "Gas/Conventional old 2",
            "Gas/OCGT new",
            "Gas/OCGT old",
            "OtherNon-RES/Gas/CCGT CCS",
            "OtherNon-RES/Gas/CCGT old 1",
            "OtherNon-RES/Gas/CCGT old 2",
            "OtherNon-RES/Gas/CCGT present 2",
            "OtherNon-RES/Gas/Conventional old 1",
            "OtherNon-RES/Gas/Conventional old 2",
            "OtherNon-RES/Gas/OCGT old",
        ],
        "color": "#FF8C00",
    },
    "Nuclear": {
        "aliases": ["Nuclear"],
        "color": "#9ACD32",
    },
    "Oil": {
        "aliases": ["Oil", "Heavy oil/Old 1", "Heavy oil/Old 2", "Light oil", "Shale oil/New"],
        "color": "#4B0082",
    },
    "Other": {
        "aliases": ["Other"],
        "color": "#A9A9A9",
    },
    "Other_Non_RES": {
        "aliases": ["Other Non RES", "OtherNon-RES"],
        "color": "#A9A9A9",
    },
    "Other_RES": {
        "aliases": ["Other RES", "other res 1"],
        "color": "#A9A9A9",
    },
    "P2G": {
        "aliases": ["P2G"],
        "color": "#777777",
    },
    "PSP": {
        "aliases": ["PSP", "Closed loop pumping", "Open loop pumping"],
        "color": "#4169E1",
    },
    "PV": {
        "aliases": ["PV", "Solar pv", "Solar rooftop", "Solar thermal"],
        "color": "#FFD700",
    },
    "RoR": {
        "aliases": ["RoR", "Run of river", "Reservoir", "Pondage"],
        "color": "#00BFFF",
    },
    "Storage": {
        "aliases": ["Storage"],
        "color": "#4682B4",
    },
    "Wind": {
        "aliases": ["Wind", "Wind onshore", "Wind offshore"],
        "color": "#1E90FF",
    },
    "battery_load": {
        "aliases": ["battery load"],
        "color": "#B22222",
    },
    "hydrogen": {
        "aliases": ["hydrogen"],
        "color": "#777777",
    },
    "implicit_dsr": {
        "aliases": ["implicit_dsr", "Demand shifting"],
        "color": "#555555",
    },
    "pumpload_CL": {
        "aliases": ["pumpload_CL"],
        "color": "#6495ED",
    },
    "pumpload_OL": {
        "aliases": ["pumpload_OL"],
        "color": "#6495ED",
    },
}


def normalize_technology_name(value: Any) -> str:
    text = str(value).strip().lower()
    for old, new in (("_", " "), ("-", " "), ("/", " ")):
        text = text.replace(old, new)
    return " ".join(text.split())


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    raw = color.strip().lstrip("#")
    if len(raw) != 6:
        return (127, 127, 127)
    return (int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16))


def _rgb_to_hex(red: int, green: int, blue: int) -> str:
    r = max(0, min(255, red))
    g = max(0, min(255, green))
    b = max(0, min(255, blue))
    return f"#{r:02X}{g:02X}{b:02X}"


def _shift_color_lightness(color: str, offset: float) -> str:
    red, green, blue = _hex_to_rgb(color)
    hue, lightness, saturation = colorsys.rgb_to_hls(red / 255.0, green / 255.0, blue / 255.0)
    adjusted_lightness = max(0.20, min(0.85, lightness + offset))
    out_red, out_green, out_blue = colorsys.hls_to_rgb(hue, adjusted_lightness, saturation)
    return _rgb_to_hex(
        int(round(out_red * 255)),
        int(round(out_green * 255)),
        int(round(out_blue * 255)),
    )


def _alias_offsets(count: int) -> list[float]:
    if count <= 1:
        return [0.0]

    offsets: list[float] = [0.0]
    step = 0.025
    level = 1
    while len(offsets) < count:
        offsets.append(step * level)
        if len(offsets) < count:
            offsets.append(-step * level)
        level += 1
    return offsets[:count]


def _alias_jitter(alias_key: str) -> float:
    signature = sum((index + 1) * ord(char) for index, char in enumerate(alias_key))
    return ((signature % 37) - 18) * 0.0014


def _build_technology_alias_map() -> dict[str, str]:
    alias_map: dict[str, str] = {}
    for cluster, config in TECHNOLOGY_DEFINITIONS.items():
        names = [cluster] + list(config.get("aliases", []))
        for name in names:
            alias_map[normalize_technology_name(name)] = cluster
    return alias_map


def _build_technology_alias_color_map() -> dict[str, str]:
    alias_color_map: dict[str, str] = {}
    for cluster, config in TECHNOLOGY_DEFINITIONS.items():
        base_color = str(config.get("color", "#808080"))
        names = [cluster] + list(config.get("aliases", []))
        offsets = _alias_offsets(len(names))
        for name, base_offset in zip(names, offsets):
            alias_key = normalize_technology_name(name)
            subtle_offset = max(-0.14, min(0.14, base_offset + _alias_jitter(alias_key)))
            alias_color_map[alias_key] = _shift_color_lightness(base_color, subtle_offset)
    return alias_color_map


TECHNOLOGY_ALIAS_MAP = _build_technology_alias_map()
TECHNOLOGY_COLOR_MAP = {cluster: config["color"] for cluster, config in TECHNOLOGY_DEFINITIONS.items()}
TECHNOLOGY_ALIAS_COLOR_MAP = _build_technology_alias_color_map()
