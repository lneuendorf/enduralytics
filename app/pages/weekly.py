"""Weekly page: per-week sport breakdown and longest sessions."""

from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import ALL, Input, Output, State, callback, ctx, dcc, html, no_update
from sqlalchemy.engine import Engine

from app.components import (
    DEFAULT_RANGE_WEEKS,
    next_sort_state,
    range_selector,
    section_card,
    slice_weeks,
    sort_rows,
    sortable_table,
)
from app.data import get_engine, get_weekly_training
from app.utils import meters_to_miles, meters_to_yards


def _km_to_miles(distance_km: float | None) -> float:
    return meters_to_miles((distance_km or 0) * 1000)


def _km_to_yards(distance_km: float | None) -> float:
    return meters_to_yards((distance_km or 0) * 1000)


WEEKLY_COLUMNS = [
    {"key": "week_start", "label": "Week", "default_dir": "desc",
     "sort": lambda w: w.get("week_start"),
     "render": lambda w: w["week_start"]},
    {"key": "total_tss", "label": "Total TSS", "align": "end", "cell_class": "fw-semibold",
     "sort": lambda w: w.get("total_tss") or 0,
     "render": lambda w: f"{w.get('total_tss') or 0:.0f}"},
    {"key": "run_tss", "label": "Run TSS", "align": "end",
     "sort": lambda w: w.get("run_tss") or 0,
     "render": lambda w: f"{w.get('run_tss') or 0:.0f}"},
    {"key": "bike_tss", "label": "Bike TSS", "align": "end",
     "sort": lambda w: w.get("bike_tss") or 0,
     "render": lambda w: f"{w.get('bike_tss') or 0:.0f}"},
    {"key": "swim_tss", "label": "Swim TSS", "align": "end",
     "sort": lambda w: w.get("swim_tss") or 0,
     "render": lambda w: f"{w.get('swim_tss') or 0:.0f}"},
    {"key": "total_hours", "label": "Hours", "align": "end",
     "sort": lambda w: w.get("total_hours") or 0,
     "render": lambda w: f"{w.get('total_hours') or 0:.1f}"},
    {"key": "run_distance", "label": "Run Total", "align": "end",
     "sort": lambda w: w.get("run_distance") or 0,
     "render": lambda w: f"{_km_to_miles(w.get('run_distance')):.1f} mi"},
    {"key": "bike_distance", "label": "Bike Total", "align": "end",
     "sort": lambda w: w.get("bike_distance") or 0,
     "render": lambda w: f"{_km_to_miles(w.get('bike_distance')):.1f} mi"},
    {"key": "swim_distance", "label": "Swim Total", "align": "end",
     "sort": lambda w: w.get("swim_distance") or 0,
     "render": lambda w: f"{_km_to_yards(w.get('swim_distance')):.0f} yd"},
]

DEFAULT_WEEKLY_SORT = {"col": "week_start", "dir": "desc"}


def _weekly_table(weeks: list[dict], sort_state: dict):
    ordered = sort_rows(weeks, WEEKLY_COLUMNS, sort_state)
    return sortable_table(ordered, WEEKLY_COLUMNS, sort_state, "weekly-sort-col")


def layout(engine: Engine):
    weeks = get_weekly_training(engine)

    if not weeks:
        return dbc.Container(
            [
                html.H1("Weekly", className="mt-2 mb-4"),
                dbc.Alert("No training data yet. Run the sync to import activities.", color="info"),
            ],
            fluid=True,
        )

    return dbc.Container(
        [
            html.H1("Weekly", className="mt-2 mb-4"),
            dcc.Store(id="weekly-sort", data=DEFAULT_WEEKLY_SORT),
            range_selector("weekly-range"),
            html.Div(id="weekly-table-container"),
        ],
        fluid=True,
    )


@callback(
    Output("weekly-sort", "data"),
    Input({"type": "weekly-sort-col", "index": ALL}, "n_clicks"),
    State("weekly-sort", "data"),
    prevent_initial_call=True,
)
def update_weekly_sort(n_clicks, current):
    if not ctx.triggered or not ctx.triggered[0]["value"]:
        return no_update
    return next_sort_state(WEEKLY_COLUMNS, current, ctx.triggered_id["index"])


# Sorting a column only re-renders this (small) table, so the chart above it is
# left untouched — no heavy re-transmit and no layout shift under the cursor.
@callback(
    Output("weekly-table-container", "children"),
    Input("weekly-range", "value"),
    Input("weekly-sort", "data"),
)
def update_weekly_table(range_weeks, sort_state):
    weeks = get_weekly_training(get_engine())
    if not weeks:
        return None
    weeks = slice_weeks(weeks, range_weeks if range_weeks is not None else DEFAULT_RANGE_WEEKS)
    return section_card("Weekly Detail", _weekly_table(weeks, sort_state or DEFAULT_WEEKLY_SORT))
