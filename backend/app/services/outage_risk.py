"""Outage risk scoring model.

Weighted scoring: wind(0.4) + ice(0.3) + lightning(0.15) + precip(0.15)
Wind + ice synergy bonus when both present.
"""

from app.config import settings
from app.schemas.impact import OutageRisk
from app.schemas.weather import WeatherConditions


def compute(weather: WeatherConditions) -> OutageRisk:
    wind_score = _wind_score(weather.wind_speed_mph, weather.wind_gust_mph)
    ice_score = _ice_score(weather.ice_accum_in)
    lightning_score = _lightning_score(weather.lightning_probability_pct)
    precip_score = _precip_score(
        weather.precip_rate_in_hr,
        weather.snow_rate_in_hr,
        weather.precip_probability_pct,
    )

    base_score = (
        wind_score * 0.4
        + ice_score * 0.3
        + lightning_score * 0.15
        + precip_score * 0.15
    )

    # Synergy bonus: wind + ice together are disproportionately dangerous
    synergy = 0.0
    if wind_score > 30 and ice_score > 30:
        synergy = min(wind_score, ice_score) * 0.25

    score = min(100.0, base_score + synergy)

    factors = []
    if wind_score > 20:
        factors.append(f"Wind ({weather.wind_speed_mph or 0:.0f} mph)")
    if ice_score > 20:
        factors.append(f"Ice ({weather.ice_accum_in or 0:.2f} in)")
    if lightning_score > 20:
        factors.append("Lightning risk")
    if precip_score > 20:
        factors.append("Heavy precipitation")
    if synergy > 0:
        factors.append("Wind+Ice synergy")

    level = _score_to_level(score)
    estimated = _estimate_outages(score)

    return OutageRisk(
        zone_id=weather.zone_id,
        score=round(score, 1),
        level=level,
        estimated_outages=estimated,
        contributing_factors=factors,
    )


def _wind_score(speed: float | None, gust: float | None) -> float:
    effective = max(speed or 0, (gust or 0) * 0.8)
    if effective < 15:
        return 0.0
    if effective < settings.wind_advisory_threshold:
        return ((effective - 15) / (settings.wind_advisory_threshold - 15)) * 30
    if effective < settings.wind_warning_threshold:
        return 30 + ((effective - settings.wind_advisory_threshold) /
                      (settings.wind_warning_threshold - settings.wind_advisory_threshold)) * 40
    if effective < settings.wind_extreme_threshold:
        return 70 + ((effective - settings.wind_warning_threshold) /
                      (settings.wind_extreme_threshold - settings.wind_warning_threshold)) * 20
    return 100.0


def _ice_score(ice_in: float | None) -> float:
    if not ice_in or ice_in <= 0:
        return 0.0
    if ice_in < settings.ice_advisory_threshold:
        return (ice_in / settings.ice_advisory_threshold) * 30
    if ice_in < settings.ice_warning_threshold:
        return 30 + ((ice_in - settings.ice_advisory_threshold) /
                      (settings.ice_warning_threshold - settings.ice_advisory_threshold)) * 40
    if ice_in < settings.ice_extreme_threshold:
        return 70 + ((ice_in - settings.ice_warning_threshold) /
                      (settings.ice_extreme_threshold - settings.ice_warning_threshold)) * 20
    return 100.0


def _lightning_score(prob: float | None) -> float:
    if not prob or prob <= 0:
        return 0.0
    return min(100.0, prob * 1.2)


def _precip_score(rate: float | None, snow: float | None, prob: float | None) -> float:
    rate_factor = min(100.0, (rate or 0) * 50) if rate else 0
    snow_factor = min(100.0, (snow or 0) * 30) if snow else 0
    prob_factor = (prob or 0) * 0.3
    return min(100.0, max(rate_factor, snow_factor) + prob_factor)


def _score_to_level(score: float) -> str:
    if score < 25:
        return "Low"
    if score < 50:
        return "Moderate"
    if score < 75:
        return "High"
    return "Extreme"


def _estimate_outages(score: float) -> int:
    """Rough estimate of per-zone outages based on risk score."""
    if score < 10:
        return 0
    if score < 25:
        return int(score * 2)
    if score < 50:
        return int(score * 10)
    if score < 75:
        return int(score * 40)
    return int(score * 100)
