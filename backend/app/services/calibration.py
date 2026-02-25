"""Automated calibration service.

Runs 2x/day via cron to compare predicted vs actual outages and compute
correction factors stored in the outage_weather_correlations table.

The correction factors are read by outage_risk._estimate_outages() and
job_forecast._estimate_jobs() to adjust predictions based on real data.
"""

import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func as sqlfunc
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.impact import ImpactAssessment
from app.models.outage import OutageSnapshot, OutageWeatherCorrelation
from app.models.weather import WeatherObservation

logger = logging.getLogger(__name__)

# Minimum data points needed per zone to compute calibration
MIN_SNAPSHOTS = 5
MIN_ASSESSMENTS = 3


def run_calibration():
    """Main calibration entry point.

    1. Gather recent outage snapshots and impact assessments per zone
    2. Compute predicted-vs-actual ratios
    3. Derive correction factors
    4. Store in outage_weather_correlations table
    5. Log a calibration report
    """
    db: Session = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        lookback = now - timedelta(hours=24)

        zones = _get_active_zones(db, lookback)
        if not zones:
            logger.info("Calibration: no zones with recent data, skipping")
            return

        report_lines = [f"=== Calibration Report {now.strftime('%Y-%m-%d %H:%M UTC')} ==="]

        for zone_id in zones:
            result = _calibrate_zone(db, zone_id, lookback, now)
            if result:
                report_lines.append(result)

        report = "\n".join(report_lines)
        logger.info(report)
        print(report)

    except Exception as e:
        logger.error("Calibration failed: %s", e)
        raise
    finally:
        db.close()


def _get_active_zones(db: Session, since: datetime) -> list[str]:
    """Get zones that have recent outage snapshots."""
    rows = (
        db.query(OutageSnapshot.zone_id)
        .filter(OutageSnapshot.snapshot_at >= since)
        .group_by(OutageSnapshot.zone_id)
        .having(sqlfunc.count() >= MIN_SNAPSHOTS)
        .all()
    )
    return [r[0] for r in rows]


def _calibrate_zone(
    db: Session, zone_id: str, since: datetime, now: datetime,
) -> str | None:
    """Compute calibration for a single zone and store it."""

    # --- Gather actual outage data ---
    snapshots = (
        db.query(OutageSnapshot)
        .filter(
            OutageSnapshot.zone_id == zone_id,
            OutageSnapshot.snapshot_at >= since,
            OutageSnapshot.outage_count > 0,
        )
        .order_by(OutageSnapshot.snapshot_at.desc())
        .all()
    )
    if len(snapshots) < MIN_SNAPSHOTS:
        return None

    actual_avg = sum(s.outage_count for s in snapshots) / len(snapshots)
    actual_max = max(s.outage_count for s in snapshots)
    actual_min = min(s.outage_count for s in snapshots)

    # --- Gather predicted data ---
    assessments = (
        db.query(ImpactAssessment)
        .filter(
            ImpactAssessment.zone_id == zone_id,
            ImpactAssessment.assessed_at >= since,
            ImpactAssessment.forecast_hour == 0,  # current assessments only
        )
        .order_by(ImpactAssessment.assessed_at.desc())
        .all()
    )
    if len(assessments) < MIN_ASSESSMENTS:
        return None

    predicted_outages = [
        a.estimated_outages for a in assessments
        if a.estimated_outages is not None
    ]
    predicted_scores = [
        a.outage_risk_score for a in assessments
        if a.outage_risk_score is not None
    ]

    if not predicted_outages or not predicted_scores:
        return None

    predicted_avg = sum(predicted_outages) / len(predicted_outages)
    score_avg = sum(predicted_scores) / len(predicted_scores)

    # --- Gather weather correlations ---
    obs = (
        db.query(WeatherObservation)
        .filter(
            WeatherObservation.zone_id == zone_id,
            WeatherObservation.observed_at >= since,
        )
        .all()
    )

    wind_avg = _safe_avg([o.wind_speed_mph for o in obs if o.wind_speed_mph])
    temp_avg = _safe_avg([o.temperature_f for o in obs if o.temperature_f])
    precip_avg = _safe_avg([o.precip_rate_in_hr for o in obs if o.precip_rate_in_hr])
    snow_avg = _safe_avg([o.snow_rate_in_hr for o in obs if o.snow_rate_in_hr])
    ice_avg = _safe_avg([o.ice_accum_in for o in obs if o.ice_accum_in])

    # --- Compute correction factor ---
    # Ratio of actual/predicted: >1 means we under-predict, <1 means over-predict
    if predicted_avg > 0:
        correction_ratio = actual_avg / predicted_avg
    else:
        correction_ratio = 1.0

    # Clamp to reasonable range [0.3, 3.0] to prevent wild swings
    correction_ratio = max(0.3, min(3.0, correction_ratio))

    # Job prediction accuracy (from job_count_estimate JSON)
    job_predictions = []
    for a in assessments:
        if a.job_count_estimate and isinstance(a.job_count_estimate, dict):
            mid = a.job_count_estimate.get("estimated_jobs_mid", 0)
            if mid is not None:
                job_predictions.append(mid)

    job_avg = sum(job_predictions) / len(job_predictions) if job_predictions else 0

    # --- Store calibration ---
    calibrated = {
        "outage_correction_ratio": round(correction_ratio, 3),
        "actual_outage_avg": round(actual_avg, 1),
        "actual_outage_max": actual_max,
        "actual_outage_min": actual_min,
        "predicted_outage_avg": round(predicted_avg, 1),
        "predicted_score_avg": round(score_avg, 1),
        "predicted_jobs_avg": round(job_avg, 1),
        "observation_count": len(obs),
        "snapshot_count": len(snapshots),
        "assessment_count": len(assessments),
        "wind_avg_mph": round(wind_avg, 1) if wind_avg else None,
        "temp_avg_f": round(temp_avg, 1) if temp_avg else None,
        "precip_avg_in_hr": round(precip_avg, 3) if precip_avg else None,
    }

    # Simple weather-outage correlations (Pearson-like using available data)
    wind_corr = _compute_correlation(obs, snapshots, "wind_speed_mph")
    temp_corr = _compute_correlation(obs, snapshots, "temperature_f")

    correlation = OutageWeatherCorrelation(
        zone_id=zone_id,
        computed_at=now,
        wind_correlation=wind_corr,
        ice_correlation=None,  # insufficient ice data typically
        precip_correlation=None,
        snow_correlation=None,
        temp_correlation=temp_corr,
        calibrated_coefficients=calibrated,
    )
    db.add(correlation)
    db.commit()

    # --- Build report line ---
    ratio_label = "OVER" if correction_ratio < 0.9 else "UNDER" if correction_ratio > 1.1 else "OK"
    return (
        f"  {zone_id}: actual_avg={actual_avg:.0f} predicted_avg={predicted_avg:.0f} "
        f"ratio={correction_ratio:.2f} ({ratio_label}) "
        f"jobs_avg={job_avg:.0f} score_avg={score_avg:.1f} "
        f"snaps={len(snapshots)} assessments={len(assessments)}"
    )


def _safe_avg(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _compute_correlation(
    obs: list[WeatherObservation],
    snapshots: list[OutageSnapshot],
    weather_field: str,
) -> float | None:
    """Compute simple correlation between a weather field and outage counts.

    Pairs observations and snapshots by closest timestamp within 30 min.
    Returns correlation coefficient or None if insufficient pairs.
    """
    pairs = []
    for snap in snapshots:
        # Find closest observation within 30 min
        best_obs = None
        best_delta = timedelta(minutes=30)
        for o in obs:
            if o.observed_at is None or snap.snapshot_at is None:
                continue
            try:
                delta = abs(o.observed_at - snap.snapshot_at)
            except TypeError:
                continue
            if delta < best_delta:
                val = getattr(o, weather_field, None)
                if val is not None:
                    best_delta = delta
                    best_obs = o

        if best_obs is not None:
            val = getattr(best_obs, weather_field, None)
            if val is not None:
                pairs.append((val, snap.outage_count))

    if len(pairs) < 5:
        return None

    # Pearson correlation
    n = len(pairs)
    x_vals = [p[0] for p in pairs]
    y_vals = [p[1] for p in pairs]
    x_mean = sum(x_vals) / n
    y_mean = sum(y_vals) / n

    numerator = sum((x - x_mean) * (y - y_mean) for x, y in pairs)
    x_var = sum((x - x_mean) ** 2 for x in x_vals)
    y_var = sum((y - y_mean) ** 2 for y in y_vals)

    denominator = (x_var * y_var) ** 0.5
    if denominator == 0:
        return 0.0

    return round(numerator / denominator, 4)


def get_latest_calibration(zone_id: str) -> dict | None:
    """Read the most recent calibration for a zone.

    Returns the calibrated_coefficients dict or None.
    """
    db: Session = SessionLocal()
    try:
        row = (
            db.query(OutageWeatherCorrelation)
            .filter(OutageWeatherCorrelation.zone_id == zone_id)
            .order_by(OutageWeatherCorrelation.computed_at.desc())
            .first()
        )
        if row and row.calibrated_coefficients:
            return row.calibrated_coefficients
        return None
    except Exception:
        return None
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    run_calibration()
