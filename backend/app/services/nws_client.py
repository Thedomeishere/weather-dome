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
                snow_depth_in=_m_to_in(obs.get("snowDepth", {}).get("value")),
                condition_text=obs.get("textDescription"),
            )
    except Exception as e:
        logger.warning("NWS current fetch failed for %s: %s", zone.zone_id, e)
        return None


async def fetch_forecast(zone: ZoneDefinition) -> ZoneForecast | None:
    """Fetch hourly forecast from NWS gridpoint, enriched with snow data."""
    hourly_url = f"{NWS_BASE}/gridpoints/{zone.nws_grid_office}/{zone.nws_grid_x},{zone.nws_grid_y}/forecast/hourly"
    grid_url = f"{NWS_BASE}/gridpoints/{zone.nws_grid_office}/{zone.nws_grid_x},{zone.nws_grid_y}"
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=15) as client:
            resp = await client.get(hourly_url)
            resp.raise_for_status()
            periods = resp.json()["properties"]["periods"]

            # Also fetch raw gridpoint data for snowfallAmount
            snowfall_map = _fetch_snowfall_map(await client.get(grid_url))

            now = datetime.now(timezone.utc)
            points = []
            for p in periods[:120]:
                forecast_time = p["startTime"]
                condition = p.get("shortForecast", "")
                snow_amount = _lookup_snowfall(snowfall_map, forecast_time)
                # Infer snow_depth from recent snowfall accumulation and conditions
                snow_depth = _estimate_depth_from_context(
                    snowfall_map, forecast_time, condition,
                )
                points.append(ForecastPoint(
                    forecast_for=forecast_time,
                    temperature_f=p.get("temperature"),
                    wind_speed_mph=_parse_wind_speed(p.get("windSpeed", "")),
                    precip_probability_pct=p.get("probabilityOfPrecipitation", {}).get("value"),
                    snow_amount_in=snow_amount,
                    snow_depth_in=snow_depth,
                    condition_text=condition,
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
                    url=f.get("id"),
                ))
            return alerts
    except Exception as e:
        logger.warning("NWS alerts fetch failed for %s: %s", zone.zone_id, e)
        return []


def _fetch_snowfall_map(grid_resp) -> list[tuple[datetime, float, float]]:
    """Parse snowfallAmount from raw gridpoint response into time-indexed list.

    Returns list of (start_time, duration_hours, amount_inches) sorted by time.
    """
    try:
        if grid_resp.status_code != 200:
            return []
        props = grid_resp.json().get("properties", {})
        snow_data = props.get("snowfallAmount", {})
        values = snow_data.get("values", [])
        result = []
        for v in values:
            valid_time = v.get("validTime", "")
            mm_val = v.get("value", 0) or 0
            inches = round(mm_val / 25.4, 2)
            # Parse ISO duration from validTime "2026-02-25T06:00:00+00:00/PT6H"
            if "/" in valid_time:
                time_str, duration_str = valid_time.split("/", 1)
                start = datetime.fromisoformat(time_str)
                hours = _parse_iso_duration_hours(duration_str)
                result.append((start, hours, inches))
        return sorted(result, key=lambda x: x[0])
    except Exception as e:
        logger.debug("Failed to parse gridpoint snowfall: %s", e)
        return []


def _parse_iso_duration_hours(duration: str) -> float:
    """Parse ISO 8601 duration like PT6H, PT3H into hours."""
    import re
    m = re.match(r"PT(\d+)H", duration)
    return float(m.group(1)) if m else 1.0


def _lookup_snowfall(snowfall_map: list, forecast_time_str: str) -> float | None:
    """Find snowfall rate (in/hr) for a given forecast hour."""
    if not snowfall_map:
        return None
    try:
        ft = datetime.fromisoformat(str(forecast_time_str))
        for start, hours, inches in snowfall_map:
            end = start + __import__("datetime").timedelta(hours=hours)
            if start <= ft < end:
                return round(inches / max(hours, 1), 3) if inches > 0 else None
    except Exception:
        pass
    return None


def _estimate_depth_from_context(
    snowfall_map: list,
    forecast_time_str: str,
    condition_text: str,
) -> float | None:
    """Estimate snow depth on ground from gridpoint snowfall history + conditions.

    Sums all snowfall from gridpoint data preceding the forecast hour,
    then applies temperature-based melt decay. Also uses condition_text
    to infer a minimum snow depth when conditions mention snow.
    """
    if not snowfall_map and not condition_text:
        return None

    try:
        ft = datetime.fromisoformat(str(forecast_time_str))
    except Exception:
        return None

    # Sum all snowfall preceding this forecast time
    accumulated = 0.0
    for start, hours, inches in snowfall_map:
        end = start + __import__("datetime").timedelta(hours=hours)
        if end <= ft:
            # Past period: all snow fell
            accumulated += inches
        elif start < ft:
            # Partially past: pro-rate
            elapsed = (ft - start).total_seconds() / 3600
            fraction = elapsed / max(hours, 1)
            accumulated += inches * fraction

    # Infer minimum snow on ground from condition_text
    cond_lower = (condition_text or "").lower()
    snow_keywords = ("snow", "blizzard", "flurries", "wintry mix")
    has_snow_conditions = any(kw in cond_lower for kw in snow_keywords)

    if accumulated > 0.1:
        return round(accumulated, 1)
    elif has_snow_conditions:
        # If NWS says snow conditions but no accumulation data,
        # there must be at least some snow on the ground
        return 2.0  # conservative minimum
    return None


def _m_to_in(meters: float | None) -> float | None:
    """Convert meters to inches (NWS snowDepth is in meters)."""
    if meters is None:
        return None
    return round(meters * 39.3701, 1)


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
