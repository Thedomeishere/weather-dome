"""Impact engine: orchestrates all impact models for a zone."""

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.impact import ImpactAssessment
from app.schemas.impact import ForecastImpactPoint, ZoneImpact
from app.schemas.weather import ForecastPoint, WeatherConditions
from app.services import outage_risk, vegetation_risk, load_forecast, equipment_stress, crew_deployment, melt_risk
from app.services.outage_ingest import get_cached_outages
from app.services.weather_ingest import get_cached_current, get_cached_forecast
from app.territory.definitions import ALL_ZONES, ZoneDefinition, get_zones_for_territory

logger = logging.getLogger(__name__)

# In-memory cache for latest assessments
_impact_cache: dict[str, ZoneImpact] = {}
_forecast_impact_cache: dict[str, list[ForecastImpactPoint]] = {}


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
        ice_accum_in=fp.ice_accum_in,
        lightning_probability_pct=fp.lightning_probability_pct,
        condition_text=fp.condition_text,
    )


def compute_zone_forecast_impacts(
    zone: ZoneDefinition, points: list[ForecastPoint],
) -> list[ForecastImpactPoint]:
    """Run impact models every 3h through the forecast timeline."""
    if not points:
        return []

    base_time = points[0].forecast_for
    results: list[ForecastImpactPoint] = []

    for i, fp in enumerate(points):
        # Sample every 3 hours
        if i % 3 != 0:
            continue

        weather = _forecast_point_to_weather(fp, zone.zone_id)
        m_risk = melt_risk.compute(zone.zone_id, weather)
        o_risk = outage_risk.compute(weather, melt_risk_score=m_risk.score)
        v_risk = vegetation_risk.compute(weather)
        l_forecast_result = load_forecast.compute(weather, zone)
        e_stress = equipment_stress.compute(
            weather, zone, load_pct=l_forecast_result.pct_capacity / 100,
        )

        # Adaptive weights: include melt when non-trivial
        if m_risk.score > 5:
            overall_score = (
                o_risk.score * 0.30
                + m_risk.score * 0.10
                + (l_forecast_result.pct_capacity - 40) * 0.6 * 0.18
                + v_risk.score * 0.13
                + e_stress.score * 0.14
                + 0  # no crew proxy for forecast
            )
        else:
            overall_score = (
                o_risk.score * 0.35
                + v_risk.score * 0.15
                + (l_forecast_result.pct_capacity - 40) * 0.6 * 0.20
                + e_stress.score * 0.15
                + 0  # no crew proxy for forecast
            )
        overall_score = max(0, min(100, overall_score))

        hours_ahead = int((fp.forecast_for - base_time).total_seconds() / 3600)

        results.append(ForecastImpactPoint(
            forecast_for=fp.forecast_for,
            forecast_hour=hours_ahead,
            overall_risk_score=round(overall_score, 1),
            overall_risk_level=_score_to_level(overall_score),
            outage_risk_score=round(o_risk.score, 1),
            estimated_outages=o_risk.estimated_outages,
            vegetation_risk_score=round(v_risk.score, 1),
            load_pct_capacity=round(l_forecast_result.pct_capacity, 1),
            equipment_stress_score=round(e_stress.score, 1),
            melt_risk_score=round(m_risk.score, 1),
        ))

    return results


def compute_zone_impact(zone: ZoneDefinition, weather: WeatherConditions) -> ZoneImpact:
    """Run all impact models for a single zone given current weather."""
    # Compute melt risk
    m_risk = melt_risk.compute(zone.zone_id, weather)

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
    c_deploy = crew_deployment.compute(zone, o_risk, v_risk)

    # Adaptive weights: include melt when non-trivial
    if m_risk.score > 5:
        overall_score = (
            o_risk.score * 0.30
            + m_risk.score * 0.10
            + (l_forecast.pct_capacity - 40) * 0.6 * 0.18
            + v_risk.score * 0.13
            + e_stress.score * 0.14
            + min(100, c_deploy.total_crews * 5) * 0.15
        )
    else:
        overall_score = (
            o_risk.score * 0.35
            + v_risk.score * 0.15
            + (l_forecast.pct_capacity - 40) * 0.6 * 0.20  # normalize load contribution
            + e_stress.score * 0.15
            + min(100, c_deploy.total_crews * 5) * 0.15  # crew need as proxy
        )
    overall_score = max(0, min(100, overall_score))

    overall_level = _score_to_level(overall_score)
    summary = _build_summary(zone, o_risk, v_risk, l_forecast, e_stress, m_risk, overall_level)

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
        crew_recommendation=c_deploy,
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
            crew_recommendation=impact.crew_recommendation.model_dump() if impact.crew_recommendation else None,
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


def _build_summary(zone, o_risk, v_risk, l_forecast, e_stress, m_risk, level):
    parts = [f"{zone.name}: {level} overall risk."]
    if o_risk.score > 30:
        parts.append(f"Outage risk {o_risk.level} ({o_risk.estimated_outages} est. outages).")
    if v_risk.score > 30:
        parts.append(f"Vegetation risk {v_risk.level}.")
    if l_forecast.pct_capacity > 80:
        parts.append(f"Load at {l_forecast.pct_capacity}% capacity.")
    if e_stress.score > 30:
        parts.append(f"Equipment stress {e_stress.level}.")
    if m_risk.score > 20:
        parts.append(f"Underground melt risk {m_risk.level}.")
    return " ".join(parts)
