import logging
from datetime import datetime, timezone

import httpx

from app.config import settings
from app.schemas.weather import WeatherConditions, ForecastPoint, ZoneForecast
from app.territory.definitions import ZoneDefinition

logger = logging.getLogger(__name__)

VC_BASE = "https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline"


async def fetch_current(zone: ZoneDefinition) -> WeatherConditions | None:
    """Fetch current conditions from Visual Crossing Timeline API."""
    if not settings.visual_crossing_api_key:
        return None

    location = f"{zone.latitude},{zone.longitude}"
    url = f"{VC_BASE}/{location}/today"
    params = {
        "key": settings.visual_crossing_api_key,
        "unitGroup": "us",
        "include": "current",
        "contentType": "json",
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            current = data.get("currentConditions", {})

            return WeatherConditions(
                zone_id=zone.zone_id,
                source="visual_crossing",
                observed_at=datetime.now(timezone.utc),
                temperature_f=current.get("temp"),
                feels_like_f=current.get("feelslike"),
                humidity_pct=current.get("humidity"),
                wind_speed_mph=current.get("windspeed"),
                wind_gust_mph=current.get("windgust"),
                wind_direction_deg=current.get("winddir"),
                precip_rate_in_hr=current.get("precip"),
                precip_probability_pct=current.get("precipprob"),
                snow_rate_in_hr=current.get("snow"),
                visibility_mi=current.get("visibility"),
                cloud_cover_pct=current.get("cloudcover"),
                pressure_mb=current.get("pressure"),
                condition_text=current.get("conditions"),
            )
    except Exception as e:
        logger.warning("Visual Crossing current fetch failed for %s: %s", zone.zone_id, e)
        return None


async def fetch_forecast(zone: ZoneDefinition) -> ZoneForecast | None:
    """Fetch hourly forecast from Visual Crossing."""
    if not settings.visual_crossing_api_key:
        return None

    location = f"{zone.latitude},{zone.longitude}"
    url = f"{VC_BASE}/{location}/next5days"
    params = {
        "key": settings.visual_crossing_api_key,
        "unitGroup": "us",
        "include": "hours",
        "contentType": "json",
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            now = datetime.now(timezone.utc)

            points = []
            for day in data.get("days", []):
                date_str = day.get("datetime", "")
                for h in day.get("hours", []):
                    hour_str = h.get("datetime", "00:00:00")
                    try:
                        dt = datetime.fromisoformat(f"{date_str}T{hour_str}")
                        dt = dt.replace(tzinfo=timezone.utc)
                    except ValueError:
                        continue

                    points.append(ForecastPoint(
                        forecast_for=dt,
                        temperature_f=h.get("temp"),
                        feels_like_f=h.get("feelslike"),
                        humidity_pct=h.get("humidity"),
                        wind_speed_mph=h.get("windspeed"),
                        wind_gust_mph=h.get("windgust"),
                        precip_probability_pct=h.get("precipprob"),
                        precip_amount_in=h.get("precip"),
                        snow_amount_in=h.get("snow"),
                        ice_accum_in=h.get("iceaccum"),
                        lightning_probability_pct=h.get("lightningprob"),
                        condition_text=h.get("conditions"),
                    ))

            return ZoneForecast(
                zone_id=zone.zone_id,
                source="visual_crossing",
                fetched_at=now,
                points=points[:120],
            )
    except Exception as e:
        logger.warning("Visual Crossing forecast fetch failed for %s: %s", zone.zone_id, e)
        return None
