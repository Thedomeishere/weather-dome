"""Load forecasting model.

Temperature-driven demand (U-curve around 65F) * time-of-day factor.
ConEd peak: 13,400 MW, O&R: 1,300 MW.
"""

from datetime import datetime, timezone

from app.config import settings
from app.schemas.impact import LoadForecast
from app.schemas.weather import WeatherConditions
from app.territory.definitions import ZoneDefinition


def compute(weather: WeatherConditions, zone: ZoneDefinition) -> LoadForecast:
    capacity = (
        settings.coned_peak_capacity_mw
        if zone.territory == "CONED"
        else settings.or_peak_capacity_mw
    )
    zone_capacity = capacity * zone.peak_load_share

    temp = weather.temperature_f or 65.0
    hour = weather.observed_at.hour if weather.observed_at else datetime.now(timezone.utc).hour

    temp_factor = _temperature_demand_factor(temp)
    tod_factor = _time_of_day_factor(hour)

    # Base load is ~40% of capacity, weather drives the rest
    base_load_pct = 0.40
    weather_load_pct = temp_factor * 0.55  # weather can add up to 55%
    tod_adj = tod_factor * 0.05  # time of day adds up to 5%

    total_pct = min(1.1, base_load_pct + weather_load_pct + tod_adj)  # allow slight overload
    load_mw = round(zone_capacity * total_pct, 1)
    pct = round(total_pct * 100, 1)

    peak_hour = _estimate_peak_hour(temp)

    return LoadForecast(
        zone_id=weather.zone_id,
        territory=zone.territory,
        load_mw=load_mw,
        capacity_mw=round(zone_capacity, 1),
        pct_capacity=pct,
        risk_level=_load_risk_level(total_pct),
        peak_hour=peak_hour,
    )


def _temperature_demand_factor(temp_f: float) -> float:
    """U-curve: minimum demand around 65F, rising for heating and cooling."""
    deviation = abs(temp_f - 65.0)
    if deviation < 5:
        return 0.0
    if deviation < 15:
        return (deviation - 5) / 10 * 0.3
    if deviation < 30:
        return 0.3 + ((deviation - 15) / 15) * 0.4
    return min(1.0, 0.7 + (deviation - 30) / 20 * 0.3)


def _time_of_day_factor(hour_utc: int) -> float:
    """Time-of-day load shape (EST = UTC-5).
    Peak: 2-6 PM EST (19-23 UTC), Off-peak: 11 PM-6 AM EST (4-11 UTC)
    """
    hour_est = (hour_utc - 5) % 24
    if 14 <= hour_est <= 18:
        return 1.0
    if 7 <= hour_est <= 13:
        return 0.7
    if 19 <= hour_est <= 22:
        return 0.6
    return 0.3  # overnight


def _estimate_peak_hour(temp_f: float) -> int:
    """Estimate peak demand hour (EST)."""
    if temp_f > 80:
        return 16  # 4 PM for cooling
    if temp_f < 30:
        return 8   # 8 AM for heating
    return 12  # noon for moderate temps


def _load_risk_level(pct: float) -> str:
    if pct < 0.7:
        return "Low"
    if pct < 0.85:
        return "Moderate"
    if pct < 0.95:
        return "High"
    return "Extreme"
