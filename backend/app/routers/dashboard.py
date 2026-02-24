from datetime import datetime, timezone

from fastapi import APIRouter, Query

from app.config import settings
from app.schemas.dashboard import DashboardResponse, TerritoryOverview
from app.schemas.impact import CrewRecommendation
from app.services.impact_engine import get_territory_impacts, get_territory_forecast_impacts
from app.services.outage_ingest import get_territory_outages
from app.services.weather_ingest import get_cached_current, get_cached_alerts, get_cached_forecast
from app.territory.definitions import get_zones_for_territory

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard/", response_model=DashboardResponse)
async def get_dashboard(territory: str = Query("CONED", pattern="^(CONED|OR)$")):
    """Composite dashboard endpoint for a territory."""
    zones = get_zones_for_territory(territory)
    impacts = get_territory_impacts(territory)

    # Current weather for all zones
    weather_list = []
    for z in zones:
        w = get_cached_current(z.zone_id)
        if w:
            weather_list.append(w)

    # Alerts across territory
    alerts = []
    for z in zones:
        alerts.extend(get_cached_alerts(z.zone_id))

    # Forecast timeline from first zone (representative)
    forecast_points = []
    if zones:
        fc = get_cached_forecast(zones[0].zone_id)
        if fc:
            forecast_points = fc.points

    # Forecast impacts per zone
    forecast_impacts = get_territory_forecast_impacts(territory)

    # Crew summary
    crew_summary = [
        i.crew_recommendation for i in impacts
        if i.crew_recommendation is not None
    ]

    # Outage status
    outage_status = get_territory_outages(territory)

    # Build overview
    risk_scores = [i.overall_risk_score for i in impacts] if impacts else [0]
    max_risk = max(risk_scores)
    total_outages = sum(
        i.outage_risk.estimated_outages for i in impacts if i.outage_risk
    )
    load_pcts = [
        i.load_forecast.pct_capacity for i in impacts if i.load_forecast
    ]
    peak_load = max(load_pcts) if load_pcts else 0

    # Actual outages from live data
    total_actual_outages = sum(o.active_outages for o in outage_status)

    # Melt risk from impacts
    melt_scores = [i.melt_risk.score for i in impacts if i.melt_risk] if impacts else [0]
    max_melt = max(melt_scores) if melt_scores else 0

    overview = TerritoryOverview(
        territory=territory,
        overall_risk_level=_score_to_level(max_risk),
        overall_risk_score=round(max_risk, 1),
        active_alert_count=len(alerts),
        zones_at_risk=sum(1 for i in impacts if i.overall_risk_score >= 25),
        total_zones=len(zones),
        peak_load_pct=round(peak_load, 1),
        total_estimated_outages=total_outages,
        total_actual_outages=total_actual_outages,
        max_melt_risk_score=round(max_melt, 1),
        max_melt_risk_level=_score_to_level(max_melt),
    )

    return DashboardResponse(
        territory=territory,
        as_of=datetime.now(timezone.utc),
        poll_interval_seconds=settings.dashboard_poll_interval,
        overview=overview,
        zones=impacts,
        current_weather=weather_list,
        alerts=alerts,
        forecast_timeline=forecast_points,
        forecast_impacts=forecast_impacts,
        crew_summary=crew_summary,
        outage_status=outage_status,
    )


def _score_to_level(score: float) -> str:
    if score < 25:
        return "Low"
    if score < 50:
        return "Moderate"
    if score < 75:
        return "High"
    return "Extreme"
