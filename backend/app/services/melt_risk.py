"""Underground melt risk model.

Snowmelt/ice-melt causes manhole events and cable failures (2000+/year in NYC,
peaking Feb-Mar). Uses 48h weather history to detect dangerous melt conditions.

Six sub-scores:
- Snow cover melt (35%): Snow on ground + above-freezing temps = active melt
  infiltrating underground infrastructure. Primary driver.
- Salt-melt contamination (25%): Road salt + melting snow creates conductive brine
  that infiltrates manholes/vaults causing short circuits and fires
- Melt potential (15%): Temperature above freezing × snow depth interaction
- Rain-on-snow (10%): Active precipitation accelerating melt when snow present
- Temperature trend (10%): Rate of warming from <32F to >40F
- Freeze-thaw cycling (5%): Count of 32F crossings in 48h

Modifiers: underground density * seasonal factor
"""

import logging
from datetime import datetime, timezone

from app.config import settings
from app.models.weather import WeatherObservation
from app.schemas.outage import MeltRisk
from app.schemas.weather import WeatherConditions

logger = logging.getLogger(__name__)

# Underground melt vulnerability per zone (0-1).
# NOT just density — reflects age of infrastructure, cable insulation type,
# manhole drainage quality, and historical melt event frequency.
# Brooklyn/Queens have the most vulnerable underground: aging paper-insulated
# lead cables, poor manhole drainage, direct-buried lines, tree root damage.
# Manhattan is dense but well-maintained with modern XLPE cables and better
# waterproofing. BKN/QNS historically see 2-3x more melt outages than Manhattan.
UNDERGROUND_DENSITY: dict[str, float] = {
    "CONED-BKN": 1.0,   # Highest: oldest cables, worst drainage, most melt events
    "CONED-QNS": 0.95,  # Very high: similar aging infrastructure to Brooklyn
    "CONED-BRX": 0.85,  # High: older infrastructure, mixed overhead/underground
    "CONED-MAN": 0.70,  # Dense but well-maintained, modern cables, better waterproofing
    "CONED-WST": 0.30,  # Suburban: more overhead, some vulnerable underground
    "CONED-SI": 0.15,   # Mostly overhead distribution
    "OR-ORA": 0.05,
    "OR-ROC": 0.04,
    "OR-SUL": 0.02,
    "OR-BER": 0.05,
    "OR-SSX": 0.02,
}

# Effective melt threshold per zone (°F).
# Road salt lowers effective freezing to 15-20°F on treated surfaces.
# Urban heat island, solar radiation on dark surfaces (manholes, streets),
# subsurface heat (steam pipes, subway), and building exhaust all cause
# melt well below the 32°F air temperature threshold.
EFFECTIVE_MELT_THRESHOLD: dict[str, float] = {
    "CONED-MAN": 25.0,   # Heaviest salt, steam pipes, dense building heat
    "CONED-BKN": 27.0,   # Heavy urban, salted roads
    "CONED-BRX": 27.0,
    "CONED-QNS": 27.0,
    "CONED-SI": 29.0,    # Less urban density
    "CONED-WST": 28.0,   # Suburban, still salted
    "OR-ORA": 30.0,      # Suburban/rural
    "OR-ROC": 30.0,
    "OR-SUL": 31.0,      # More rural
    "OR-BER": 30.0,
    "OR-SSX": 31.0,
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


def _estimate_snow_on_ground(
    observations: list[WeatherObservation],
    freezing: float,
    zone_id: str = "",
) -> float:
    """Estimate snow on ground from observation history using accumulation minus melt decay.

    Tracks running snow depth: adds snowfall, subtracts temperature-based melt.
    Standard degree-day snowmelt: ~0.06 in/°F/day = 0.0025 in/°F/hr.
    Urban zones melt 2-3.5x faster due to plowing, salting, dark surfaces.
    """
    if not observations:
        return 0.0

    # Urban melt multiplier: NYC plows/salts aggressively
    _MELT_MULT = {
        "CONED-MAN": 3.5, "CONED-BKN": 3.0, "CONED-QNS": 3.0,
        "CONED-BRX": 2.5, "CONED-SI": 2.0, "CONED-WST": 2.0,
        "OR-ORA": 1.5, "OR-ROC": 1.5, "OR-SUL": 1.2,
        "OR-BER": 1.5, "OR-SSX": 1.2,
    }
    mult = _MELT_MULT.get(zone_id, 1.5)

    accumulated = 0.0
    for obs in observations:
        # Add snowfall
        if obs.snow_rate_in_hr is not None and obs.snow_rate_in_hr > 0:
            accumulated += obs.snow_rate_in_hr * 0.25  # ~15min intervals

        # Subtract melt when above freezing (degree-day method + urban accel)
        if obs.temperature_f is not None and obs.temperature_f > freezing:
            degrees_above = obs.temperature_f - freezing
            melt = degrees_above * 0.005 * mult * 0.25  # per 15-min interval
            accumulated = max(0.0, accumulated - melt)

    return accumulated


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

    # Use per-zone effective melt threshold (accounts for salt, urban heat, solar)
    freezing = EFFECTIVE_MELT_THRESHOLD.get(zone_id, settings.melt_risk_freezing_point_f)
    warm_thresh = freezing + 8.0  # warm threshold scales with effective freezing
    rapid_rate = settings.melt_risk_rapid_warming_rate_f_per_hr

    current_temp = weather.temperature_f or 50.0
    snow_rate = weather.snow_rate_in_hr or 0.0
    snow_depth = weather.snow_depth_in or 0.0
    precip_rate = weather.precip_rate_in_hr or 0.0
    ice_accum = weather.ice_accum_in or 0.0

    # Extract history from observations if available
    temps: list[float] = []
    total_snow = 0.0
    max_obs_snow_depth = 0.0
    if observations:
        for obs in observations:
            if obs.temperature_f is not None:
                temps.append(obs.temperature_f)
            if obs.snow_rate_in_hr is not None:
                total_snow += obs.snow_rate_in_hr * 0.25  # ~15min intervals
            if getattr(obs, "snow_depth_in", None) is not None:
                max_obs_snow_depth = max(max_obs_snow_depth, obs.snow_depth_in)
    # Always include current temp
    temps.append(current_temp)

    # Snow persistence estimate from accumulation minus melt decay
    estimated_ground_snow = _estimate_snow_on_ground(observations or [], freezing, zone_id)

    # Infer snow on ground from condition_text when no depth data available.
    # These are CONSERVATIVE estimates — condition text alone is weak signal.
    # NWS forecast snow_depth_in (when available) is far more reliable.
    # Calibrated: Feb 2026 NYC "Snow" conditions had 0.3-0.9" actual depth.
    condition_text = (weather.condition_text or "").lower()
    condition_snow_estimate = 0.0
    if any(kw in condition_text for kw in ("snow", "blizzard", "flurries", "wintry")):
        if "blizzard" in condition_text or "heavy snow" in condition_text:
            condition_snow_estimate = 6.0
        elif "snow" in condition_text and "light" not in condition_text:
            condition_snow_estimate = 3.0
        elif "light snow" in condition_text:
            condition_snow_estimate = 1.5
        elif "flurries" in condition_text or "wintry" in condition_text:
            condition_snow_estimate = 0.5

    # Effective snow depth: prefer measured/explicit over inferred.
    # Only fall back to condition_text estimate if no other data source available.
    measured_depth = max(snow_depth, max_obs_snow_depth, estimated_ground_snow)
    if measured_depth > 0.1:
        # We have real data — use it, ignore condition text inference
        effective_snow_depth = max(measured_depth, total_snow)
    else:
        # No measured data — use condition text as weak fallback
        effective_snow_depth = max(total_snow, condition_snow_estimate)

    factors: list[str] = []

    # --- Sub-score 1: Snow cover melt (35%) ---
    # Primary driver: snow on ground + above-freezing temp = continuous meltwater
    # infiltrating underground infrastructure
    snow_cover_melt = 0.0
    snow_present = effective_snow_depth > 0.1 or snow_rate > 0 or ice_accum > 0
    if current_temp > freezing and snow_present:
        # Depth factor: saturates at 6 inches (even modest snow = significant melt volume)
        depth_factor = min(1.0, effective_snow_depth / 6.0) if effective_snow_depth > 0 else 0.1
        # Temperature factor: saturates at 6F above freezing (38F)
        # Warmer = faster melt = more water volume
        temp_factor = min(1.0, (current_temp - freezing) / 6.0)
        snow_cover_melt = depth_factor * temp_factor * 100
        if snow_cover_melt > 10:
            factors.append(
                f"Snow cover melt ({effective_snow_depth:.1f} in at {current_temp:.0f}F)"
            )

    # --- Sub-score 2: Salt-melt contamination (25%) ---
    # Heavy snow → more road salt applied → when it melts, conductive brine
    # infiltrates manholes and cable vaults causing short circuits and fires.
    salt_melt = 0.0
    effective_snow_for_salt = max(effective_snow_depth, total_snow + snow_rate)
    if current_temp >= freezing and effective_snow_for_salt > 0.5:
        # More snow = more salt applied by road crews; saturates at 6 inches
        snow_factor = min(1.0, effective_snow_for_salt / 6.0)
        # Warmer above freezing = faster melt dissolving more salt; saturates at 8F
        melt_intensity = min(1.0, (current_temp - freezing) / 8.0)
        salt_melt = snow_factor * melt_intensity * 100
        if salt_melt > 15:
            factors.append(
                f"Salt-melt brine risk ({effective_snow_for_salt:.1f} in snow + "
                f"{current_temp - freezing:.0f}F above freezing)"
            )

    # --- Sub-score 3: Melt potential (15%) ---
    melt_potential = 0.0
    if current_temp > freezing and snow_present:
        temp_factor = min(1.0, (current_temp - freezing) / 10.0)  # saturates at 10F above
        snow_factor = min(1.0, (effective_snow_depth + ice_accum) / 4.0)  # saturates at 4in
        melt_potential = (temp_factor * 0.5 + snow_factor * 0.5) * 100
        factors.append(f"Active snowmelt conditions ({effective_snow_depth:.1f} in snow on ground)")

    # --- Sub-score 4: Rain-on-snow (10%) ---
    rain_on_snow = 0.0
    if precip_rate > 0 and snow_present and current_temp > freezing:
        precip_factor = min(1.0, precip_rate / 0.5)  # saturates at 0.5 in/hr
        # Deeper snow pack = more melt volume when rain hits it
        depth_factor = min(1.0, effective_snow_depth / 6.0) if effective_snow_depth > 0 else 0.3
        rain_on_snow = precip_factor * (0.5 + 0.5 * depth_factor) * 100
        factors.append("Rain-on-snow accelerating melt")

    # --- Sub-score 5: Temperature trend (10%) ---
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

    # --- Sub-score 6: Freeze-thaw cycles (5%) ---
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

    # --- Rapid warming premium (research-backed) ---
    # Historical data: worst underground outages occur during the transition
    # from extreme cold to warming ("first warm day after storm").
    # Fresh salt hasn't been washed away, frozen ground prevents drainage,
    # thermal stress on cable insulation from rapid temp change.
    rapid_warming_bonus = 0.0
    if temp_trend_f_per_hr > 1.5 and current_temp > freezing and snow_present:
        # Scale bonus by warming rate: 1.5 F/hr → 10%, 3+ F/hr → 25%
        rapid_warming_bonus = min(25.0, (temp_trend_f_per_hr - 1.0) * 12.5)
        if rapid_warming_bonus > 5:
            factors.append(f"Rapid warming premium (+{rapid_warming_bonus:.0f}%)")

    # --- Weighted combination ---
    raw_score = (
        snow_cover_melt * 0.35
        + salt_melt * 0.25
        + melt_potential * 0.15
        + rain_on_snow * 0.10
        + temp_trend_score * 0.10
        + ftc_score * 0.05
    ) + rapid_warming_bonus

    # Apply modifiers
    final_score = raw_score * density * season
    final_score = max(0, min(100, final_score))

    if density >= 0.8:
        factors.append("Very high underground melt vulnerability (aging infrastructure)")
    elif density >= 0.5:
        factors.append("High underground infrastructure density")

    return MeltRisk(
        zone_id=zone_id,
        score=round(final_score, 1),
        level=_score_to_level(final_score),
        temperature_trend_f_per_hr=round(temp_trend_f_per_hr, 2),
        melt_potential=round(melt_potential, 1),
        rain_on_snow_risk=round(rain_on_snow, 1),
        salt_melt_risk=round(salt_melt, 1),
        snow_depth_in=round(effective_snow_depth, 1),
        freeze_thaw_cycles_48h=freeze_thaw_cycles,
        contributing_factors=factors,
    )
