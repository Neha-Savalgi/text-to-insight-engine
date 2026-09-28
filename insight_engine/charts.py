"""Turn a query result plus Claude's chart suggestion into a Plotly figure."""

import plotly.express as px


def _numeric_columns(df):
    return [c for c, t in zip(df.columns, df.dtypes) if t.is_numeric()]


def build_figure(df, spec, title=""):
    """Return a Plotly figure, or None when a table or single number fits better."""
    if df is None or df.height == 0:
        return None
    spec = spec or {}
    chart_type = spec.get("type", "table")
    if chart_type in ("table", "metric") or df.width < 2:
        return None

    x, y, color = spec.get("x"), spec.get("y"), spec.get("color")
    # If Claude named a column that is not in the result, fall back to sensible defaults.
    if x not in df.columns:
        x = df.columns[0]
    if y not in df.columns:
        numeric = [c for c in _numeric_columns(df) if c != x]
        if not numeric:
            return None
        y = numeric[0]
    if color not in df.columns:
        color = None

    pdf = df.to_pandas()
    if chart_type == "line":
        fig = px.line(pdf, x=x, y=y, color=color, markers=True)
    elif chart_type == "scatter":
        fig = px.scatter(pdf, x=x, y=y, color=color)
    elif chart_type == "pie":
        fig = px.pie(pdf, names=x, values=y)
    else:
        fig = px.bar(pdf, x=x, y=y, color=color)
    fig.update_layout(title=title, margin=dict(l=10, r=10, t=50, b=10))
    return fig


def single_value(df):
    """If the result is one row and one column, return that value (for a metric card)."""
    if df is not None and df.height == 1 and df.width == 1:
        return df.item()
    return None
