from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from database.models import Activity
from database.settings import build_settings_resolver

from .atl import compute_atl
from .ctl import compute_ctl
from .tsb import compute_tsb
from .tss import activity_tss, classify_discipline

# Maps a normalized discipline to the legacy per-sport duration key.
_DISCIPLINE_DURATION_KEY = {
    "run": "running_duration_seconds",
    "bike": "cycling_duration_seconds",
    "swim": "swimming_duration_seconds",
}


def _start_of_week(activity_date: datetime) -> date:
    monday = activity_date - timedelta(days=activity_date.weekday())
    return monday.date()


def _new_bucket() -> dict[str, Any]:
    return {
        "week_start": None,
        "running_duration_seconds": 0,
        "cycling_duration_seconds": 0,
        "swimming_duration_seconds": 0,
        "total_duration_seconds": 0,
        "total_distance_km": 0.0,
        "run_distance_km": 0.0,
        "bike_distance_km": 0.0,
        "swim_distance_km": 0.0,
        "run_tss": 0.0,
        "bike_tss": 0.0,
        "swim_tss": 0.0,
        "total_tss": 0.0,
        "longest_run_km": 0.0,
        "longest_bike_km": 0.0,
        "longest_swim_km": 0.0,
        "ctl": 0.0,
        "atl": 0.0,
        "tsb": 0.0,
    }


def _build_daily_load_series(
    daily_tss: dict[date, float],
) -> dict[date, dict[str, float]]:
    """Compute CTL/ATL/TSB for every calendar day in the activity span."""
    if not daily_tss:
        return {}

    start_day = min(daily_tss)
    end_day = max(daily_tss)
    span_days = (end_day - start_day).days + 1

    days = [start_day + timedelta(days=offset) for offset in range(span_days)]
    series = [daily_tss.get(day, 0.0) for day in days]

    ctl = compute_ctl(series)
    atl = compute_atl(series)
    tsb = compute_tsb(ctl, atl)

    return {
        day: {"ctl": ctl[idx], "atl": atl[idx], "tsb": tsb[idx]}
        for idx, day in enumerate(days)
    }


def _sample_week_load(
    week_start: date, load_by_day: dict[date, dict[str, float]]
) -> dict[str, float]:
    """CTL/ATL/TSB as of the end of ``week_start``'s week (clamped to data span)."""
    empty = {"ctl": 0.0, "atl": 0.0, "tsb": 0.0}
    if not load_by_day:
        return empty

    first_day = min(load_by_day)
    last_day = max(load_by_day)
    week_end = week_start + timedelta(days=6)
    sample_day = min(max(week_end, first_day), last_day)
    return load_by_day.get(sample_day, empty)


def aggregate_weekly_activity_summaries(engine: Engine) -> list[dict[str, Any]]:
    with Session(engine) as session:
        resolve_settings = build_settings_resolver(session)
        activities = (
            session.query(Activity)
            .filter(Activity.date.is_not(None))
            .order_by(Activity.date.asc())
            .all()
        )

    grouped: dict[date, dict[str, Any]] = defaultdict(_new_bucket)
    daily_tss: dict[date, float] = defaultdict(float)

    for activity in activities:
        if not activity.date:
            continue

        settings = resolve_settings(activity.date.date())

        week_start = _start_of_week(activity.date)
        bucket = grouped[week_start]
        bucket["week_start"] = week_start.isoformat()

        duration = int(activity.duration_seconds or 0)
        distance_m = float(activity.distance or 0.0)
        distance_km = distance_m / 1000.0
        bucket["total_duration_seconds"] += duration
        bucket["total_distance_km"] += distance_km

        discipline = classify_discipline(activity.sport)
        if discipline in _DISCIPLINE_DURATION_KEY:
            bucket[_DISCIPLINE_DURATION_KEY[discipline]] += duration
            bucket[f"{discipline}_distance_km"] += distance_km
            longest_key = f"longest_{discipline}_km"
            if distance_km > bucket[longest_key]:
                bucket[longest_key] = distance_km

        result = activity_tss(
            sport=activity.sport,
            duration_seconds=duration,
            distance_meters=distance_m,
            normalized_power=activity.normalized_power,
            avg_power=activity.avg_power,
            avg_hr=activity.avg_hr,
            ftp_watts=settings.get("ftp_watts"),
            run_threshold_pace_seconds_per_km=settings.get("run_threshold_pace_seconds_per_km"),
            swim_css_pace_seconds_per_100m=settings.get("swim_css_pace_seconds_per_100m"),
            threshold_hr=settings.get("threshold_hr"),
            resting_hr=settings.get("resting_hr"),
        )
        if result is not None:
            bucket["total_tss"] += result.tss
            if discipline in _DISCIPLINE_DURATION_KEY:
                bucket[f"{discipline}_tss"] += result.tss
            daily_tss[activity.date.date()] += result.tss

    load_by_day = _build_daily_load_series(dict(daily_tss))

    summaries: list[dict[str, Any]] = []
    for week_start, bucket in sorted(grouped.items()):
        load = _sample_week_load(week_start, load_by_day)
        bucket["ctl"] = round(load["ctl"], 1)
        bucket["atl"] = round(load["atl"], 1)
        bucket["tsb"] = round(load["tsb"], 1)
        for key in ("total_tss", "run_tss", "bike_tss", "swim_tss"):
            bucket[key] = round(bucket[key], 1)
        for key in (
            "total_distance_km",
            "run_distance_km",
            "bike_distance_km",
            "swim_distance_km",
            "longest_run_km",
            "longest_bike_km",
            "longest_swim_km",
        ):
            bucket[key] = round(bucket[key], 2)
        summaries.append(dict(bucket))

    return summaries


def get_recent_activities(engine: Engine, limit: int = 10) -> list[dict[str, Any]]:
    with Session(engine) as session:
        activities = (
            session.query(Activity)
            .filter(Activity.date.is_not(None))
            .order_by(Activity.date.desc())
            .limit(limit)
            .all()
        )

    return [
        {
            "activity_id": activity.activity_id,
            "activity_name": activity.activity_name,
            "sport": activity.sport,
            "date": activity.date.date().isoformat() if activity.date else None,
            "duration_seconds": activity.duration_seconds,
            "distance_meters": activity.distance,
            "distance_km": round((activity.distance or 0) / 1000.0, 2) if activity.distance else 0.0,
        }
        for activity in activities
    ]
