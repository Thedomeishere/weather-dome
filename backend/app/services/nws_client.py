import logging
from datetime import datetime, timezone

import httpx

from app.schemas.weather import WeatherConditions, ForecastPoint, ZoneForecast, AlertSchema
from app.territory.definitions import ZoneDefinition

logger = logging.getLogger(__name__)

NWS_BASE = "https://api.weather.gov"
HEADERS = {
    "User-Agent": "(weather-dome, weather-dome@example.com)",
    "Accept": "application/geo+json",
}


async def fetch_current(zone: ZoneDefinition) -> WeatherConditions | None:
    """Fetch current observations from the nearest NWS station."""
    url = f"{NWS_BASE}/points/{zone.latitude},{zone.longitude}"
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=15) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            props = resp.json()["properties"]
            station_url = props.get("observationStations")
            if not station_url:
                return None

            stations_resp = await client.get(station_url)
            stations_resp.raise_for_status()
            features = stations_resp.json().get("features", [])
            if not features:
                return None

            station_id = features[0]["properties"]["stationIdentifier"]
            obs_url = f"{NWS_BASE}/stations/{station_id}/observations/latest"
            obs_resp = await client.get(obs_url)
            obs_resp.raise_for_status()
            obs = obs_resp.json()["properties"]

            return WeatherConditions(
                zone_id=zone.zone_id,
                source="nws",
                observed_at=obs.get("timestamp", datetime.now(timezone.utc).isoformat()),
                temperature_f=_c_to_f(obs.get("temperature", {}).get("value")),
                humidity_pct=obs.get("relativeHumidity", {}).get("value"),
                wind_speed_mph=_kmh_to_mph(obs.get("windSpeed", {}).get("value")),
                wind_gust_mph=_kmh_to_mph(obs.get("windGust", {}).get("value")),
                wind_direction_deg=obs.get("windDirection", {}).get("value"),
                visibility_mi=_m_to_mi(obs.get("visibility", {}).get("value")),
                pressure_mb=_pa_to_mb(obs.get("barometricPressure", {}).get("value")),
                condition_text=obs.get("textDescription"),
            )
    except Exception as e:
        logger.warning("NWS current fetch failed for %s: %s", zone.zone_id, e)
        return None


async def fetch_forecast(zone: ZoneDefinition) -> ZoneForecast | None:
    """Fetch hourly forecast from NWS gridpoint."""
    url = f"{NWS_BASE}/gridpoints/{zone.nws_grid_office}/{zone.nws_grid_x},{zone.nws_grid_y}/forecast/hourly"
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=15) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            periods = resp.json()["properties"]["periods"]

            now = datetime.now(timezone.utc)
            points = []
            for p in periods[:120]:
                points.append(ForecastPoint(
                    forecast_for=p["startTime"],
                    temperature_f=p.get("temperature"),
                    wind_speed_mph=_parse_wind_speed(p.get("windSpeed", "")),
                    precip_probability_pct=p.get("probabilityOfPrecipitation", {}).get("value"),
                    condition_text=p.get("shortForecast"),
                ))

            return ZoneForecast(
                zone_id=zone.zone_id,
                source="nws",
                fetched_at=now,
                points=points,
            )
    except Exception as e:
        logger.warning("NWS forecast fetch failed for %s: %s", zone.zone_id, e)
        return None


async def fetch_alerts(zone: ZoneDefinition) -> list[AlertSchema]:
    """Fetch active alerts for an NWS zone."""
    url = f"{NWS_BASE}/alerts/active/zone/{zone.nws_zone}"
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=15) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            features = resp.json().get("features", [])

            alerts = []
            for f in features:
                p = f["properties"]
                alerts.append(AlertSchema(
                    alert_id=p.get("id", f.get("id", "")),
                    zone_id=zone.zone_id,
                    event=p.get("event", "Unknown"),
                    severity=p.get("severity", "Unknown"),
                    urgency=p.get("urgency"),
                    certainty=p.get("certainty"),
                    headline=p.get("headline"),
                    description=p.get("description"),
                    instruction=p.get("instruction"),
                    onset=p.get("onset"),
                    expires=p.get("expires"),
                ))
            return alerts
    except Exception as e:
        logger.warning("NWS alerts fetch failed for %s: %s", zone.zone_id, e)
        return []


def _c_to_f(celsius: float | None) -> float | None:
    if celsius is None:
        return None
    return round(celsius * 9 / 5 + 32, 1)


def _kmh_to_mph(kmh: float | None) -> float | None:
    if kmh is None:
        return None
    return round(kmh * 0.621371, 1)


def _m_to_mi(meters: float | None) -> float | None:
    if meters is None:
        return None
    return round(meters / 1609.34, 1)


def _pa_to_mb(pascals: float | None) -> float | None:
    if pascals is None:
        return None
    return round(pascals / 100, 1)


def _parse_wind_speed(wind_str: str) -> float | None:
    """Parse NWS wind speed string like '15 mph' or '10 to 20 mph'."""
    if not wind_str:
        return None
    import re
    numbers = re.findall(r"(\d+)", wind_str)
    if not numbers:
        return None
    return max(float(n) for n in numbers)
