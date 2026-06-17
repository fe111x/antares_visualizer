from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.express as px

from .config import (
    TECHNOLOGY_ALIAS_COLOR_MAP,
    FILE_SOURCE_COLUMN,
    FILE_SOURCE_LABEL,
    TECHNOLOGY_ALIAS_MAP,
    TECHNOLOGY_COLOR_MAP,
    TECHNOLOGY_SOURCE_COLUMN,
    normalize_technology_name,
)


def empty_figure(message: str) -> px.line:
    fig = px.line(template="plotly_white")
    fig.update_layout(
        xaxis={"visible": False},
        yaxis={"visible": False},
        annotations=[
            {
                "text": message,
                "xref": "paper",
                "yref": "paper",
                "x": 0.5,
                "y": 0.5,
                "showarrow": False,
                "font": {"size": 14},
            }
        ],
        margin={"l": 30, "r": 20, "t": 40, "b": 30},
    )
    return fig


def display_group_column(column: str) -> str:
    if column == FILE_SOURCE_COLUMN:
        return FILE_SOURCE_LABEL
    if column == "__dispatch_component":
        return "Dispatch"
    return column


def build_series_label(df: pd.DataFrame, group_columns: list[str]) -> pd.Series:
    if not group_columns:
        return pd.Series(["Gesamt"] * len(df), index=df.index, dtype="object")

    if len(group_columns) == 1:
        column = group_columns[0]
        values = df[column].astype("object")
        values = values.where(values.notna(), "NA").astype(str)
        # Always include the column name as prefix for clarity.
        prefix = f"{display_group_column(column)}="
        return prefix + values

    labels = pd.Series([""] * len(df), index=df.index, dtype="object")
    for index, column in enumerate(group_columns):
        values = df[column].astype("object")
        values = values.where(values.notna(), "NA").astype(str)
        prefix = f"{display_group_column(column)}="
        labels = prefix + values if index == 0 else labels + " | " + prefix + values
    return labels


def build_series_order(series: pd.Series) -> list[str]:
    unique_series = pd.Series(series.dropna().astype(str).unique())
    return sorted(unique_series.tolist(), key=lambda label: label.casefold())


def build_duration_curve_frame(plot_df: pd.DataFrame, value_column: str) -> pd.DataFrame:
    duration_df = plot_df[["__series", value_column]].copy()
    duration_df[value_column] = pd.to_numeric(duration_df[value_column], errors="coerce")
    duration_df = duration_df[duration_df[value_column].notna()].copy()
    if duration_df.empty:
        return duration_df

    # Stable sorting keeps equal values in deterministic order.
    duration_df = duration_df.sort_values(["__series", value_column], ascending=[True, False], kind="mergesort")
    duration_df["__rank"] = duration_df.groupby("__series", sort=False).cumcount() + 1
    series_lengths = duration_df.groupby("__series", sort=False)["__rank"].transform("max")
    duration_df["__duration_percent"] = duration_df["__rank"] / series_lengths * 100.0

    return duration_df


def build_series_color_map(plot_df: pd.DataFrame, group_columns: list[str]) -> dict[str, str] | None:
    """Build a color map for series based on technology (if available) or auto-generate for other dimensions."""
    if "__series" not in plot_df.columns:
        return None

    # Try technology-based coloring first (if PEMMDB_TECHNOLOGY is in group_columns).
    if TECHNOLOGY_SOURCE_COLUMN in group_columns and TECHNOLOGY_SOURCE_COLUMN in plot_df.columns:
        mapper_df = pd.DataFrame(
            {
                "__series": plot_df["__series"].astype(str),
                "__tech": plot_df[TECHNOLOGY_SOURCE_COLUMN],
            }
        )
        per_series = mapper_df.groupby("__series", observed=True)["__tech"].first()

        color_map: dict[str, str] = {}
        for series_name, raw_tech in per_series.items():
            alias_key = normalize_technology_name(raw_tech)
            color = TECHNOLOGY_ALIAS_COLOR_MAP.get(alias_key)
            if color is None:
                cluster = TECHNOLOGY_ALIAS_MAP.get(alias_key)
                color = TECHNOLOGY_COLOR_MAP.get(cluster) if cluster else None
            if color:
                color_map[series_name] = color

        return color_map or None

    # If no technology-based coloring, generate auto colors for all series.
    # Use a predefined palette of distinct colors.
    palette = [
        "#1f77b4",  # Blue
        "#ff7f0e",  # Orange
        "#2ca02c",  # Green
        "#d62728",  # Red
        "#9467bd",  # Purple
        "#8c564b",  # Brown
        "#e377c2",  # Pink
        "#7f7f7f",  # Gray
        "#bcbd22",  # Yellow-green
        "#17becf",  # Cyan
    ]

    unique_series = sorted(plot_df["__series"].astype(str).unique())
    color_map = {}
    for i, series_name in enumerate(unique_series):
        color_map[series_name] = palette[i % len(palette)]

    return color_map or None
