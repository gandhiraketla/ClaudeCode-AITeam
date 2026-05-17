"""
chart_engine.py — Chart specification selection and Plotly figure rendering.

Applies rule-based heuristics to column profiles to select chart types,
then builds Plotly Figure objects ready for Streamlit rendering.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

logger = logging.getLogger(__name__)

# Maximum unique values for a categorical column to be eligible for a pie chart
PIE_MAX_NUNIQUE = 6
# Maximum unique values for a categorical column to be used as a bar chart x-axis
BAR_MAX_NUNIQUE = 50
# Minimum data rows required to attempt chart rendering
MIN_ROWS_FOR_CHART = 2


def select_chart_specs(column_profiles: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Apply deterministic heuristics to column profiles to produce chart specifications.

    Rules (applied in order, first match wins per column pair):
      - date + numeric  -> line chart
      - categorical (nunique <= BAR_MAX_NUNIQUE) + numeric -> bar chart
      - categorical (nunique <= PIE_MAX_NUNIQUE) -> pie chart (standalone)

    Returns a dict with keys:
        chart_specs: list[dict]  — each spec has chart_type, x_column, y_column, title
        count: int               — number of specs produced
    """
    numeric_cols = [p for p in column_profiles if p["inferred_type"] == "numeric"]
    date_cols = [p for p in column_profiles if p["inferred_type"] == "date"]
    categorical_cols = [p for p in column_profiles if p["inferred_type"] == "categorical"]

    specs: list[dict[str, Any]] = []
    used_pairs: set[tuple[str, str]] = set()

    # Rule 1: date + numeric -> line chart
    for date_col in date_cols:
        for num_col in numeric_cols:
            pair = (date_col["name"], num_col["name"])
            if pair not in used_pairs:
                specs.append({
                    "chart_type": "line",
                    "x_column": date_col["name"],
                    "y_column": num_col["name"],
                    "title": f"{num_col['name']} Over Time",
                })
                used_pairs.add(pair)
                if len(specs) >= 6:
                    break
        if len(specs) >= 6:
            break

    # Rule 2: categorical + numeric -> bar chart
    for cat_col in categorical_cols:
        if cat_col["nunique"] > BAR_MAX_NUNIQUE:
            continue
        for num_col in numeric_cols:
            pair = (cat_col["name"], num_col["name"])
            if pair not in used_pairs:
                specs.append({
                    "chart_type": "bar",
                    "x_column": cat_col["name"],
                    "y_column": num_col["name"],
                    "title": f"{num_col['name']} by {cat_col['name']}",
                })
                used_pairs.add(pair)
                if len(specs) >= 6:
                    break
        if len(specs) >= 6:
            break

    # Rule 3: low-cardinality categorical -> pie chart (first numeric as values, or count)
    for cat_col in categorical_cols:
        if cat_col["nunique"] > PIE_MAX_NUNIQUE or cat_col["nunique"] < 2:
            continue
        # Only add pie if not already covered by a bar chart for this column
        already_bar = any(
            s["chart_type"] == "bar" and s["x_column"] == cat_col["name"]
            for s in specs
        )
        if already_bar:
            continue
        y_col = numeric_cols[0]["name"] if numeric_cols else None
        specs.append({
            "chart_type": "pie",
            "x_column": cat_col["name"],
            "y_column": y_col,
            "title": f"Distribution of {cat_col['name']}",
        })
        if len(specs) >= 6:
            break

    logger.info(
        "Chart spec selection: %d specs produced (%d line, %d bar, %d pie)",
        len(specs),
        sum(1 for s in specs if s["chart_type"] == "line"),
        sum(1 for s in specs if s["chart_type"] == "bar"),
        sum(1 for s in specs if s["chart_type"] == "pie"),
    )

    return {"chart_specs": specs, "count": len(specs)}


def render_charts(
    chart_specs: list[dict[str, Any]],
    dataframe: pd.DataFrame,
) -> dict[str, Any]:
    """
    Build Plotly Figure objects from chart_specs and the parsed DataFrame.

    Returns a dict with keys:
        figures: list[dict]  — each entry has 'figure' (go.Figure), 'title', 'chart_type'
        errors:  list[dict]  — each entry has 'spec' and 'reason' for failed renders
    """
    if dataframe is None or len(dataframe) < MIN_ROWS_FOR_CHART:
        return {
            "figures": [],
            "errors": [{"spec": None, "reason": "DataFrame has insufficient rows for charting."}],
        }

    figures: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for spec in chart_specs:
        try:
            fig = _build_figure(spec, dataframe)
            if fig is not None:
                figures.append({
                    "figure": fig,
                    "title": spec["title"],
                    "chart_type": spec["chart_type"],
                })
        except Exception as exc:
            logger.warning("Chart render failed for spec %s: %s", spec, exc)
            errors.append({"spec": spec, "reason": str(exc)})

    logger.info(
        "Chart rendering complete: %d rendered, %d failed", len(figures), len(errors)
    )
    return {"figures": figures, "errors": errors}


def _build_figure(spec: dict[str, Any], df: pd.DataFrame) -> go.Figure | None:
    """
    Build a single Plotly figure from a chart spec and DataFrame.
    Returns None if the required columns are missing or all-null.
    """
    chart_type = spec["chart_type"]
    x_col = spec["x_column"]
    y_col = spec.get("y_column")

    # Validate required columns exist
    if x_col not in df.columns:
        raise ValueError(f"Column '{x_col}' not found in DataFrame.")
    if y_col and y_col not in df.columns:
        raise ValueError(f"Column '{y_col}' not found in DataFrame.")

    # Guard: x column must have non-null values
    if df[x_col].dropna().empty:
        raise ValueError(f"Column '{x_col}' contains only null values.")

    if chart_type == "line":
        return _build_line_chart(spec, df, x_col, y_col)
    elif chart_type == "bar":
        return _build_bar_chart(spec, df, x_col, y_col)
    elif chart_type == "pie":
        return _build_pie_chart(spec, df, x_col, y_col)
    else:
        raise ValueError(f"Unknown chart_type '{chart_type}'.")


def _build_line_chart(
    spec: dict[str, Any], df: pd.DataFrame, x_col: str, y_col: str
) -> go.Figure:
    """Build a line chart with date on x-axis and numeric on y-axis."""
    plot_df = df[[x_col, y_col]].dropna().copy()
    if plot_df.empty:
        raise ValueError(f"No valid rows after dropping nulls for '{x_col}' and '{y_col}'.")

    # Parse dates for correct ordering
    plot_df[x_col] = pd.to_datetime(plot_df[x_col], errors="coerce")
    plot_df = plot_df.dropna(subset=[x_col]).sort_values(x_col)

    if plot_df.empty:
        raise ValueError(f"No parseable dates in column '{x_col}'.")

    fig = px.line(
        plot_df,
        x=x_col,
        y=y_col,
        title=spec["title"],
        labels={x_col: x_col, y_col: y_col},
    )
    fig.update_layout(title_font_size=14, margin={"t": 50, "b": 40, "l": 40, "r": 20})
    return fig


def _build_bar_chart(
    spec: dict[str, Any], df: pd.DataFrame, x_col: str, y_col: str
) -> go.Figure:
    """Build a bar chart aggregating y_col sum grouped by x_col."""
    plot_df = df[[x_col, y_col]].dropna().copy()
    if plot_df.empty:
        raise ValueError(f"No valid rows after dropping nulls for '{x_col}' and '{y_col}'.")

    # Aggregate: sum of numeric per category, sorted descending
    agg = (
        plot_df.groupby(x_col, as_index=False)[y_col]
        .sum()
        .sort_values(y_col, ascending=False)
        .head(BAR_MAX_NUNIQUE)
    )

    fig = px.bar(
        agg,
        x=x_col,
        y=y_col,
        title=spec["title"],
        labels={x_col: x_col, y_col: y_col},
    )
    fig.update_layout(title_font_size=14, margin={"t": 50, "b": 40, "l": 40, "r": 20})
    return fig


def _build_pie_chart(
    spec: dict[str, Any], df: pd.DataFrame, x_col: str, y_col: str | None
) -> go.Figure:
    """Build a pie chart. Uses y_col sum as values, or category count if y_col is None."""
    if y_col:
        plot_df = df[[x_col, y_col]].dropna().copy()
        if plot_df.empty:
            raise ValueError(f"No valid rows after dropping nulls for '{x_col}' and '{y_col}'.")
        agg = plot_df.groupby(x_col, as_index=False)[y_col].sum()
        values_col = y_col
    else:
        agg = df[x_col].dropna().value_counts().reset_index()
        agg.columns = [x_col, "count"]
        values_col = "count"

    if agg.empty:
        raise ValueError(f"No data to render pie chart for '{x_col}'.")

    fig = px.pie(
        agg,
        names=x_col,
        values=values_col,
        title=spec["title"],
    )
    fig.update_layout(title_font_size=14, margin={"t": 50, "b": 20, "l": 20, "r": 20})
    return fig