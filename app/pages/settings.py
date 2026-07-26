"""Settings page: record dated athlete thresholds and recompute metrics.

Each threshold is entered as a *dated* value: you say what the value was and
when it took effect. The processing pipeline then resolves the value in effect
for every activity date (forward-looking, with a backward-looking fallback for
dates that precede the earliest recorded value).
"""

from __future__ import annotations

from datetime import date

import dash_bootstrap_components as dbc
from dash import ALL, Input, Output, State, callback, ctx, dcc, html, no_update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.components import section_card
from app.data import clear_read_cache, get_engine
from database.settings import (
    add_setting_entry,
    delete_setting_entry,
    list_setting_entries,
)
from pipeline.process_activities import process_all

# The DB stores run threshold pace in seconds per kilometer (matching the
# analytics), but the UI presents it in minutes per mile.
_KM_PER_MILE = 1.609344


# --- Field metadata --------------------------------------------------------
#
# ``kind`` drives parsing/formatting and the input control type. Insertion order
# controls the order of the six setting cards on the page.
FIELD_DEFS: dict[str, dict[str, str]] = {
    "ftp_watts": {
        "label": "FTP (watts)",
        "kind": "int",
        "placeholder": "e.g. 250",
        "help": "Functional Threshold Power — bike TSS.",
    },
    "threshold_hr": {
        "label": "Threshold HR (bpm)",
        "kind": "int",
        "placeholder": "e.g. 165",
        "help": "Lactate threshold heart rate — HR-based TSS.",
    },
    "resting_hr": {
        "label": "Resting HR (bpm)",
        "kind": "int",
        "placeholder": "e.g. 48",
        "help": "Enables HR-reserve intensity when set.",
    },
    "max_hr": {
        "label": "Max HR (bpm)",
        "kind": "int",
        "placeholder": "e.g. 190",
        "help": "Maximum heart rate.",
    },
    "run_threshold_pace_seconds_per_km": {
        "label": "Run threshold pace (min/mi)",
        "kind": "run_pace",
        "placeholder": "e.g. 6:50",
        "help": "Threshold pace as mm:ss per mile — run TSS.",
    },
    "swim_css_pace_seconds_per_100m": {
        "label": "Swim CSS pace (min/100m)",
        "kind": "swim_pace",
        "placeholder": "e.g. 1:35",
        "help": "Critical Swim Speed as mm:ss per 100 m — swim TSS.",
    },
}


def _parse_pace(text) -> float | None:
    """Parse 'mm:ss' or plain seconds into float seconds."""
    if text in (None, ""):
        return None
    text = str(text).strip()
    if not text:
        return None
    if ":" in text:
        minutes, seconds = text.split(":", 1)
        return float(int(minutes) * 60 + float(seconds))
    return float(text)


def _format_pace(seconds) -> str:
    if not seconds:
        return ""
    seconds = int(round(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def _km_pace_to_mile(seconds_per_km) -> float | None:
    """Convert a seconds-per-km pace to seconds-per-mile for display."""
    if not seconds_per_km:
        return None
    return seconds_per_km * _KM_PER_MILE


def _mile_pace_to_km(seconds_per_mile) -> float | None:
    """Convert a seconds-per-mile pace to seconds-per-km for storage."""
    if not seconds_per_mile:
        return None
    return seconds_per_mile / _KM_PER_MILE


def _parse_value(kind: str, raw) -> float:
    """Parse a raw UI value into the canonical stored number for ``kind``.

    Raises ``ValueError``/``TypeError`` on unparseable input.
    """
    if raw in (None, ""):
        raise ValueError("empty")
    if kind == "int":
        return float(int(raw))
    if kind == "run_pace":
        km = _mile_pace_to_km(_parse_pace(raw))
        if km is None:
            raise ValueError("bad pace")
        return float(km)
    if kind == "swim_pace":
        sec = _parse_pace(raw)
        if sec is None:
            raise ValueError("bad pace")
        return float(sec)
    raise ValueError(f"unknown kind {kind}")


def _format_value(kind: str, value) -> str:
    if value is None:
        return ""
    if kind == "int":
        return str(int(round(value)))
    if kind == "run_pace":
        return f"{_format_pace(_km_pace_to_mile(value))} /mi"
    if kind == "swim_pace":
        return f"{_format_pace(value)} /100m"
    return str(value)


def _setting_card(field: str, meta: dict[str, str]):
    is_pace = meta["kind"] in ("run_pace", "swim_pace")
    body = html.Div(
        [
            dbc.Label("Value", className="fw-semibold"),
            dbc.Input(
                id={"type": "setting-value", "field": field},
                type="text" if is_pace else "number",
                placeholder=meta["placeholder"],
            ),
            html.Small(meta["help"], className="text-muted d-block mb-2"),
            dbc.Label("Effective date", className="fw-semibold"),
            html.Div(
                dcc.DatePickerSingle(
                    id={"type": "setting-date", "field": field},
                    date=date.today().isoformat(),
                    display_format="YYYY-MM-DD",
                    className="d-block",
                )
            ),
            dbc.Button(
                "Add value",
                id={"type": "add-setting", "field": field},
                color="primary",
                size="sm",
                className="mt-2",
                n_clicks=0,
            ),
        ]
    )
    return dbc.Col(section_card(meta["label"], body), md=6, lg=4, className="mb-3")


def _entry_row(entry):
    meta = FIELD_DEFS.get(entry.field, {})
    return html.Tr(
        [
            html.Td(meta.get("label", entry.field)),
            html.Td(_format_value(meta.get("kind", ""), entry.value)),
            html.Td(entry.effective_date.isoformat() if entry.effective_date else ""),
            html.Td(
                dbc.Button(
                    "\u2715",
                    id={"type": "del-setting", "index": entry.id},
                    color="link",
                    size="sm",
                    className="text-danger p-0",
                    n_clicks=0,
                    title="Delete this value",
                ),
                className="text-end",
            ),
        ]
    )


def _entries_table(entries):
    if not entries:
        return html.P("No values recorded yet.", className="text-muted mb-0")
    header = html.Thead(
        html.Tr(
            [
                html.Th("Setting"),
                html.Th("Value"),
                html.Th("Effective date"),
                html.Th("", className="text-end"),
            ]
        )
    )
    body = html.Tbody([_entry_row(e) for e in entries])
    return dbc.Table([header, body], hover=True, responsive=True, className="align-middle mb-0")


def _entries_view(engine: Engine):
    with Session(engine) as session:
        entries = list_setting_entries(session)
    return _entries_table(entries)


def layout(engine: Engine):
    cards = dbc.Row([_setting_card(field, meta) for field, meta in FIELD_DEFS.items()])

    return dbc.Container(
        [
            html.H1("Settings", className="mt-2 mb-2"),
            html.P(
                "Record each threshold with the date it took effect. Every activity "
                "uses the value in effect on its date (the most recent value on or "
                "before it; the earliest value for dates before your first entry).",
                className="text-muted",
            ),
            cards,
            html.Div(id="settings-status", className="mt-2 mb-3"),
            section_card(
                "Recorded values",
                html.Div(_entries_view(engine), id="settings-entries"),
            ),
        ],
        fluid=True,
    )


@callback(
    Output("settings-entries", "children"),
    Output("settings-status", "children"),
    Input({"type": "add-setting", "field": ALL}, "n_clicks"),
    Input({"type": "del-setting", "index": ALL}, "n_clicks"),
    State({"type": "setting-value", "field": ALL}, "value"),
    State({"type": "setting-value", "field": ALL}, "id"),
    State({"type": "setting-date", "field": ALL}, "date"),
    State({"type": "setting-date", "field": ALL}, "id"),
    prevent_initial_call=True,
)
def modify_settings(add_clicks, del_clicks, values, value_ids, dates, date_ids):
    trigger = ctx.triggered_id
    if not trigger or not isinstance(trigger, dict):
        return no_update, no_update

    # A pattern-matching input fires on any change; ignore no-op fires where the
    # triggering button was never actually clicked.
    triggered = ctx.triggered[0] if ctx.triggered else {}
    if not triggered.get("value"):
        return no_update, no_update

    engine = get_engine()

    try:
        if trigger.get("type") == "add-setting":
            field = trigger["field"]
            meta = FIELD_DEFS[field]
            value_by_field = {vid["field"]: v for v, vid in zip(values, value_ids)}
            date_by_field = {did["field"]: d for d, did in zip(dates, date_ids)}

            raw_value = value_by_field.get(field)
            raw_date = date_by_field.get(field)
            if raw_date in (None, ""):
                return no_update, dbc.Alert("Pick an effective date.", color="danger")

            try:
                parsed = _parse_value(meta["kind"], raw_value)
            except (ValueError, TypeError):
                return no_update, dbc.Alert(
                    f"Could not parse the {meta['label']} value.", color="danger"
                )

            effective = date.fromisoformat(raw_date[:10])
            with Session(engine) as session:
                add_setting_entry(session, field, parsed, effective)
                session.commit()
            action = (
                f"Added {meta['label']} = {_format_value(meta['kind'], parsed)} "
                f"on {effective.isoformat()}."
            )

        elif trigger.get("type") == "del-setting":
            entry_id = trigger["index"]
            with Session(engine) as session:
                removed = delete_setting_entry(session, entry_id)
                session.commit()
            if not removed:
                return _entries_view(engine), dbc.Alert("Value already removed.", color="warning")
            action = "Deleted value."
        else:
            return no_update, no_update
    except Exception as exc:  # pragma: no cover - surface unexpected errors in UI
        return no_update, dbc.Alert(f"Something went wrong: {exc}", color="danger")

    counts = process_all(engine=engine)
    clear_read_cache()
    message = (
        f"{action} Recomputed {counts['activity_metrics']} activities and "
        f"{counts['weekly_training']} weekly rollups."
    )
    return _entries_view(engine), dbc.Alert(message, color="success")
