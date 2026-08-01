"""Helpers for reading and persisting athlete threshold settings.

The training-load calculations (bike/run/swim TSS, CTL, ATL, TSB) all depend on
per-athlete thresholds. This module centralizes reading and upserting the single
``athlete_settings`` row so both the pipeline and dashboard use one code path.
"""

from __future__ import annotations

import os
from collections import defaultdict
from datetime import date
from typing import Any, Callable

from sqlalchemy.orm import Session

from .connection import session_scope
from .models import AthleteSettingEntry, AthleteSettings

DEFAULT_ATHLETE_ID = "default"

# The threshold fields that can be recorded as dated entries. These map directly
# to the keyword arguments consumed by ``analytics.tss``.
SETTING_FIELDS: tuple[str, ...] = (
    "ftp_watts",
    "run_threshold_pace_seconds_per_km",
    "swim_css_pace_seconds_per_100m",
    "threshold_hr",
    "resting_hr",
    "max_hr",
)

# Environment variable -> AthleteSettings field, with the parser to apply.
_ENV_FIELD_MAP: dict[str, tuple[str, type]] = {
    "ATHLETE_FTP_WATTS": ("ftp_watts", int),
    "ATHLETE_RUN_THRESHOLD_PACE_SECONDS_PER_KM": ("run_threshold_pace_seconds_per_km", float),
    "ATHLETE_SWIM_CSS_PACE_SECONDS_PER_100M": ("swim_css_pace_seconds_per_100m", float),
    "ATHLETE_MAX_HR": ("max_hr", int),
    "ATHLETE_RESTING_HR": ("resting_hr", int),
    "ATHLETE_THRESHOLD_HR": ("threshold_hr", int),
}



def get_athlete_settings(
    session: Session, athlete_id: str = DEFAULT_ATHLETE_ID
) -> AthleteSettings | None:
    """Return the settings row for ``athlete_id`` or ``None`` if not seeded yet."""
    return (
        session.query(AthleteSettings)
        .filter(AthleteSettings.athlete_id == athlete_id)
        .one_or_none()
    )


def get_season_goals(
    session: Session, athlete_id: str = DEFAULT_ATHLETE_ID
) -> dict[str, float | None]:
    """Return the annual TSS/hours planning targets (``None`` when unset)."""
    settings = get_athlete_settings(session, athlete_id)
    if settings is None:
        return {"annual_tss_goal": None, "annual_hours_goal": None}
    return {
        "annual_tss_goal": settings.annual_tss_goal,
        "annual_hours_goal": settings.annual_hours_goal,
    }


def athlete_tss_kwargs(
    session: Session, athlete_id: str = DEFAULT_ATHLETE_ID
) -> dict[str, Any]:
    """Return the threshold keyword arguments consumed by ``analytics.tss``.

    Resolves the values in effect *today* from the dated setting entries, falling
    back to the legacy single-row settings when no dated entries exist. Kept as a
    convenience for callers that do not need per-activity resolution.
    """
    resolver = build_settings_resolver(session, athlete_id)
    resolved = resolver(date.today())
    if resolved:
        return resolved

    settings = get_athlete_settings(session, athlete_id)
    if settings is None:
        return {}
    return {
        "ftp_watts": settings.ftp_watts,
        "run_threshold_pace_seconds_per_km": settings.run_threshold_pace_seconds_per_km,
        "swim_css_pace_seconds_per_100m": settings.swim_css_pace_seconds_per_100m,
        "threshold_hr": settings.threshold_hr,
        "resting_hr": settings.resting_hr,
    }


def list_setting_entries(
    session: Session, athlete_id: str = DEFAULT_ATHLETE_ID
) -> list[AthleteSettingEntry]:
    """Return every dated setting entry, newest effective date first."""
    return (
        session.query(AthleteSettingEntry)
        .filter(AthleteSettingEntry.athlete_id == athlete_id)
        .order_by(
            AthleteSettingEntry.effective_date.desc(),
            AthleteSettingEntry.created_at.desc(),
        )
        .all()
    )


def add_setting_entry(
    session: Session,
    field: str,
    value: float,
    effective_date: date,
    athlete_id: str = DEFAULT_ATHLETE_ID,
) -> AthleteSettingEntry:
    """Record a dated value for one threshold ``field``."""
    if field not in SETTING_FIELDS:
        raise ValueError(f"Unknown setting field '{field}'")
    entry = AthleteSettingEntry(
        athlete_id=athlete_id,
        field=field,
        value=float(value),
        effective_date=effective_date,
    )
    session.add(entry)
    session.flush()
    return entry


def delete_setting_entry(
    session: Session, entry_id: int, athlete_id: str = DEFAULT_ATHLETE_ID
) -> bool:
    """Delete a dated entry by id. Returns True when a row was removed."""
    entry = (
        session.query(AthleteSettingEntry)
        .filter(
            AthleteSettingEntry.id == entry_id,
            AthleteSettingEntry.athlete_id == athlete_id,
        )
        .one_or_none()
    )
    if entry is None:
        return False
    session.delete(entry)
    session.flush()
    return True


def build_settings_resolver(
    session: Session, athlete_id: str = DEFAULT_ATHLETE_ID
) -> Callable[[date], dict[str, Any]]:
    """Return ``resolve(target_date) -> {field: value}`` for the dated entries.

    For each field, ``resolve`` picks the most recent entry whose effective date
    is on or before ``target_date`` (forward-looking). For dates that fall before
    every recorded entry, it uses the earliest entry (backward-looking). Fields
    with no entries are omitted, so the caller falls back to duration-based TSS.
    """
    entries = (
        session.query(AthleteSettingEntry)
        .filter(AthleteSettingEntry.athlete_id == athlete_id)
        .order_by(
            AthleteSettingEntry.effective_date.asc(),
            AthleteSettingEntry.created_at.asc(),
        )
        .all()
    )

    by_field: dict[str, list[AthleteSettingEntry]] = defaultdict(list)
    for entry in entries:
        by_field[entry.field].append(entry)

    # Legacy single-row settings act as an undated baseline: they apply to every
    # date for any field that has no dated entries of its own.
    legacy: dict[str, Any] = {}
    settings_row = get_athlete_settings(session, athlete_id)
    if settings_row is not None:
        for field in SETTING_FIELDS:
            value = getattr(settings_row, field, None)
            if value is not None and field not in by_field:
                legacy[field] = float(value)

    def resolve(target_date: date) -> dict[str, Any]:
        resolved: dict[str, Any] = dict(legacy)
        for field, field_entries in by_field.items():
            chosen = None
            for entry in field_entries:  # ascending by effective date
                if entry.effective_date <= target_date:
                    chosen = entry
                else:
                    break
            if chosen is None:
                chosen = field_entries[0]  # backward-looking: earliest value
            resolved[field] = chosen.value
        return resolved

    return resolve


def upsert_athlete_settings(
    session: Session, athlete_id: str = DEFAULT_ATHLETE_ID, **fields: Any
) -> AthleteSettings:
    """Create or update the settings row for ``athlete_id``.

    Only keys present in ``fields`` are written; ``None`` values are ignored so a
    partial update never clobbers existing thresholds.
    """
    settings = get_athlete_settings(session, athlete_id)
    if settings is None:
        settings = AthleteSettings(athlete_id=athlete_id)
        session.add(settings)

    for key, value in fields.items():
        if value is None:
            continue
        if not hasattr(settings, key):
            raise AttributeError(f"AthleteSettings has no field '{key}'")
        setattr(settings, key, value)

    session.flush()
    return settings


def _settings_from_env() -> dict[str, Any]:
    """Read known athlete settings from environment variables."""
    values: dict[str, Any] = {}
    for env_name, (field, parser) in _ENV_FIELD_MAP.items():
        raw = os.getenv(env_name)
        if raw is None or raw == "":
            continue
        values[field] = parser(raw)
    return values


def seed_from_env(
    database_url: str | None = None, athlete_id: str = DEFAULT_ATHLETE_ID
) -> AthleteSettings:
    """Upsert athlete settings from environment variables and return the row."""
    values = _settings_from_env()
    with session_scope(database_url) as session:
        settings = upsert_athlete_settings(session, athlete_id=athlete_id, **values)
        session.expunge(settings)
        return settings


def main() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    settings = seed_from_env()
    print(f"Seeded athlete settings for '{settings.athlete_id}': {settings.to_dict()}")


if __name__ == "__main__":
    main()
