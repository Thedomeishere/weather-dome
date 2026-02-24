"""Vegetation risk model.

Factors: seasonal foliage * wind interaction + soil saturation + ice loading.
"""

from datetime import datetime, timezone

from app.schemas.impact import VegetationRisk
from app.schemas.weather import WeatherConditions


def compute(weather: WeatherConditions) -> VegetationRisk:
    month = datetime.now(timezone.utc).month
    foliage = _foliage_factor(month)
    wind_veg = _wind_vegetation_score(weather.wind_speed_mph, weather.wind_gust_mph, foliage)
    soil = _soil_saturation_score(weather.precip_rate_in_hr, weather.precip_probability_pct)
    ice_load = _ice_loading_score(weather.ice_accum_in)

    score = min(100.0, wind_veg * 0.5 + soil * 0.2 + ice_load * 0.3)

    soil_label = "normal"
    if soil > 60:
        soil_label = "saturated"
    elif soil > 30:
        soil_label = "moist"

    return VegetationRisk(
        zone_id=weather.zone_id,
        score=round(score, 1),
        level=_score_to_level(score),
        foliage_factor=foliage,
        soil_saturation=soil_label,
    )


def _foliage_factor(month: int) -> float:
    """Seasonal foliage density affects wind catchment.
    Full leaf: Jun-Sep (1.0), partial: Apr-May, Oct (0.7), bare: Nov-Mar (0.3)
    """
    if month in (6, 7, 8, 9):
        return 1.0
    if month in (4, 5, 10):
        return 0.7
    return 0.3


def _wind_vegetation_score(
    speed: float | None, gust: float | None, foliage: float
) -> float:
    effective = max(speed or 0, (gust or 0) * 0.8)
    if effective < 20:
        base = 0.0
    elif effective < 40:
        base = ((effective - 20) / 20) * 50
    elif effective < 60:
        base = 50 + ((effective - 40) / 20) * 30
    else:
        base = min(100.0, 80 + (effective - 60) * 1.5)

    return base * foliage


def _soil_saturation_score(precip_rate: float | None, precip_prob: float | None) -> float:
    rate_score = min(100.0, (precip_rate or 0) * 40)
    prob_score = (precip_prob or 0) * 0.5
    return min(100.0, rate_score + prob_score)


def _ice_loading_score(ice_in: float | None) -> float:
    if not ice_in or ice_in <= 0:
        return 0.0
    if ice_in < 0.1:
        return ice_in / 0.1 * 30
    if ice_in < 0.25:
        return 30 + ((ice_in - 0.1) / 0.15) * 40
    return min(100.0, 70 + (ice_in - 0.25) * 120)


def _score_to_level(score: float) -> str:
    if score < 25:
        return "Low"
    if score < 50:
        return "Moderate"
    if score < 75:
        return "High"
    return "Extreme"
