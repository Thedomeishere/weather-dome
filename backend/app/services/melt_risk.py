"""Underground melt risk model.

Snowmelt/ice-melt causes manhole events and cable failures (2000+/year in NYC,
peaking Feb-Mar). Uses 48h weather history to detect dangerous melt conditions.

Five sub-scores:
- Temperature trend (30%): Rate of warming from <32F to >40F
- Melt potential (20%): Current temp above freezing + recent snow accumulation
- Rain-on-snow (20%): Active precipitation when snow cover exists and temp >32F
- Salt-melt contamination (20%): Road salt + melting snow creates conductive brine
  that infiltrates manholes/vaults causing short circuits and fires
- Freeze-thaw cycling (10%): Count of 32F crossings in 48h

Modifiers: underground density * seasonal factor
"""

import logging
from datetime import datetime, timezone

from app.config import settings
from app.models.weather import WeatherObservation
from app.schemas.outage import MeltRisk
from app.schemas.weather import WeatherConditions

logger = logging.getLogger(__name__)

# Underground infrastructure density per zone (0-1)
UNDERGROUND_DENSITY: dict[str, float] = {
    "CONED-MAN": 1.0,
    "CONED-BKN": 0.8,
    "CONED-BRX": 0.7,
    "CONED-QNS": 0.7,
    "CONED-SI": 0.3,
    "CONED-WST": 0.2,
    "OR-ORA": 0.05,
    "OR-ROC": 0.04,
    "OR-SUL": 0.02,
    "OR-BER": 0.05,
    "OR-SSX": 0.02,
}


def _seasonal_factor(dt: datetime | None = None) -> float:
    """Peak 1.0 in Feb-Mar, 0.0 Jun-Sep, ramp in between."""
    if dt is None:
        dt = datetime.now(timezone.utc)
    month = dt.month
    if month in (2, 3):
        return 1.0
    if month in (1, 4):
        return 0.7
    if month in (5, 11, 12):
        return 0.4
    if month == 10:
        return 0.2
    # Jun-Sep
    return 0.0


def _score_to_level(score: float) -> str:
    if score < 25:
        return "Low"
    if score < 50:
        return "Moderate"
    if score < 75:
        return "High"
    return "Extreme"


def compute(
    zone_id: str,
    weather: WeatherConditions,
    observations: list[WeatherObservation] | None = None,
) -> MeltRisk:
    """Compute underground melt risk for a zone.

    Args:
        zone_id: Zone identifier
        weather: Current weather conditions
        observations: Optional 48h historical weather observations from DB
    """
    density = UNDERGROUND_DENSITY.get(zone_id, 0.0)
    season = _seasonal_factor(weather.observed_at)

    # If no underground infrastructure or not in season, return zero
    if density < 0.01 or season < 0.01:
        return MeltRisk(zone_id=zone_id)

    freezing = settings.melt_risk_freezing_point_f
    warm_thresh = settings.melt_risk_warm_threshold_f
    rapid_rate = settings.melt_risk_rapid_warming_rate_f_per_hr

    current_temp = weather.temperature_f or 50.0
    snow_rate = weather.snow_rate_in_hr or 0.0
    precip_rate = weather.precip_rate_in_hr or 0.0
    ice_accum = weather.ice_accum_in or 0.0

    # Extract history from observations if available
    temps: list[float] = []
    total_snow = 0.0
    if observations:
        for obs in observations:
            if obs.temperature_f is not None:
                temps.append(obs.temperature_f)
            if obs.snow_rate_in_hr is not None:
                total_snow += obs.snow_rate_in_hr * 0.25  # ~15min intervals
    # Always include current temp
    temps.append(current_temp)

    factors: list[str] = []

    # --- Sub-score 1: Temperature trend (35%) ---
    temp_trend_f_per_hr = 0.0
    temp_trend_score = 0.0
    if len(temps) >= 2:
        # Use first-half min vs current to detect warming from below freezing
        half = len(temps) // 2
        first_half_min = min(temps[:half]) if half > 0 else temps[0]
        hours_span = max(1, len(temps) * 0.25)  # ~15min intervals
        temp_trend_f_per_hr = (current_temp - first_half_min) / hours_span

        if first_half_min < freezing and current_temp > freezing:
            # Warming from below freezing — dangerous
            rate_factor = min(1.0, temp_trend_f_per_hr / rapid_rate)
            temp_above = min(1.0, (current_temp - freezing) / (warm_thresh - freezing))
            temp_trend_score = (rate_factor * 0.6 + temp_above * 0.4) * 100
            factors.append(f"Warming {temp_trend_f_per_hr:.1f}F/hr from below freezing")
        elif current_temp > freezing and temp_trend_f_per_hr > 0.5:
            temp_trend_score = min(50, temp_trend_f_per_hr / rapid_rate * 50)

    # --- Sub-score 2: Melt potential (25%) ---
    melt_potential = 0.0
    snow_present = total_snow > 0.1 or snow_rate > 0 or ice_accum > 0
    if current_temp > freezing and snow_present:
        temp_factor = min(1.0, (current_temp - freezing) / 15.0)  # saturates at 15F above
        snow_factor = min(1.0, (total_snow + ice_accum) / 2.0)  # saturates at 2in
        melt_potential = (temp_factor * 0.5 + snow_factor * 0.5) * 100
        factors.append("Active snowmelt conditions")

    # --- Sub-score 3: Rain-on-snow (25%) ---
    rain_on_snow = 0.0
    if precip_rate > 0 and snow_present and current_temp > freezing:
        precip_factor = min(1.0, precip_rate / 0.5)  # saturates at 0.5 in/hr
        rain_on_snow = precip_factor * 100
        factors.append("Rain-on-snow accelerating melt")

    # --- Sub-score 4: Salt-melt contamination (20%) ---
    # Heavy snow → more road salt applied → when it melts, conductive brine
    # infiltrates manholes and cable vaults causing short circuits and fires.
    salt_melt = 0.0
    effective_snow = total_snow + snow_rate  # accumulated + currently falling
    if current_temp >= freezing and effective_snow > 0.5:
        # More snow = more salt applied by road crews
        # Saturates at 4 inches (heavy salting level)
        snow_factor = min(1.0, effective_snow / 4.0)
        # Warmer above freezing = faster melt dissolving more salt
        # Saturates at 10F above freezing
        melt_intensity = min(1.0, (current_temp - freezing) / 10.0)
        salt_melt = snow_factor * melt_intensity * 100
        if salt_melt > 15:
            factors.append(
                f"Salt-melt brine risk ({effective_snow:.1f} in snow + {current_temp - freezing:.0f}F above freezing)"
            )

    # --- Sub-score 5: Freeze-thaw cycles (10%) ---
    freeze_thaw_cycles = 0
    if len(temps) >= 4:
        above = temps[0] > freezing
        for t in temps[1:]:
            now_above = t > freezing
            if now_above != above:
                freeze_thaw_cycles += 1
                above = now_above
        freeze_thaw_cycles = freeze_thaw_cycles // 2  # full cycles
    ftc_score = min(100.0, freeze_thaw_cycles * 25.0)  # 4+ cycles = max
    if freeze_thaw_cycles >= 2:
        factors.append(f"{freeze_thaw_cycles} freeze-thaw cycles in 48h")

    # --- Weighted combination ---
    raw_score = (
        temp_trend_score * 0.30
        + melt_potential * 0.20
        + rain_on_snow * 0.20
        + salt_melt * 0.20
        + ftc_score * 0.10
    )

    # Apply modifiers
    final_score = raw_score * density * season
    final_score = max(0, min(100, final_score))

    if density >= 0.5:
        factors.append("High underground infrastructure density")

    return MeltRisk(
        zone_id=zone_id,
        score=round(final_score, 1),
        level=_score_to_level(final_score),
        temperature_trend_f_per_hr=round(temp_trend_f_per_hr, 2),
        melt_potential=round(melt_potential, 1),
        rain_on_snow_risk=round(rain_on_snow, 1),
        salt_melt_risk=round(salt_melt, 1),
        freeze_thaw_cycles_48h=freeze_thaw_cycles,
        contributing_factors=factors,
    )
