import logging
from datetime import datetime, timezone

import httpx

from app.config import settings
from app.schemas.weather import WeatherConditions, ForecastPoint, ZoneForecast
from app.territory.definitions import ZoneDefinition

logger = logging.getLogger(__name__)

OWM_BASE = "https://api.openweathermap.org/data/3.0/onecall"


async def fetch_current(zone: ZoneDefinition) -> WeatherConditions | None:
    """Fetch current weather from OpenWeatherMap One Call API."""
    if not settings.owm_api_key:
        return None

    params = {
        "lat": zone.latitude,
        "lon": zone.longitude,
        "appid": settings.owm_api_key,
        "units": "imperial",
        "exclude": "minutely",
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(OWM_BASE, params=params)
            resp.raise_for_status()
            data = resp.json()
            current = data.get("current", {})

            # OWM snow object: {"1h": mm} — convert mm to inches
            snow_obj = current.get("snow", {})
            snow_1h_mm = snow_obj.get("1h", 0) if isinstance(snow_obj, dict) else 0
            snow_rate_in = round(snow_1h_mm / 25.4, 2) if snow_1h_mm else None

            return WeatherConditions(
                zone_id=zone.zone_id,
                source="owm",
                observed_at=datetime.fromtimestamp(current["dt"], tz=timezone.utc),
                temperature_f=current.get("temp"),
                feels_like_f=current.get("feels_like"),
                humidity_pct=current.get("humidity"),
                wind_speed_mph=current.get("wind_speed"),
                wind_gust_mph=current.get("wind_gust"),
                wind_direction_deg=current.get("wind_deg"),
                snow_rate_in_hr=snow_rate_in,
                visibility_mi=_m_to_mi(current.get("visibility")),
                cloud_cover_pct=current.get("clouds"),
                pressure_mb=current.get("pressure"),
                condition_text=current.get("weather", [{}])[0].get("description"),
            )
    except Exception as e:
        logger.warning("OWM current fetch failed for %s: %s", zone.zone_id, e)
        return None


async def fetch_forecast(zone: ZoneDefinition) -> ZoneForecast | None:
    """Fetch hourly forecast from OWM One Call API."""
    if not settings.owm_api_key:
        return None

    params = {
        "lat": zone.latitude,
        "lon": zone.longitude,
        "appid": settings.owm_api_key,
        "units": "imperial",
        "exclude": "minutely,current",
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(OWM_BASE, params=params)
            resp.raise_for_status()
            data = resp.json()
            now = datetime.now(timezone.utc)

            points = []
            for h in data.get("hourly", []):
                h_snow = h.get("snow", {})
                h_snow_mm = h_snow.get("1h", 0) if isinstance(h_snow, dict) else 0
                h_snow_in = round(h_snow_mm / 25.4, 2) if h_snow_mm else None
                points.append(ForecastPoint(
                    forecast_for=datetime.fromtimestamp(h["dt"], tz=timezone.utc),
                    temperature_f=h.get("temp"),
                    feels_like_f=h.get("feels_like"),
                    humidity_pct=h.get("humidity"),
                    wind_speed_mph=h.get("wind_speed"),
                    wind_gust_mph=h.get("wind_gust"),
                    precip_probability_pct=(h.get("pop", 0) * 100),
                    snow_amount_in=h_snow_in,
                    cloud_cover_pct=h.get("clouds"),
                    condition_text=h.get("weather", [{}])[0].get("description"),
                ))

            # Append daily entries for days 3-5 as extra forecast points
            for d in data.get("daily", [])[2:]:
                dt = datetime.fromtimestamp(d["dt"], tz=timezone.utc)
                points.append(ForecastPoint(
                    forecast_for=dt,
                    temperature_f=d.get("temp", {}).get("day"),
                    feels_like_f=d.get("feels_like", {}).get("day"),
                    humidity_pct=d.get("humidity"),
                    wind_speed_mph=d.get("wind_speed"),
                    wind_gust_mph=d.get("wind_gust"),
                    precip_probability_pct=(d.get("pop", 0) * 100),
                    cloud_cover_pct=d.get("clouds"),
                    condition_text=d.get("weather", [{}])[0].get("description"),
                ))

            return ZoneForecast(
                zone_id=zone.zone_id,
                source="owm",
                fetched_at=now,
                points=points,
            )
    except Exception as e:
        logger.warning("OWM forecast fetch failed for %s: %s", zone.zone_id, e)
        return None


def _m_to_mi(meters: float | None) -> float | None:
    if meters is None:
        return None
    return round(meters / 1609.34, 1)
