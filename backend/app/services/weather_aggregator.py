"""Conservative multi-source weather aggregation.

Strategy: max wind/ice/precip (safety-first), weighted avg temperature.
"""

import logging
from datetime import datetime, timezone

from app.schemas.weather import WeatherConditions, ForecastPoint, ZoneForecast

logger = logging.getLogger(__name__)


def aggregate_current(observations: list[WeatherConditions], zone_id: str) -> WeatherConditions:
    """Merge multiple source observations into a single conservative estimate."""
    valid = [o for o in observations if o is not None]
    if not valid:
        return WeatherConditions(
            zone_id=zone_id,
            source="aggregated",
            observed_at=datetime.now(timezone.utc),
        )

    if len(valid) == 1:
        result = valid[0].model_copy()
        result.source = "aggregated"
        return result

    return WeatherConditions(
        zone_id=zone_id,
        source="aggregated",
        observed_at=datetime.now(timezone.utc),
        temperature_f=_weighted_avg([o.temperature_f for o in valid]),
        feels_like_f=_weighted_avg([o.feels_like_f for o in valid]),
        humidity_pct=_safe_max([o.humidity_pct for o in valid]),
        wind_speed_mph=_safe_max([o.wind_speed_mph for o in valid]),
        wind_gust_mph=_safe_max([o.wind_gust_mph for o in valid]),
        wind_direction_deg=_weighted_avg([o.wind_direction_deg for o in valid]),
        precip_rate_in_hr=_safe_max([o.precip_rate_in_hr for o in valid]),
        precip_probability_pct=_safe_max([o.precip_probability_pct for o in valid]),
        snow_rate_in_hr=_safe_max([o.snow_rate_in_hr for o in valid]),
        ice_accum_in=_safe_max([o.ice_accum_in for o in valid]),
        visibility_mi=_safe_min([o.visibility_mi for o in valid]),  # worst visibility
        cloud_cover_pct=_safe_max([o.cloud_cover_pct for o in valid]),
        pressure_mb=_weighted_avg([o.pressure_mb for o in valid]),
        lightning_probability_pct=_safe_max([o.lightning_probability_pct for o in valid]),
        condition_text=_pick_condition(valid),
    )


def aggregate_forecasts(forecasts: list[ZoneForecast], zone_id: str) -> ZoneForecast:
    """Merge forecast timelines from multiple sources."""
    valid = [f for f in forecasts if f is not None and f.points]
    if not valid:
        return ZoneForecast(
            zone_id=zone_id,
            source="aggregated",
            fetched_at=datetime.now(timezone.utc),
        )

    if len(valid) == 1:
        result = valid[0].model_copy()
        result.source = "aggregated"
        return result

    # Group by nearest hour
    hourly: dict[str, list[ForecastPoint]] = {}
    for fc in valid:
        for p in fc.points:
            key = p.forecast_for.strftime("%Y-%m-%dT%H:00")
            hourly.setdefault(key, []).append(p)

    merged_points = []
    for key in sorted(hourly.keys()):
        pts = hourly[key]
        merged_points.append(ForecastPoint(
            forecast_for=datetime.fromisoformat(key).replace(tzinfo=timezone.utc),
            temperature_f=_weighted_avg([p.temperature_f for p in pts]),
            feels_like_f=_weighted_avg([p.feels_like_f for p in pts]),
            humidity_pct=_safe_max([p.humidity_pct for p in pts]),
            wind_speed_mph=_safe_max([p.wind_speed_mph for p in pts]),
            wind_gust_mph=_safe_max([p.wind_gust_mph for p in pts]),
            precip_probability_pct=_safe_max([p.precip_probability_pct for p in pts]),
            precip_amount_in=_safe_max([p.precip_amount_in for p in pts]),
            snow_amount_in=_safe_max([p.snow_amount_in for p in pts]),
            ice_accum_in=_safe_max([p.ice_accum_in for p in pts]),
            lightning_probability_pct=_safe_max([p.lightning_probability_pct for p in pts]),
            condition_text=pts[0].condition_text,
        ))

    return ZoneForecast(
        zone_id=zone_id,
        source="aggregated",
        fetched_at=datetime.now(timezone.utc),
        points=merged_points[:120],
    )


def _safe_max(values: list[float | None]) -> float | None:
    nums = [v for v in values if v is not None]
    return max(nums) if nums else None


def _safe_min(values: list[float | None]) -> float | None:
    nums = [v for v in values if v is not None]
    return min(nums) if nums else None


def _weighted_avg(values: list[float | None]) -> float | None:
    nums = [v for v in values if v is not None]
    if not nums:
        return None
    return round(sum(nums) / len(nums), 1)


def _pick_condition(observations: list[WeatherConditions]) -> str | None:
    for o in observations:
        if o.condition_text:
            return o.condition_text
    return None
