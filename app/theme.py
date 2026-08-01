"""Shared visual theme for the dashboard.

Colors mirror the Bootswatch "brite" theme in ``assets/bootstrap.css`` so Plotly
figures blend seamlessly with the Bootstrap UI. Use :func:`base_layout` (or
:func:`make_figure`) for every chart to keep styling consistent.
"""

from __future__ import annotations

from typing import Any

import plotly.graph_objects as go

FONT_FAMILY = (
    'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", '
    '"Noto Sans", "Liberation Sans", Arial, sans-serif'
)

# Brite palette (from assets/bootstrap.css :root variables).
COLORS = {
    "primary": "#a2e436",
    "blue": "#61bcff",
    "indigo": "#828df9",
    "purple": "#be82fa",
    "pink": "#ea4998",
    "red": "#f56565",
    "orange": "#fa984a",
    "yellow": "#ffc700",
    "green": "#68d391",
    "teal": "#2ed3be",
    "cyan": "#22d2ed",
    "gray": "#868e96",
    "grid": "#e9ecef",
    "text": "#212529",
    "muted": "rgba(33, 37, 41, 0.6)",
}

# Per-discipline colors, reused across every chart and card.
SPORT_COLORS = {
    "run": COLORS["orange"],
    "bike": COLORS["blue"],
    "swim": COLORS["cyan"],
}

# Training-load series colors. Kept distinct from the blue<->orange TSB
# diverging scale so the fitness/fatigue lines never blend into the form bars.
LOAD_COLORS = {
    "ctl": COLORS["green"],
    "atl": COLORS["purple"],
    "tsb": COLORS["purple"],
}

# Default ordering for categorical color cycling.
COLORWAY = [
    COLORS["primary"],
    COLORS["blue"],
    COLORS["orange"],
    COLORS["purple"],
    COLORS["cyan"],
    COLORS["pink"],
    COLORS["green"],
    COLORS["yellow"],
]


def _axis() -> dict[str, Any]:
    return {
        "gridcolor": COLORS["grid"],
        "zerolinecolor": COLORS["grid"],
        "linecolor": COLORS["grid"],
        "tickfont": {"color": COLORS["muted"]},
        "title": {"font": {"color": COLORS["muted"]}},
        "fixedrange": True,
    }


def base_layout(
    title: str | None = None,
    height: int | None = None,
    hovermode: str | bool = "x unified",
    **overrides: Any,
) -> dict[str, Any]:
    """Return a Plotly layout dict styled to match the brite theme."""
    layout: dict[str, Any] = {
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "font": {"family": FONT_FAMILY, "color": COLORS["text"], "size": 13},
        "colorway": COLORWAY,
        "margin": {"l": 55, "r": 20, "t": 50 if title else 20, "b": 45},
        "hovermode": hovermode,
        "dragmode": False,
        "legend": {
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1,
            "font": {"color": COLORS["text"]},
        },
        "xaxis": _axis(),
        "yaxis": _axis(),
    }
    if title:
        layout["title"] = {
            "text": title,
            "x": 0.01,
            "xanchor": "left",
            "font": {"size": 16, "color": COLORS["text"]},
        }
    if height:
        layout["height"] = height
    layout.update(overrides)
    return layout


def make_figure(traces: list[Any], title: str | None = None, height: int | None = None, **overrides: Any) -> go.Figure:
    """Build a themed ``go.Figure`` from traces."""
    return go.Figure(data=traces, layout=base_layout(title=title, height=height, **overrides))


def total_hover_trace(x: list[Any], totals: list[float], number_format: str = "%{y:.0f}") -> go.Scatter:
    """An invisible trace that adds a "Total" row to a unified (x) hover tooltip.

    Positioned at the top of a stacked bar so the marker is hidden but the value
    shows in the shared tooltip alongside the individual sport traces.
    """
    return go.Scatter(
        name="Total",
        x=x,
        y=totals,
        mode="markers",
        marker={"color": "rgba(0,0,0,0)", "size": 0.1},
        hovertemplate=f"{number_format}<extra>Total</extra>",
        showlegend=False,
    )
