"""Overview page: current fitness/fatigue/form and recent weekly load."""

from __future__ import annotations

import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import Input, Output, callback, dcc, html
from sqlalchemy.engine import Engine

from app.components import (
    DEFAULT_RANGE_WEEKS,
    RANGE_OPTIONS,
    STATIC_GRAPH_CONFIG,
    section_card,
    slice_weeks,
)
from app.data import get_engine, get_weekly_training
from app.theme import COLORS, LOAD_COLORS, SPORT_COLORS, make_figure, total_hover_trace


FORM_ZONES = [
    {"label": "Freshness", "range": "+5 to +25", "color": COLORS["blue"]},
    {"label": "Grey Zone", "range": "-10 to +5", "color": COLORS["gray"]},
    {"label": "Optimal Training", "range": "-30 to -10", "color": COLORS["orange"]},
    {"label": "High Risk", "range": "Below -30", "color": COLORS["red"]},
]


def _form_zone(tsb: float) -> dict:
    if tsb >= 5:
        return FORM_ZONES[0]
    if tsb >= -10:
        return FORM_ZONES[1]
    if tsb >= -30:
        return FORM_ZONES[2]
    return FORM_ZONES[3]


def _rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


def _weekly_tss_figure(weeks: list[dict]) -> go.Figure:
    weeks_labels = [w["week_start"] for w in weeks]
    traces = [
        go.Bar(name="Run", x=weeks_labels, y=[w["run_tss"] or 0 for w in weeks], marker_color=SPORT_COLORS["run"]),
        go.Bar(name="Bike", x=weeks_labels, y=[w["bike_tss"] or 0 for w in weeks], marker_color=SPORT_COLORS["bike"]),
        go.Bar(name="Swim", x=weeks_labels, y=[w["swim_tss"] or 0 for w in weeks], marker_color=SPORT_COLORS["swim"]),
        total_hover_trace(
            weeks_labels,
            [(w["run_tss"] or 0) + (w["bike_tss"] or 0) + (w["swim_tss"] or 0) for w in weeks],
            "%{y:.0f}",
        ),
    ]
    fig = make_figure(traces, height=340)
    fig.update_layout(barmode="stack", yaxis_title="TSS", xaxis_title="Week")
    return fig


def _weekly_hours_figure(weeks: list[dict]) -> go.Figure:
    weeks_labels = [w["week_start"] for w in weeks]
    traces = [
        go.Bar(name="Run", x=weeks_labels, y=[w["run_hours"] or 0 for w in weeks], marker_color=SPORT_COLORS["run"]),
        go.Bar(name="Bike", x=weeks_labels, y=[w["bike_hours"] or 0 for w in weeks], marker_color=SPORT_COLORS["bike"]),
        go.Bar(name="Swim", x=weeks_labels, y=[w["swim_hours"] or 0 for w in weeks], marker_color=SPORT_COLORS["swim"]),
        total_hover_trace(
            weeks_labels,
            [(w["run_hours"] or 0) + (w["bike_hours"] or 0) + (w["swim_hours"] or 0) for w in weeks],
            "%{y:.1f}",
        ),
    ]
    fig = make_figure(traces, height=340)
    fig.update_layout(barmode="stack", yaxis_title="Hours", xaxis_title="Week")
    return fig


def _weekly_tss_per_hour_figure(weeks: list[dict]) -> go.Figure:
    labels = [w["week_start"] for w in weeks]
    values = [
        (w["total_tss"] / w["total_hours"]) if (w.get("total_tss") and w.get("total_hours")) else 0
        for w in weeks
    ]
    traces = [
        go.Bar(
            name="TSS/hr", x=labels, y=values,
            marker_color="#8f84b3", marker_line_width=0,
            hovertemplate="%{y:.1f}<extra>TSS/hr</extra>",
        )
    ]
    fig = make_figure(traces, height=360, hovermode="x")
    fig.update_layout(yaxis_title="TSS / hr", xaxis_title="Week", showlegend=False)
    # Zoom the y-axis to the data band so week-to-week variation is legible
    # instead of being flattened against a 0 baseline.
    nonzero = [v for v in values if v]
    if nonzero:
        lo, hi = min(nonzero), max(nonzero)
        pad = max((hi - lo) * 0.4, hi * 0.01, 0.5)
        fig.update_yaxes(range=[lo - pad, hi + pad])
    return fig


def _tsb_color(v: float) -> str:
    return _form_zone(v)["color"]


def _load_form_figure(weeks: list[dict]) -> go.Figure:
    """Fitness/Fatigue lines (left Load axis) overlaid on Form bars (right TSB
    axis). The right axis is symmetric so TSB=0 sits at the vertical center."""
    labels = [w["week_start"] for w in weeks]
    ctl = [w["ctl"] or 0 for w in weeks]
    atl = [w["atl"] or 0 for w in weeks]
    tsb = [w["tsb"] or 0 for w in weeks]

    tsb_bars = go.Bar(
        name="TSB (Form)", x=labels, y=tsb,
        marker_color=[_tsb_color(v) for v in tsb], marker_line_width=0,
        yaxis="y2",
    )
    ctl_line = go.Scatter(
        name="CTL (Fitness)", x=labels, y=ctl, mode="lines+markers",
        line={"color": LOAD_COLORS["ctl"], "width": 3},
    )
    atl_line = go.Scatter(
        name="ATL (Fatigue)", x=labels, y=atl, mode="lines+markers",
        line={"color": LOAD_COLORS["atl"], "width": 2, "dash": "dot"},
    )

    # Bars added first so the fitness/fatigue lines render on top of them.
    fig = make_figure([tsb_bars, ctl_line, atl_line], height=360)
    m = (max((abs(v) for v in tsb), default=10) or 10) * 1.15
    fig.update_layout(
        yaxis_title="Load",
        xaxis_title="Week",
        margin={"l": 55, "r": 55, "t": 20, "b": 45},
        yaxis2={
            "title": {"text": "TSB (Form)", "font": {"color": COLORS["muted"]}},
            "overlaying": "y",
            "side": "right",
            "range": [-m, m],
            "zeroline": True,
            "zerolinecolor": COLORS["grid"],
            "showgrid": False,
            "fixedrange": True,
            "tickfont": {"color": COLORS["muted"]},
        },
    )
    return fig


def _sparkline(values: list[float], color: str) -> go.Figure:
    fig = go.Figure(
        go.Scatter(
            x=list(range(len(values))),
            y=values,
            mode="lines",
            line={"color": color, "width": 2, "shape": "spline"},
            fill="tozeroy",
            fillcolor=_rgba(color, 0.12),
            hoverinfo="skip",
        )
    )
    fig.update_layout(
        height=44,
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        xaxis={"visible": False, "fixedrange": True},
        yaxis={"visible": False, "fixedrange": True},
    )
    return fig


def _delta(cur: float, prev: float | None, pct: bool = False):
    if prev is None:
        return None, None
    diff = cur - prev
    if pct:
        if not prev:
            return None, None
        text = f"{abs(diff / prev * 100):.0f}%"
    else:
        text = f"{abs(diff):.0f}"
    return diff >= 0, text


def _delta_span(up, text):
    if up is None:
        return None
    arrow = "\u2191" if up else "\u2193"
    cls = "kpi-delta up" if up else "kpi-delta down"
    return html.Span(f"{arrow} {text}", className=cls)


def _metric_card(title, value, subtitle, accent, series, delta, info=None, info_id=None):
    up, text = delta
    if info:
        header = html.Div(
            [
                html.Span(title, className="kpi-title"),
                html.Span("\u24d8", id=info_id, className="kpi-info"),
            ],
            className="kpi-header",
        )
    else:
        header = html.Div(title, className="kpi-title")
    body = [
        header,
        html.Div(
            [html.Span(value, className="kpi-value"), _delta_span(up, text)],
            className="kpi-value-row",
        ),
        dcc.Graph(figure=_sparkline(series, accent), config=STATIC_GRAPH_CONFIG, className="kpi-spark"),
        html.Div(subtitle, className="kpi-subtitle"),
    ]
    if info:
        body.append(dbc.Tooltip(info, target=info_id, placement="bottom"))
    return dbc.Card(
        dbc.CardBody(body),
        className="h-100 shadow-sm kpi-card",
        style={"borderLeft": f"4px solid {accent}"},
    )


def _compare_card(title, value, cur, prev, accent):
    up, text = _delta(cur, prev, pct=True)
    subtitle = f"vs last week ({prev:.0f})" if prev is not None else "no prior week"
    return dbc.Card(
        dbc.CardBody(
            [
                html.Div(title, className="kpi-title"),
                html.Div(
                    [html.Span(value, className="kpi-value"), _delta_span(up, text)],
                    className="kpi-value-row",
                ),
                html.Div(subtitle, className="kpi-subtitle mt-auto"),
            ],
            className="d-flex flex-column h-100",
        ),
        className="h-100 shadow-sm kpi-card",
        style={"borderLeft": f"4px solid {accent}"},
    )


def _zone_tooltip():
    rows = [
        html.Div(
            [
                html.Span(className="kpi-zone-swatch", style={"backgroundColor": z["color"]}),
                html.Span(f"{z['label']} — {z['range']}"),
            ],
            className="kpi-zone-row",
        )
        for z in FORM_ZONES
    ]
    return html.Div(rows)


def _form_card(tsb, zone, info_id="overview-form-info"):
    return dbc.Card(
        dbc.CardBody(
            [
                html.Div(
                    [
                        html.Span("Form (TSB)", className="kpi-title"),
                        html.Span("\u24d8", id=info_id, className="kpi-info"),
                    ],
                    className="kpi-header",
                ),
                html.Div(
                    [
                        html.Span(f"{tsb:+.0f}", className="kpi-value"),
                        html.Span(
                            zone["label"],
                            className="kpi-zone-chip",
                            style={"backgroundColor": _rgba(zone["color"], 0.18), "color": zone["color"]},
                        ),
                    ],
                    className="kpi-value-row",
                ),
                html.Div(f"{zone['label']} zone ({zone['range']})", className="kpi-subtitle"),
                dbc.Tooltip(_zone_tooltip(), target=info_id, placement="bottom", className="kpi-zone-tooltip"),
            ]
        ),
        className="h-100 shadow-sm kpi-card",
        style={"borderLeft": f"4px solid {zone['color']}"},
    )


def _kpi_strip(weeks: list[dict]):
    latest = weeks[-1]
    prev = weeks[-2] if len(weeks) > 1 else None
    ctl = latest.get("ctl") or 0
    atl = latest.get("atl") or 0
    tsb = latest.get("tsb") or 0.0
    tss = latest.get("total_tss") or 0
    hours = latest.get("total_hours") or 0

    # Scope each sparkline to its metric's load window. Data is weekly, so
    # 42-day fitness ≈ last 6 weeks and 7-day fatigue ≈ the most recent week
    # (floored to 2 points so a line can still render).
    ctl_series = [w["ctl"] or 0 for w in weeks][-6:]
    atl_series = [w["atl"] or 0 for w in weeks][-2:]

    return dbc.Row(
        [
            dbc.Col(
                _metric_card("Fitness (CTL)", f"{ctl:.0f}", "42-day load", LOAD_COLORS["ctl"],
                             ctl_series, _delta(ctl, (prev or {}).get("ctl")),
                             info="Sparkline shows the last 6 weeks (~42-day fitness load).",
                             info_id="overview-ctl-info"),
                lg=2, md=4, sm=6, className="mb-3",
            ),
            dbc.Col(
                _metric_card("Fatigue (ATL)", f"{atl:.0f}", "7-day load", LOAD_COLORS["atl"],
                             atl_series, _delta(atl, (prev or {}).get("atl")),
                             info="Sparkline shows the most recent week (~7-day fatigue load).",
                             info_id="overview-atl-info"),
                lg=2, md=4, sm=6, className="mb-3",
            ),
            dbc.Col(_form_card(tsb, _form_zone(tsb)), lg=2, md=4, sm=6, className="mb-3"),
            dbc.Col(
                _compare_card("This Week TSS", f"{tss:.0f}", tss, (prev or {}).get("total_tss"), COLORS["primary"]),
                lg=3, md=6, sm=6, className="mb-3",
            ),
            dbc.Col(
                _compare_card("This Week Hours", f"{hours:.1f}", hours, (prev or {}).get("total_hours"), COLORS["teal"]),
                lg=3, md=6, sm=6, className="mb-3",
            ),
        ],
        className="g-3",
    )


def layout(engine: Engine):
    weeks = get_weekly_training(engine)

    if not weeks:
        return dbc.Container(
            [
                html.H1("Overview", className="mt-2 mb-4"),
                dbc.Alert(
                    "No training data yet. Run the sync to import activities.",
                    color="info",
                ),
            ],
            fluid=True,
        )

    header = html.Div(
        [
            html.H1("Overview", className="mb-0"),
            html.Div(
                dcc.Dropdown(
                    id="overview-range",
                    options=RANGE_OPTIONS,
                    value=DEFAULT_RANGE_WEEKS,
                    clearable=False,
                    searchable=False,
                    className="range-dropdown",
                ),
                style={"width": "150px"},
            ),
        ],
        className="overview-header mt-2 mb-4",
    )

    return dbc.Container(
        [
            header,
            html.Div(id="overview-kpis"),
            html.Div(id="overview-charts"),
        ],
        fluid=True,
    )


def _charts(weeks: list[dict]):
    return [
        dbc.Row(
            [
                dbc.Col(section_card("Weekly TSS by Sport", dcc.Graph(figure=_weekly_tss_figure(weeks), config=STATIC_GRAPH_CONFIG)), lg=6),
                dbc.Col(section_card("Weekly Hours by Sport", dcc.Graph(figure=_weekly_hours_figure(weeks), config=STATIC_GRAPH_CONFIG)), lg=6),
            ],
            className="mb-3",
        ),
        dbc.Row(
            [
                dbc.Col(section_card("Fitness, Fatigue & Form", dcc.Graph(figure=_load_form_figure(weeks), config=STATIC_GRAPH_CONFIG)), lg=6),
                dbc.Col(section_card("Weekly TSS / Hour", dcc.Graph(figure=_weekly_tss_per_hour_figure(weeks), config=STATIC_GRAPH_CONFIG)), lg=6),
            ]
        ),
    ]


@callback(
    Output("overview-kpis", "children"),
    Output("overview-charts", "children"),
    Input("overview-range", "value"),
)
def update_overview(range_weeks):
    weeks = get_weekly_training(get_engine())
    if not weeks:
        return dbc.Alert("No training data yet.", color="info"), None
    weeks = slice_weeks(weeks, range_weeks if range_weeks is not None else DEFAULT_RANGE_WEEKS)
    return _kpi_strip(weeks), _charts(weeks)
