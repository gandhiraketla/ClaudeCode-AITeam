import logging
from typing import Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

logger = logging.getLogger(__name__)


def select_chart_specs(column_profiles: list) -> dict:
    """
    Apply deterministic heuristics to column profiles to produce chart specs.
    Returns: {chart_specs: list, count: int}
    """
    date_cols = [p for p in column_profiles if p["inferred_type"] == "date"]
    numeric_cols = [p for p in column_profiles if p["inferred_type"] == "numeric"]
    categorical_cols = [p for p in column_profiles if p["inferred_type"] == "categorical"]

    specs = []
    used_pairs = set()

    # Rule 1: date + numeric -> line chart
    for dc in date_cols[:2]:
        for nc in numeric_cols[:3]:
            key = (dc["name"], nc["name"])
            if key not in used_pairs:
                specs.append({
                    "chart_type": "line",
                    "x_column": dc["name"],
                    "y_column": nc["name"],
                    "title": f"{nc['name']} over {dc['name']}"
                })
                used_pairs.add(key)

    # Rule 2: categorical + numeric -> bar chart
    for cc in categorical_cols[:2]:
        for nc in numeric_cols[:2]:
            key = (cc["name"], nc["name"])
            if key not in used_pairs and len(specs) < 8:
                specs.append({
                    "chart_type": "bar",
                    "x_column": cc["name"],
                    "y_column": nc["name"],
                    "title": f"{nc['name']} by {cc['name']}"
                })
                used_pairs.add(key)

    # Rule 3: categorical with nunique <= 6 -> pie chart (use first numeric as values)
    for cc in categorical_cols:
        if cc["nunique"] <= 6 and numeric_cols and len(specs) < 8:
            nc = numeric_cols[0]
            key = ("pie", cc["name"], nc["name"])
            if key not in used_pairs:
                specs.append({
                    "chart_type": "pie",
                    "x_column": cc["name"],
                    "y_column": nc["name"],
                    "title": f"{nc['name']} share by {cc['name']}"
                })
                used_pairs.add(key)

    # Fallback: if fewer than 2 specs, add numeric histograms
    if len(specs) < 2:
        for nc in numeric_cols:
            if len(specs) >= 2:
                break
            key = ("hist", nc["name"])
            if key not in used_pairs:
                specs.append({
                    "chart_type": "bar",
                    "x_column": nc["name"],
                    "y_column": None,
                    "title": f"Distribution of {nc['name']}"
                })
                used_pairs.add(key)

    return {"chart_specs": specs[:6], "count": min(len(specs), 6)}


def render_charts(chart_specs: list, dataframe: pd.DataFrame) -> dict:
    """
    Build Plotly figures from chart_specs and DataFrame.
    Returns: {figures: list of dicts with fig+metadata, errors: list}
    """
    figures = []
    errors = []

    for spec in chart_specs:
        try:
            fig = _build_figure(spec, dataframe)
            if fig is not None:
                figures.append({
                    "fig": fig,
                    "title": spec["title"],
                    "chart_type": spec["chart_type"]
                })
        except Exception as e:
            logger.warning("Failed to render chart '%s': %s", spec.get("title", "unknown"), e)
            errors.append({"spec": spec, "reason": str(e)})

    return {"figures": figures, "errors": errors}


def _build_figure(spec: dict, df: pd.DataFrame) -> Optional[go.Figure]:
    chart_type = spec["chart_type"]
    x_col = spec["x_column"]
    y_col = spec.get("y_column")
    title = spec["title"]

    if x_col not in df.columns:
        raise ValueError(f"Column '{x_col}' not found in DataFrame")
    if y_col and y_col not in df.columns:
        raise ValueError(f"Column '{y_col}' not found in DataFrame")

    if chart_type == "line":
        if y_col is None:
            raise ValueError("line chart requires y_column")
        plot_df = df[[x_col, y_col]].dropna().sort_values(x_col)
        if plot_df.empty:
            raise ValueError(f"No non-null data for line chart: {x_col}, {y_col}")
        fig = px.line(plot_df, x=x_col, y=y_col, title=title)

    elif chart_type == "bar":
        if y_col is not None:
            agg = df.groupby(x_col)[y_col].sum().reset_index().sort_values(y_col, ascending=False).head(20)
            if agg.empty:
                raise ValueError(f"No data for bar chart: {x_col}, {y_col}")
            fig = px.bar(agg, x=x_col, y=y_col, title=title)
        else:
            # Histogram / distribution
            plot_df = df[[x_col]].dropna()
            if plot_df.empty:
                raise ValueError(f"No non-null data for histogram: {x_col}")
            fig = px.histogram(plot_df, x=x_col, title=title)

    elif chart_type == "pie":
        if y_col is None:
            raise ValueError("pie chart requires y_column")
        agg = df.groupby(x_col)[y_col].sum().reset_index()
        agg = agg[agg[y_col] > 0]
        if agg.empty:
            raise ValueError(f"No positive values for pie chart: {x_col}, {y_col}")
        fig = px.pie(agg, names=x_col, values=y_col, title=title)

    else:
        raise ValueError(f"Unknown chart type: {chart_type}")

    fig.update_layout(margin=dict(t=50, b=30, l=30, r=30))
    return fig
