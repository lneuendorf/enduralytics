"""Processing stage: derive and persist training-load metrics.

Reads normalized activities, computes per-activity :class:`ActivityMetrics`, and
rolls them up into :class:`WeeklyTraining`. The stage is idempotent: rerunning it
recomputes every value in place using the same analytics used by the dashboard,
so it is safe to call after every sync.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from analytics.tss import activity_tss, classify_discipline
from analytics.weekly import aggregate_weekly_activity_summaries
from database.connection import create_engine_from_url
from database.models import Activity, ActivityMetrics, WeeklyTraining
from database.settings import build_settings_resolver

# Weekly summary key -> WeeklyTraining column mapping (distances stored in km).
_WEEKLY_COLUMN_MAP = {
    "total_tss": "total_tss",
    "bike_tss": "bike_tss",
    "run_tss": "run_tss",
    "swim_tss": "swim_tss",
    "bike_distance_km": "bike_distance",
    "run_distance_km": "run_distance",
    "swim_distance_km": "swim_distance",
    "ctl": "ctl",
    "atl": "atl",
    "tsb": "tsb",
    "longest_run_km": "longest_run",
    "longest_bike_km": "longest_bike",
    "longest_swim_km": "longest_swim",
}


def _metrics_fields(activity: Activity, settings: dict) -> dict | None:
    """Compute the ActivityMetrics field values for one activity."""
    result = activity_tss(
        sport=activity.sport,
        duration_seconds=activity.duration_seconds,
        distance_meters=activity.distance,
        normalized_power=activity.normalized_power,
        avg_power=activity.avg_power,
        avg_hr=activity.avg_hr,
        ftp_watts=settings.get("ftp_watts"),
        run_threshold_pace_seconds_per_km=settings.get("run_threshold_pace_seconds_per_km"),
        swim_css_pace_seconds_per_100m=settings.get("swim_css_pace_seconds_per_100m"),
        threshold_hr=settings.get("threshold_hr"),
        resting_hr=settings.get("resting_hr"),
    )
    if result is None:
        return None

    discipline = classify_discipline(activity.sport)
    fields = {
        "discipline": discipline,
        "tss": round(result.tss, 1),
        "intensity_factor": round(result.intensity_factor, 3) if result.intensity_factor else None,
        "tss_method": result.method,
        "bike_tss": None,
        "run_tss": None,
        "swim_tss": None,
    }
    if discipline in ("bike", "run", "swim"):
        fields[f"{discipline}_tss"] = round(result.tss, 1)
    return fields


def process_activity_metrics(session: Session) -> int:
    """Upsert ActivityMetrics for every activity. Returns rows written."""
    resolve_settings = build_settings_resolver(session)

    activities = session.query(Activity).all()
    existing = {
        metric.activity_id: metric
        for metric in session.query(ActivityMetrics).all()
    }

    written = 0
    for activity in activities:
        target = activity.date.date() if activity.date else date.today()
        fields = _metrics_fields(activity, resolve_settings(target))
        if fields is None:
            continue

        metric = existing.get(activity.activity_id)
        if metric is None:
            metric = ActivityMetrics(activity_id=activity.activity_id)
            session.add(metric)

        for key, value in fields.items():
            setattr(metric, key, value)
        written += 1

    return written


def process_weekly_training(session: Session, engine) -> int:
    """Upsert WeeklyTraining rollups from the weekly aggregator. Returns rows written."""
    summaries = aggregate_weekly_activity_summaries(engine)
    existing = {row.week_start: row for row in session.query(WeeklyTraining).all()}

    written = 0
    for summary in summaries:
        week_start = date.fromisoformat(summary["week_start"])
        row = existing.get(week_start)
        if row is None:
            row = WeeklyTraining(week_start=week_start)
            session.add(row)

        row.total_hours = round(summary["total_duration_seconds"] / 3600.0, 2)
        row.run_hours = round(summary["running_duration_seconds"] / 3600.0, 2)
        row.bike_hours = round(summary["cycling_duration_seconds"] / 3600.0, 2)
        row.swim_hours = round(summary["swimming_duration_seconds"] / 3600.0, 2)

        for summary_key, column in _WEEKLY_COLUMN_MAP.items():
            setattr(row, column, summary[summary_key])
        written += 1

    return written


def process_all(engine=None, database_url: str | None = None) -> dict[str, int]:
    """Run the full processing stage and return the counts written."""
    if engine is None:
        engine = create_engine_from_url(database_url)

    with Session(engine) as session:
        metrics = process_activity_metrics(session)
        weeks = process_weekly_training(session, engine)
        session.commit()

    return {"activity_metrics": metrics, "weekly_training": weeks}


def main() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    counts = process_all()
    print(
        f"Processed {counts['activity_metrics']} activity metrics and "
        f"{counts['weekly_training']} weekly rollups"
    )


if __name__ == "__main__":
    main()
