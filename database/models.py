from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column, Date, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class ActivityRaw(Base):
    __tablename__ = "activity_raw"
    __table_args__ = (UniqueConstraint("activity_id", name="uq_activity_raw_activity_id"),)

    id = Column(Integer, primary_key=True)
    activity_id = Column(String(64), nullable=False, index=True)
    garmin_json = Column(JSON, nullable=False)
    import_timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)


class Activity(Base):
    __tablename__ = "activities"
    __table_args__ = (UniqueConstraint("activity_id", name="uq_activities_activity_id"),)

    id = Column(Integer, primary_key=True)
    activity_id = Column(String(64), nullable=False, index=True)
    date = Column(DateTime, nullable=True)
    activity_name = Column(String(255), nullable=True)
    sport = Column(String(64), nullable=True)
    subsport = Column(String(64), nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    distance = Column(Float, nullable=True)
    avg_hr = Column(Float, nullable=True)
    max_hr = Column(Float, nullable=True)
    avg_power = Column(Float, nullable=True)
    normalized_power = Column(Float, nullable=True)
    pace = Column(Float, nullable=True)
    elevation_gain = Column(Float, nullable=True)
    source_data = Column(Text, nullable=True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "activity_id": self.activity_id,
            "date": self.date,
            "activity_name": self.activity_name,
            "sport": self.sport,
            "subsport": self.subsport,
            "duration_seconds": self.duration_seconds,
            "distance": self.distance,
            "avg_hr": self.avg_hr,
            "max_hr": self.max_hr,
            "avg_power": self.avg_power,
            "normalized_power": self.normalized_power,
            "pace": self.pace,
            "elevation_gain": self.elevation_gain,
        }


class AthleteSettings(Base):
    """Athlete thresholds used by the training-load calculations.

    A single active row is expected for the personal use case, but ``athlete_id``
    keeps the schema open to multiple athletes later on.
    """

    __tablename__ = "athlete_settings"
    __table_args__ = (UniqueConstraint("athlete_id", name="uq_athlete_settings_athlete_id"),)

    id = Column(Integer, primary_key=True)
    athlete_id = Column(String(64), nullable=False, default="default")

    # Bike: functional threshold power in watts (power-based TSS).
    ftp_watts = Column(Integer, nullable=True)

    # Run: threshold pace in seconds per kilometer (pace-based TSS).
    run_threshold_pace_seconds_per_km = Column(Float, nullable=True)

    # Swim: critical swim speed pace in seconds per 100 meters (CSS-based TSS).
    swim_css_pace_seconds_per_100m = Column(Float, nullable=True)

    # Heart-rate reference points and optional custom zone definitions.
    max_hr = Column(Integer, nullable=True)
    resting_hr = Column(Integer, nullable=True)
    threshold_hr = Column(Integer, nullable=True)
    hr_zones = Column(JSON, nullable=True)

    # Season planning targets (total TSS / hours for the calendar year).
    annual_tss_goal = Column(Float, nullable=True)
    annual_hours_goal = Column(Float, nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "athlete_id": self.athlete_id,
            "ftp_watts": self.ftp_watts,
            "run_threshold_pace_seconds_per_km": self.run_threshold_pace_seconds_per_km,
            "swim_css_pace_seconds_per_100m": self.swim_css_pace_seconds_per_100m,
            "max_hr": self.max_hr,
            "resting_hr": self.resting_hr,
            "threshold_hr": self.threshold_hr,
            "hr_zones": self.hr_zones,
            "annual_tss_goal": self.annual_tss_goal,
            "annual_hours_goal": self.annual_hours_goal,
        }


class AthleteSettingEntry(Base):
    """A single dated threshold value.

    Each row records that one threshold ``field`` took the given ``value`` as of
    ``effective_date``. The processing pipeline resolves the value in effect for
    any given activity date: the most recent entry on or before that date
    (forward-looking), falling back to the earliest entry for dates that precede
    every recorded value (backward-looking).
    """

    __tablename__ = "athlete_setting_entries"

    id = Column(Integer, primary_key=True)
    athlete_id = Column(String(64), nullable=False, default="default", index=True)
    field = Column(String(48), nullable=False, index=True)
    value = Column(Float, nullable=False)
    effective_date = Column(Date, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "athlete_id": self.athlete_id,
            "field": self.field,
            "value": self.value,
            "effective_date": self.effective_date.isoformat() if self.effective_date else None,
        }



class ActivityMetrics(Base):
    """Per-activity training-load values derived from raw activity data.

    ``discipline`` is the normalized sport bucket (``run``/``bike``/``swim``) and
    ``tss_method`` records how the value was derived (power/pace/hr/duration) so
    the dashboard can flag estimates.
    """

    __tablename__ = "activity_metrics"
    __table_args__ = (UniqueConstraint("activity_id", name="uq_activity_metrics_activity_id"),)

    id = Column(Integer, primary_key=True)
    activity_id = Column(String(64), nullable=False, index=True)

    discipline = Column(String(16), nullable=True)
    tss = Column(Float, nullable=True)
    intensity_factor = Column(Float, nullable=True)
    tss_method = Column(String(16), nullable=True)

    bike_tss = Column(Float, nullable=True)
    run_tss = Column(Float, nullable=True)
    swim_tss = Column(Float, nullable=True)

    zone_distribution = Column(JSON, nullable=True)

    computed_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "activity_id": self.activity_id,
            "discipline": self.discipline,
            "tss": self.tss,
            "intensity_factor": self.intensity_factor,
            "tss_method": self.tss_method,
            "bike_tss": self.bike_tss,
            "run_tss": self.run_tss,
            "swim_tss": self.swim_tss,
            "zone_distribution": self.zone_distribution,
        }


class WeeklyTraining(Base):
    """Weekly rollup used as the primary dashboard analytics table."""

    __tablename__ = "weekly_training"
    __table_args__ = (UniqueConstraint("week_start", name="uq_weekly_training_week_start"),)

    id = Column(Integer, primary_key=True)
    week_start = Column(Date, nullable=False, index=True)

    total_tss = Column(Float, nullable=True)
    bike_tss = Column(Float, nullable=True)
    run_tss = Column(Float, nullable=True)
    swim_tss = Column(Float, nullable=True)

    total_hours = Column(Float, nullable=True)
    bike_hours = Column(Float, nullable=True)
    run_hours = Column(Float, nullable=True)
    swim_hours = Column(Float, nullable=True)

    bike_distance = Column(Float, nullable=True)
    run_distance = Column(Float, nullable=True)
    swim_distance = Column(Float, nullable=True)

    ctl = Column(Float, nullable=True)
    atl = Column(Float, nullable=True)
    tsb = Column(Float, nullable=True)

    longest_run = Column(Float, nullable=True)
    longest_bike = Column(Float, nullable=True)
    longest_swim = Column(Float, nullable=True)

    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "week_start": self.week_start.isoformat() if self.week_start else None,
            "total_tss": self.total_tss,
            "bike_tss": self.bike_tss,
            "run_tss": self.run_tss,
            "swim_tss": self.swim_tss,
            "total_hours": self.total_hours,
            "bike_hours": self.bike_hours,
            "run_hours": self.run_hours,
            "swim_hours": self.swim_hours,
            "bike_distance": self.bike_distance,
            "run_distance": self.run_distance,
            "swim_distance": self.swim_distance,
            "ctl": self.ctl,
            "atl": self.atl,
            "tsb": self.tsb,
            "longest_run": self.longest_run,
            "longest_bike": self.longest_bike,
            "longest_swim": self.longest_swim,
        }
