"""Impact engine: orchestrates all 5 impact models for a zone."""

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.impact import ImpactAssessment
from app.schemas.impact import ZoneImpact
from app.schemas.weather import WeatherConditions
from app.services import outage_risk, vegetation_risk, load_forecast, equipment_stress, crew_deployment
from app.services.weather_ingest import get_cached_current
from app.territory.definitions import ALL_ZONES, ZoneDefinition, get_zones_for_territory

logger = logging.getLogger(__name__)

# In-memory cache for latest assessments
_impact_cache: dict[str, ZoneImpact] = {}


def compute_zone_impact(zone: ZoneDefinition, weather: WeatherConditions) -> ZoneImpact:
    """Run all impact models for a single zone given current weather."""
    o_risk = outage_risk.compute(weather)
    v_risk = vegetation_risk.compute(weather)
    l_forecast = load_forecast.compute(weather, zone)
    e_stress = equipment_stress.compute(weather, zone, load_pct=l_forecast.pct_capacity / 100)
    c_deploy = crew_deployment.compute(zone, o_risk, v_risk)

    overall_score = (
        o_risk.score * 0.35
        + v_risk.score * 0.15
        + (l_forecast.pct_capacity - 40) * 0.6 * 0.20  # normalize load contribution
        + e_stress.score * 0.15
        + min(100, c_deploy.total_crews * 5) * 0.15  # crew need as proxy
    )
    overall_score = max(0, min(100, overall_score))

    overall_level = _score_to_level(overall_score)
    summary = _build_summary(zone, o_risk, v_risk, l_forecast, e_stress, overall_level)

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


def _score_to_level(score: float) -> str:
    if score < 25:
        return "Low"
    if score < 50:
        return "Moderate"
    if score < 75:
        return "High"
    return "Extreme"


def _build_summary(zone, o_risk, v_risk, l_forecast, e_stress, level):
    parts = [f"{zone.name}: {level} overall risk."]
    if o_risk.score > 30:
        parts.append(f"Outage risk {o_risk.level} ({o_risk.estimated_outages} est. outages).")
    if v_risk.score > 30:
        parts.append(f"Vegetation risk {v_risk.level}.")
    if l_forecast.pct_capacity > 80:
        parts.append(f"Load at {l_forecast.pct_capacity}% capacity.")
    if e_stress.score > 30:
        parts.append(f"Equipment stress {e_stress.level}.")
    return " ".join(parts)
