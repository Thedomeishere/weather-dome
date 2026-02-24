from fastapi import APIRouter, Query

from app.schemas.weather import WeatherConditions, ZoneForecast, AlertSchema
from app.services.weather_ingest import (
    get_cached_current,
    get_cached_forecast,
    get_cached_alerts,
    get_all_cached_alerts,
)
from app.territory.definitions import ALL_ZONES, get_zones_for_territory

router = APIRouter(prefix="/weather", tags=["weather"])


@router.get("/current/", response_model=list[WeatherConditions])
async def get_current_weather(territory: str | None = Query(None, pattern="^(CONED|OR)$")):
    """Get current weather conditions for all zones (optionally filtered by territory)."""
    zones = get_zones_for_territory(territory) if territory else ALL_ZONES
    results = []
    for z in zones:
        w = get_cached_current(z.zone_id)
        if w:
            results.append(w)
    return results


@router.get("/current/{zone_id}", response_model=WeatherConditions | None)
async def get_zone_current(zone_id: str):
    return get_cached_current(zone_id)


@router.get("/forecast/{zone_id}", response_model=ZoneForecast | None)
async def get_zone_forecast(zone_id: str):
    return get_cached_forecast(zone_id)


@router.get("/alerts/", response_model=list[AlertSchema])
async def get_alerts(territory: str | None = Query(None, pattern="^(CONED|OR)$")):
    """Get all active weather alerts, optionally filtered by territory."""
    if not territory:
        return get_all_cached_alerts()

    zones = get_zones_for_territory(territory)
    alerts = []
    for z in zones:
        alerts.extend(get_cached_alerts(z.zone_id))
    return alerts
