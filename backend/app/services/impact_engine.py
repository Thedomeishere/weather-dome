"""Impact engine: orchestrates all impact models for a zone."""

import logging
import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.impact import ImpactAssessment
from app.schemas.impact import ForecastImpactPoint, ZoneImpact
from app.schemas.weather import AlertSchema, ForecastPoint, WeatherConditions
from app.services import outage_risk, vegetation_risk, load_forecast, equipment_stress, job_forecast, melt_risk, snow_tracker
from app.services.outage_ingest import get_cached_outages
from app.services.weather_ingest import get_cached_current, get_cached_forecast, get_cached_alerts, get_recent_observations
from app.territory.definitions import ALL_ZONES, ZoneDefinition, get_zones_for_territory

logger = logging.getLogger(__name__)

# In-memory cache for latest assessments
_impact_cache: dict[str, ZoneImpact] = {}
_forecast_impact_cache: dict[str, list[ForecastImpactPoint]] = {}

# Regex patterns for extracting snow amounts from NWS alert text
_SNOW_AMOUNT_RE = re.compile(
    r'(\d+)\s*(?:to|[-–])\s*(\d+)\s*inch', re.IGNORECASE,
)
_SNOW_SINGLE_RE = re.compile(
    r'(\d+)\s*inch(?:es)?\s*(?:of\s+)?(?:new\s+)?snow', re.IGNORECASE,
)

# Snow-related NWS alert event types (ordered by severity)
_SNOW_EVENT_DEPTHS: dict[str, float] = {
    "Blizzard Warning": 12.0,
    "Winter Storm Warning": 8.0,
    "Winter Weather Advisory": 4.0,
    "Winter Storm Watch": 6.0,
    "Snow Squall Warning": 3.0,
    "Special Weather Statement": 2.0,  # only if snow-related
}


def _estimate_snow_from_alerts(alerts: list[AlertSchema]) -> float:
    """Estimate snow depth on ground from NWS alert text.

    Fallback for when observation stations don't report snowDepth.
    Uses alert event type, severity, and text parsing.
    """
    if not alerts:
        return 0.0

    max_depth = 0.0

    for alert in alerts:
        text = f"{alert.headline or ''} {alert.description or ''}"
        text_lower = text.lower()

        # Skip non-snow alerts
        is_snow_related = any(kw in text_lower for kw in (
            "snow", "blizzard", "winter storm", "ice", "sleet",
            "snowmelt", "snow covered", "snow removal",
        ))
        if not is_snow_related:
            continue

        # Try to extract explicit amounts from text
        match = _SNOW_AMOUNT_RE.search(text)
        if match:
            high = float(match.group(2))
            max_depth = max(max_depth, high)
            continue

        match = _SNOW_SINGLE_RE.search(text)
        if match:
            max_depth = max(max_depth, float(match.group(1)))
            continue

        # Existing snow cover indicators boost estimate
        if "snowmelt" in text_lower or "snow covered" in text_lower:
            max_depth = max(max_depth, 3.0)

        # Fall back to event-type heuristic
        event_depth = _SNOW_EVENT_DEPTHS.get(alert.event, 0.0)
        max_depth = max(max_depth, event_depth)

    return max_depth


def _forecast_point_to_weather(fp: ForecastPoint, zone_id: str) -> WeatherConditions:
    """Adapt a ForecastPoint to WeatherConditions so impact models can run on it."""
    return WeatherConditions(
        zone_id=zone_id,
        source="forecast",
        observed_at=fp.forecast_for,
        temperature_f=fp.temperature_f,
        feels_like_f=fp.feels_like_f,
        humidity_pct=fp.humidity_pct,
        wind_speed_mph=fp.wind_speed_mph,
        wind_gust_mph=fp.wind_gust_mph,
        precip_probability_pct=fp.precip_probability_pct,
        precip_rate_in_hr=fp.precip_amount_in,
        snow_rate_in_hr=fp.snow_amount_in,
        snow_depth_in=fp.snow_depth_in,
        ice_accum_in=fp.ice_accum_in,
        lightning_probability_pct=fp.lightning_probability_pct,
        condition_text=fp.condition_text,
    )


def _estimate_initial_snow_depth(
    points: list[ForecastPoint], alerts: list[AlertSchema],
) -> float:
    """Estimate initial snow depth on the ground from all available signals.

    Scans the full forecast timeline for snow indicators to build the
    best estimate of existing snow cover. NWS NYC stations don't report
    snowDepth, so we combine:
    - Config override (highest priority — user knows ground truth)
    - Explicit snow_depth_in from any forecast point
    - Alert text with snow amounts
    - Condition text ("Light Snow" means snow IS on the ground)
    - Recent snowfall amounts from gridpoint data
    """
    # Check snow tracker first (dynamic, auto-decaying)
    # Use max across all zones as initial forecast depth
    all_depths = snow_tracker.get_all_depths()
    if all_depths:
        max_tracked = max(all_depths.values())
        if max_tracked > 0.1:
            return max_tracked

    from app.config import settings
    if settings.snow_depth_override_in > 0:
        return settings.snow_depth_override_in

    best_depth = 0.0

    # Check forecast points for explicit snow_depth or snow conditions
    total_snow_amount = 0.0
    snow_condition_severity = 0  # 0=none, 1=flurries, 2=light snow, 3=snow, 4=heavy/blizzard
    for fp in points[:24]:  # first 24h
        if fp.snow_depth_in is not None and fp.snow_depth_in > best_depth:
            best_depth = fp.snow_depth_in
        if fp.snow_amount_in is not None and fp.snow_amount_in > 0:
            total_snow_amount += fp.snow_amount_in
        cond = (fp.condition_text or "").lower()
        if "blizzard" in cond or "heavy snow" in cond:
            snow_condition_severity = max(snow_condition_severity, 4)
        elif "snow" in cond and "light" not in cond:
            snow_condition_severity = max(snow_condition_severity, 3)
        elif "light snow" in cond:
            snow_condition_severity = max(snow_condition_severity, 2)
        elif "flurries" in cond or "wintry" in cond:
            snow_condition_severity = max(snow_condition_severity, 1)

    # Alert-based estimate
    alert_snow = _estimate_snow_from_alerts(alerts)
    best_depth = max(best_depth, alert_snow)

    # If snow conditions are forecast but no explicit depth data, use conservative
    # inference. Calibrated against Feb 2026 NYC data: "Snow" conditions had
    # 0.3-0.9" actual NWS snow_depth, not 12"+ as previously assumed.
    # Only use condition inference if we didn't find explicit snow_depth.
    _CONDITION_SNOW_DEPTHS = {1: 0.5, 2: 1.5, 3: 3.0, 4: 6.0}
    if best_depth < 0.1:
        inferred = _CONDITION_SNOW_DEPTHS.get(snow_condition_severity, 0.0)
        best_depth = max(best_depth, inferred)

    # Add forecasted snowfall accumulation on top
    best_depth += total_snow_amount

    return best_depth


def compute_zone_forecast_impacts(
    zone: ZoneDefinition, points: list[ForecastPoint],
) -> list[ForecastImpactPoint]:
    """Run impact models every 3h through the forecast timeline.

    Maintains a running snow depth estimate that accumulates new snowfall
    and decays with temperature-based melt, so snow persists correctly
    through the entire 5-day forecast.
    """
    if not points:
        return []

    # Fetch 48h observation history so melt risk can see snow on ground
    observations = get_recent_observations(zone.zone_id, hours=48)

    # Build initial snow depth estimate from all available signals
    alerts = get_cached_alerts(zone.zone_id)
    running_snow_depth = _estimate_initial_snow_depth(points, alerts)
    # Per-zone effective melt threshold for snow decay calculation
    from app.services.melt_risk import EFFECTIVE_MELT_THRESHOLD
    effective_freezing = EFFECTIVE_MELT_THRESHOLD.get(zone.zone_id, 32.0)

    # Urban snowmelt acceleration factors: NYC plowing, salting, and dark surfaces
    # clear snow much faster than natural melt. Research: 2-3 days to clear most
    # urban snow vs 30+ days for natural melt alone.
    # NYC zones: 3x natural melt rate; suburban: 2x; rural O&R: 1.5x
    _URBAN_MELT_MULTIPLIER: dict[str, float] = {
        "CONED-MAN": 3.5, "CONED-BKN": 3.0, "CONED-QNS": 3.0,
        "CONED-BRX": 2.5, "CONED-SI": 2.0, "CONED-WST": 2.0,
        "OR-ORA": 1.5, "OR-ROC": 1.5, "OR-SUL": 1.2,
        "OR-BER": 1.5, "OR-SSX": 1.2,
    }
    urban_mult = _URBAN_MELT_MULTIPLIER.get(zone.zone_id, 1.5)

    # Get current outage count for this zone so forecast can project restoration
    outage_status = get_cached_outages(zone.zone_id)
    current_outages = outage_status.active_outages if outage_status else 0

    base_time = points[0].forecast_for
    prev_time = base_time
    prev_temp = points[0].temperature_f or 32.0
    results: list[ForecastImpactPoint] = []

    for i, fp in enumerate(points):
        temp = fp.temperature_f or 32.0

        # Update running snow depth: add new snowfall, subtract melt
        hours_elapsed = max(0.0, (fp.forecast_for - prev_time).total_seconds() / 3600)
        if hours_elapsed > 0:
            # Add new snowfall
            if fp.snow_amount_in and fp.snow_amount_in > 0:
                running_snow_depth += fp.snow_amount_in
            # Subtract temperature-based melt with urban acceleration
            # Base: 0.005 in/°F/hr × urban multiplier (plowing, salt, solar)
            if temp > effective_freezing:
                melt_rate = (temp - effective_freezing) * 0.005 * urban_mult
                running_snow_depth = max(0.0, running_snow_depth - melt_rate * hours_elapsed)
        prev_time = fp.forecast_for

        # Sample every 3 hours for impact computation
        if i % 3 != 0:
            continue

        weather = _forecast_point_to_weather(fp, zone.zone_id)
        # Apply running snow depth estimate
        weather = weather.model_copy(update={"snow_depth_in": running_snow_depth})

        # Decay current outages over the forecast horizon: outages resolve
        # over ~24-48h as crews restore service. Half-life of ~24h means
        # outages drop to ~50% by 24h and ~25% by 48h — realistic for
        # underground infrastructure where restoration is slow.
        hours_ahead = (fp.forecast_for - base_time).total_seconds() / 3600
        decay_factor = 0.5 ** (hours_ahead / 24.0)
        projected_outages = int(current_outages * decay_factor) if current_outages else None

        m_risk = melt_risk.compute(zone.zone_id, weather, observations=observations)
        o_risk = outage_risk.compute(
            weather,
            current_outages=projected_outages,
            melt_risk_score=m_risk.score,
        )
        v_risk = vegetation_risk.compute(weather)
        l_forecast_result = load_forecast.compute(weather, zone)
        e_stress = equipment_stress.compute(
            weather, zone, load_pct=l_forecast_result.pct_capacity / 100,
        )

        # Adaptive weights: include melt when non-trivial
        if m_risk.score > 5:
            overall_score = (
                o_risk.score * 0.25
                + m_risk.score * 0.25
                + (l_forecast_result.pct_capacity - 40) * 0.6 * 0.15
                + v_risk.score * 0.15
                + e_stress.score * 0.20
            )
        else:
            overall_score = (
                o_risk.score * 0.40
                + v_risk.score * 0.17
                + (l_forecast_result.pct_capacity - 40) * 0.6 * 0.23
                + e_stress.score * 0.20
            )
        overall_score = max(0, min(100, overall_score))

        hours_ahead_int = int(hours_ahead)

        # Compute job count ranges using combined outage + melt risk.
        # Reduced melt coefficient (0.4 from 0.6) to prevent over-prediction.
        combined_score = max(o_risk.score, m_risk.score * 0.4 + o_risk.score * 0.6)
        redundancy = job_forecast.NETWORK_REDUNDANCY_DISCOUNT.get(zone.zone_id, 0.5)
        weather_jobs = job_forecast._estimate_jobs(combined_score, redundancy)
        low_mult, high_mult = job_forecast._uncertainty_band(o_risk)
        # Widen uncertainty when melt is a major driver (harder to predict)
        if m_risk.score > 30:
            low_mult = min(low_mult, 0.4)
            high_mult = max(high_mult, 2.0)

        # Baseline job floor: even in calm weather, baseline outages
        # (equipment aging, animal contact, vehicle strikes, dig-ins)
        # always generate restoration crew work. ~0.3 jobs per baseline outage.
        # Modulate by time-of-day: crews work more during day shifts.
        baseline = outage_risk.BASELINE_OUTAGES.get(zone.zone_id, 5)
        hour_of_day = fp.forecast_for.hour if fp.forecast_for else 12
        # Day shift (7am-7pm): full staffing. Night (11pm-5am): ~50%. Transition hours: ~75%.
        if 7 <= hour_of_day < 19:
            staffing = 1.0
        elif 19 <= hour_of_day < 23:
            staffing = 0.75
        elif 5 <= hour_of_day < 7:
            staffing = 0.75
        else:
            staffing = 0.5
        baseline_jobs = int(baseline * 0.3 * staffing)

        mid_jobs = max(weather_jobs, baseline_jobs)
        jobs_low = max(0, int(mid_jobs * low_mult))
        jobs_high = int(mid_jobs * high_mult)

        results.append(ForecastImpactPoint(
            forecast_for=fp.forecast_for,
            forecast_hour=hours_ahead_int,
            overall_risk_score=round(overall_score, 1),
            overall_risk_level=_score_to_level(overall_score),
            outage_risk_score=round(o_risk.score, 1),
            estimated_outages=o_risk.estimated_outages,
            estimated_outages_low=jobs_low,
            estimated_outages_high=jobs_high,
            estimated_jobs_low=jobs_low,
            estimated_jobs_mid=mid_jobs,
            estimated_jobs_high=jobs_high,
            vegetation_risk_score=round(v_risk.score, 1),
            load_pct_capacity=round(l_forecast_result.pct_capacity, 1),
            equipment_stress_score=round(e_stress.score, 1),
            melt_risk_score=round(m_risk.score, 1),
        ))

    return results


def compute_zone_impact(zone: ZoneDefinition, weather: WeatherConditions) -> ZoneImpact:
    """Run all impact models for a single zone given current weather."""
    # Fetch 48h observation history for melt risk model
    observations = get_recent_observations(zone.zone_id, hours=48)

    # Snow depth priority: snow tracker (dynamic) > config override > API > estimation
    tracked_depth = snow_tracker.get_snow_depth(zone.zone_id)
    from app.config import settings as _settings
    if tracked_depth is not None and tracked_depth > 0:
        # Update tracker with current temp to apply melt decay
        temp = weather.temperature_f or 32.0
        # ~30 min between cycles
        updated_depth = snow_tracker.update_snow_depth(zone.zone_id, temp, 0.5)
        weather = weather.model_copy(update={"snow_depth_in": updated_depth})
    elif _settings.snow_depth_override_in > 0:
        # Static override — initialize the tracker with it so it starts decaying
        snow_tracker.set_all_zones(_settings.snow_depth_override_in)
        weather = weather.model_copy(update={"snow_depth_in": _settings.snow_depth_override_in})
    elif weather.snow_depth_in is None or weather.snow_depth_in == 0:
        alerts = get_cached_alerts(zone.zone_id)
        alert_snow = _estimate_snow_from_alerts(alerts)

        # Also check forecast data for snow indicators
        forecast = get_cached_forecast(zone.zone_id)
        forecast_snow = 0.0
        if forecast and forecast.points:
            forecast_snow = _estimate_initial_snow_depth(forecast.points, alerts)

        best_snow = max(alert_snow, forecast_snow)
        if best_snow > 0:
            weather = weather.model_copy(update={"snow_depth_in": best_snow})

    # Compute melt risk with observation history
    m_risk = melt_risk.compute(zone.zone_id, weather, observations=observations)

    # Get live outage data for the zone
    outage_status = get_cached_outages(zone.zone_id)
    current_outages = outage_status.active_outages if outage_status else None

    o_risk = outage_risk.compute(
        weather,
        current_outages=current_outages,
        melt_risk_score=m_risk.score,
    )
    v_risk = vegetation_risk.compute(weather)
    l_forecast = load_forecast.compute(weather, zone)
    e_stress = equipment_stress.compute(weather, zone, load_pct=l_forecast.pct_capacity / 100)
    j_forecast = job_forecast.compute(o_risk, zone, melt_risk_score=m_risk.score)

    # Adaptive weights: include melt when non-trivial
    if m_risk.score > 5:
        overall_score = (
            o_risk.score * 0.25
            + m_risk.score * 0.25
            + (l_forecast.pct_capacity - 40) * 0.6 * 0.15
            + v_risk.score * 0.15
            + e_stress.score * 0.20
        )
    else:
        overall_score = (
            o_risk.score * 0.40
            + v_risk.score * 0.17
            + (l_forecast.pct_capacity - 40) * 0.6 * 0.23
            + e_stress.score * 0.20
        )
    overall_score = max(0, min(100, overall_score))

    overall_level = _score_to_level(overall_score)
    summary = _build_summary(zone, o_risk, v_risk, l_forecast, e_stress, m_risk, j_forecast, overall_level)

    return ZoneImpact(
        zone_id=zone.zone_id,
        zone_name=zone.name,
        territory=zone.territory,
        assessed_at=datetime.now(timezone.utc),
        overall_risk_score=round(overall_score, 1),
        overall_risk_level=overall_level,
        outage_risk=o_risk,
        vegetation_risk=v_risk,
        load_forecast=l_forecast,
        equipment_stress=e_stress,
        job_count_estimate=j_forecast,
        melt_risk=m_risk,
        summary_text=summary,
    )


async def compute_all_zones():
    """Recompute impact assessments for all zones using cached weather."""
    logger.info("Starting impact computation for %d zones", len(ALL_ZONES))

    for zone in ALL_ZONES:
        weather = get_cached_current(zone.zone_id)
        if not weather:
            weather = WeatherConditions(
                zone_id=zone.zone_id,
                source="default",
                observed_at=datetime.now(timezone.utc),
                temperature_f=65.0,
                wind_speed_mph=5.0,
            )

        impact = compute_zone_impact(zone, weather)
        _impact_cache[zone.zone_id] = impact
        _persist_impact(zone, impact)

        # Compute forecast impacts
        forecast = get_cached_forecast(zone.zone_id)
        if forecast and forecast.points:
            fi = compute_zone_forecast_impacts(zone, forecast.points)
            _forecast_impact_cache[zone.zone_id] = fi

    logger.info("Impact computation complete")


def _persist_impact(zone: ZoneDefinition, impact: ZoneImpact):
    db: Session = SessionLocal()
    try:
        assessment = ImpactAssessment(
            zone_id=zone.zone_id,
            territory=zone.territory,
            assessed_at=impact.assessed_at,
            outage_risk_score=impact.outage_risk.score if impact.outage_risk else None,
            outage_risk_level=impact.outage_risk.level if impact.outage_risk else None,
            estimated_outages=impact.outage_risk.estimated_outages if impact.outage_risk else None,
            vegetation_risk_score=impact.vegetation_risk.score if impact.vegetation_risk else None,
            vegetation_risk_level=impact.vegetation_risk.level if impact.vegetation_risk else None,
            load_forecast_mw=impact.load_forecast.load_mw if impact.load_forecast else None,
            load_pct_capacity=impact.load_forecast.pct_capacity if impact.load_forecast else None,
            load_risk_level=impact.load_forecast.risk_level if impact.load_forecast else None,
            equipment_stress_score=impact.equipment_stress.score if impact.equipment_stress else None,
            equipment_stress_level=impact.equipment_stress.level if impact.equipment_stress else None,
            transformer_risk=impact.equipment_stress.transformer_risk if impact.equipment_stress else None,
            line_sag_risk=impact.equipment_stress.line_sag_risk if impact.equipment_stress else None,
            job_count_estimate=impact.job_count_estimate.model_dump() if impact.job_count_estimate else None,
            overall_risk_level=impact.overall_risk_level,
            overall_risk_score=impact.overall_risk_score,
            summary_text=impact.summary_text,
        )
        db.add(assessment)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("Failed to persist impact for %s: %s", zone.zone_id, e)
    finally:
        db.close()


def get_cached_impact(zone_id: str) -> ZoneImpact | None:
    return _impact_cache.get(zone_id)


def get_territory_impacts(territory: str) -> list[ZoneImpact]:
    zones = get_zones_for_territory(territory)
    return [_impact_cache[z.zone_id] for z in zones if z.zone_id in _impact_cache]


def get_cached_forecast_impacts(zone_id: str) -> list[ForecastImpactPoint]:
    return _forecast_impact_cache.get(zone_id, [])


def get_territory_forecast_impacts(territory: str) -> dict[str, list[ForecastImpactPoint]]:
    zones = get_zones_for_territory(territory)
    return {
        z.zone_id: _forecast_impact_cache[z.zone_id]
        for z in zones if z.zone_id in _forecast_impact_cache
    }


def _score_to_level(score: float) -> str:
    if score < 25:
        return "Low"
    if score < 50:
        return "Moderate"
    if score < 75:
        return "High"
    return "Extreme"


def _build_summary(zone, o_risk, v_risk, l_forecast, e_stress, m_risk, j_forecast, level):
    parts = [f"{zone.name}: {level} overall risk."]
    if o_risk.score > 30:
        parts.append(f"Outage risk {o_risk.level} ({o_risk.estimated_outages} est. outages).")
    if j_forecast.estimated_jobs_mid > 0:
        parts.append(
            f"Predicted jobs: {j_forecast.estimated_jobs_low}-{j_forecast.estimated_jobs_high}"
            f" (mid {j_forecast.estimated_jobs_mid})."
        )
    if v_risk.score > 30:
        parts.append(f"Vegetation risk {v_risk.level}.")
    if l_forecast.pct_capacity > 80:
        parts.append(f"Load at {l_forecast.pct_capacity}% capacity.")
    if e_stress.score > 30:
        parts.append(f"Equipment stress {e_stress.level}.")
    if m_risk.score > 20:
        parts.append(f"Underground melt risk {m_risk.level}.")
    return " ".join(parts)
