"""Data-access helpers for the dashboard.

The dashboard only *reads* processed data. These helpers pull from the persisted
``weekly_training`` and ``activity_metrics`` tables (populated by
``pipeline.process_activities``), falling back to on-the-fly aggregation when the
processed tables are empty so the app still renders on a fresh database.
"""

from __future__ import annotations

import os
import time
from datetime import date
from typing import Any

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from analytics.tss import classify_discipline
from analytics.weekly import aggregate_weekly_activity_summaries, project_year_end
from database.connection import create_engine_from_url
from database.models import Activity, ActivityMetrics, WeeklyTraining
from database.settings import get_season_goals

_engine: Engine | None = None

# Short-lived cache for the read-only dashboard queries. Pagination and column
# sorting fire the same query repeatedly; caching keeps those interactions snappy
# without a DB round-trip each time. Data only changes when the (separate) sync
# process runs, so a small TTL keeps things fresh enough.
_READ_CACHE: dict[tuple, tuple[float, Any]] = {}
_READ_CACHE_TTL = 30.0


def _cache_get(key: tuple) -> Any | None:
    entry = _READ_CACHE.get(key)
    if entry is not None and (time.monotonic() - entry[0]) < _READ_CACHE_TTL:
        return entry[1]
    return None


def _cache_put(key: tuple, value: Any) -> None:
    _READ_CACHE[key] = (time.monotonic(), value)


def clear_read_cache() -> None:
    """Drop cached query results (e.g. after a sync writes new data)."""
    _READ_CACHE.clear()


def get_engine() -> Engine:
    """Return a process-wide database engine."""
    global _engine
    if _engine is None:
        _engine = create_engine_from_url(os.getenv("DATABASE_URL", "sqlite:///enduralytics.db"))
    return _engine


def _summary_to_weekly(summary: dict[str, Any]) -> dict[str, Any]:
    """Map an in-memory weekly summary to the WeeklyTraining dict shape."""
    return {
        "week_start": summary["week_start"],
        "total_tss": summary["total_tss"],
        "bike_tss": summary["bike_tss"],
        "run_tss": summary["run_tss"],
        "swim_tss": summary["swim_tss"],
        "total_hours": round(summary["total_duration_seconds"] / 3600.0, 2),
        "run_hours": round(summary["running_duration_seconds"] / 3600.0, 2),
        "bike_hours": round(summary["cycling_duration_seconds"] / 3600.0, 2),
        "swim_hours": round(summary["swimming_duration_seconds"] / 3600.0, 2),
        "run_distance": summary["run_distance_km"],
        "bike_distance": summary["bike_distance_km"],
        "swim_distance": summary["swim_distance_km"],
        "ctl": summary["ctl"],
        "atl": summary["atl"],
        "tsb": summary["tsb"],
        "longest_run": summary["longest_run_km"],
        "longest_bike": summary["longest_bike_km"],
        "longest_swim": summary["longest_swim_km"],
    }


def get_weekly_training(engine: Engine) -> list[dict[str, Any]]:
    """Return weekly training rollups ordered by week (oldest first)."""
    cached = _cache_get(("weekly",))
    if cached is not None:
        return cached

    with Session(engine) as session:
        rows = (
            session.query(WeeklyTraining)
            .order_by(WeeklyTraining.week_start.asc())
            .all()
        )
        if rows:
            result = [row.to_dict() for row in rows]
        else:
            # Fallback: compute on the fly when nothing has been processed yet.
            result = [_summary_to_weekly(s) for s in aggregate_weekly_activity_summaries(engine)]

    _cache_put(("weekly",), result)
    return result


def get_activities_with_metrics(
    engine: Engine, discipline: str | None = None, limit: int = 1000
) -> list[dict[str, Any]]:
    """Return activities joined with their metrics, newest first.

    ``discipline`` optionally filters to ``run`` / ``bike`` / ``swim``.
    """
    cached = _cache_get(("activities", discipline, limit))
    if cached is not None:
        return cached

    with Session(engine) as session:
        rows = (
            session.query(Activity, ActivityMetrics)
            .outerjoin(ActivityMetrics, Activity.activity_id == ActivityMetrics.activity_id)
            .filter(Activity.date.is_not(None))
            .order_by(Activity.date.desc())
            .limit(limit)
            .all()
        )

    results: list[dict[str, Any]] = []
    for activity, metric in rows:
        activity_discipline = (metric.discipline if metric else None) or classify_discipline(activity.sport)
        if discipline and activity_discipline != discipline:
            continue
        results.append(
            {
                "activity_id": activity.activity_id,
                "date": activity.date.date().isoformat() if activity.date else None,
                "activity_name": activity.activity_name,
                "sport": activity.sport,
                "discipline": activity_discipline,
                "duration_seconds": activity.duration_seconds,
                "distance_meters": activity.distance,
                "avg_hr": activity.avg_hr,
                "avg_power": activity.avg_power,
                "normalized_power": activity.normalized_power,
                "tss": metric.tss if metric else None,
                "intensity_factor": metric.intensity_factor if metric else None,
                "tss_method": metric.tss_method if metric else None,
            }
        )
    _cache_put(("activities", discipline, limit), results)
    return results


def get_season_progress(engine: Engine, today: date | None = None) -> dict[str, Any]:
    """Year-to-date TSS/hours totals with year-end projections vs annual goals.

    Actuals sum the ``weekly_training`` rows whose week falls in the current
    calendar year. Projections come from :func:`analytics.weekly.project_year_end`
    using a trailing 8-week rate. Goals are read from the athlete settings row.
    """
    today = today or date.today()
    year = today.year

    weeks = get_weekly_training(engine)
    year_weeks = [w for w in weeks if str(w["week_start"])[:4] == str(year)]
    ytd_tss = sum(w.get("total_tss") or 0 for w in year_weeks)
    ytd_hours = sum(w.get("total_hours") or 0 for w in year_weeks)

    # Trailing per-week rate from the most recent (up to) 8 weeks of data.
    recent = weeks[-8:] if weeks else []
    tss_rate = (sum(w.get("total_tss") or 0 for w in recent) / len(recent)) if recent else 0.0
    hours_rate = (sum(w.get("total_hours") or 0 for w in recent) / len(recent)) if recent else 0.0

    day_of_year = today.timetuple().tm_yday
    fraction_elapsed = day_of_year / 365.0
    weeks_remaining = max((365 - day_of_year) / 7.0, 0.0)

    tss_proj = project_year_end(ytd_tss, fraction_elapsed, tss_rate, weeks_remaining)
    hours_proj = project_year_end(ytd_hours, fraction_elapsed, hours_rate, weeks_remaining)

    with Session(engine) as session:
        goals = get_season_goals(session)

    return {
        "year": year,
        "ytd_tss": ytd_tss,
        "ytd_hours": ytd_hours,
        "tss_projection": tss_proj,
        "hours_projection": hours_proj,
        "annual_tss_goal": goals["annual_tss_goal"],
        "annual_hours_goal": goals["annual_hours_goal"],
        "fraction_elapsed": fraction_elapsed,
    }
