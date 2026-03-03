"""Underground melt risk model.

Snowmelt/ice-melt causes manhole events and cable failures (2000+/year in NYC,
peaking Feb-Mar). Uses 48h weather history to detect dangerous melt conditions.

Six sub-scores:
- Snow cover melt (35%): Snow on ground + above-freezing temps = active melt
  infiltrating underground infrastructure. Primary driver.
- Salt-melt contamination (25%): Road salt creates conductive brine that
  infiltrates manholes/vaults causing short circuits and fires. Three pathways:
  (a) snow-based salt (existing), (b) ice-based salt (freezing rain/sleet),
  (c) residual salt from prior treatment (decays over 48h).
- Melt potential (15%): Temperature above freezing × snow depth interaction
- Rain-on-snow / rain infiltration (10%): Precipitation accelerating melt or
  causing drainage problems. Two pathways: (a) rain-on-snow (existing),
  (b) rain-on-frozen-ground (prolonged cold impairs drainage, salt residue
  washes into manholes as conductive brine).
- Temperature trend (10%): Rate of warming from <32F to >40F
- Freeze-thaw cycling (5%): Count of 32F crossings in 48h

Additive bonuses:
- Rapid warming premium (0-25): Fast warming with snow present
- Cold-rain transition bonus (0-20): Rain after prolonged freeze, amplified
  by residual salt (triple threat: cold ground + rain + salt brine)

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


_ICE_KEYWORDS = ("freezing rain", "ice", "sleet", "ice pellets", "glaze")


def _analyze_salt_history(
    observations: list[WeatherObservation],
    freezing: float,
) -> tuple[float, float]:
    """Scan 48h observations for ice events and salt-application conditions.

    Returns:
        (ice_hours_ago, residual_salt_score):
        - ice_hours_ago: hours since last ice condition (inf if none)
        - residual_salt_score: 0-100, full strength 0-24h, linear decay to 0 at 48h
    """
    if not observations:
        return float("inf"), 0.0

    last_ice_idx: int | None = None
    for i in range(len(observations) - 1, -1, -1):
        obs = observations[i]
        # Ice event: ice accumulation or icy condition text
        # Use try/except for robustness with mock objects in tests
        try:
            ice_accum = float(obs.ice_accum_in or 0)
        except (TypeError, ValueError):
            ice_accum = 0.0
        try:
            cond = str(obs.condition_text or "").lower()
        except (TypeError, ValueError):
            cond = ""
        try:
            temp = float(obs.temperature_f) if obs.temperature_f is not None else 50.0
        except (TypeError, ValueError):
            temp = 50.0

        is_ice_event = ice_accum > 0 or any(kw in cond for kw in _ICE_KEYWORDS)
        # Salt is also applied for snow/ice when temp is in treatment range (15-freezing)
        try:
            snow_rate = float(obs.snow_rate_in_hr or 0)
        except (TypeError, ValueError):
            snow_rate = 0.0
        is_salt_condition = (15.0 <= temp <= freezing) and (snow_rate > 0 or is_ice_event)

        if is_ice_event or is_salt_condition:
            last_ice_idx = i
            break

    if last_ice_idx is None:
        return float("inf"), 0.0

    # Approximate hours ago: each observation ~15min apart
    obs_since = len(observations) - 1 - last_ice_idx
    ice_hours_ago = obs_since * 0.25

    # Residual salt score: full strength 0-24h, linear decay to 0 at 48h
    if ice_hours_ago <= 24.0:
        residual_salt_score = 100.0
    elif ice_hours_ago <= 48.0:
        residual_salt_score = 100.0 * (1.0 - (ice_hours_ago - 24.0) / 24.0)
    else:
        residual_salt_score = 0.0

    return ice_hours_ago, residual_salt_score


def _analyze_cold_stretch(
    temps: list[float],
    freezing: float,
) -> tuple[int, bool]:
    """Count below-freezing hours in the temperature list.

    Returns:
        (cold_hours, ground_frozen):
        - cold_hours: number of hours below freezing (temps are ~15min intervals)
        - ground_frozen: True when cold_hours >= 24
    """
    if not temps:
        return 0, False

    below_freezing_intervals = sum(1 for t in temps if t < freezing)
    cold_hours = int(below_freezing_intervals * 0.25)  # ~15min intervals
    ground_frozen = cold_hours >= 24

    return cold_hours, ground_frozen


def compute(
    zone_id: str,
    weather: WeatherConditions,
    observations: list[WeatherObservation] | None = None,
    treatment_score: float | None = None,
) -> MeltRisk:
    """Compute underground melt risk for a zone.

    Args:
        zone_id: Zone identifier
        weather: Current weather conditions
        observations: Optional 48h historical weather observations from DB
        treatment_score: Optional 0-1 score from real salt/plow treatment APIs.
            Boosts or dampens the weather-inferred salt_melt sub-score.
            None = no data, preserves existing behavior exactly.
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

    # Analyze salt treatment history and cold stretch for enhanced sub-scores
    ice_hours_ago, residual_salt_score = _analyze_salt_history(observations or [], freezing)
    cold_hours, ground_frozen = _analyze_cold_stretch(temps, freezing)

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
    # Three pathways: (a) snow-based salt, (b) ice-based salt, (c) residual salt.
    # Score = max of all three pathways.
    salt_melt = 0.0
    effective_snow_for_salt = max(effective_snow_depth, total_snow + snow_rate)

    # (a) Snow-based salt — existing logic: heavy snow → road salt applied
    snow_salt = 0.0
    if current_temp >= freezing and effective_snow_for_salt > 0.5:
        snow_factor = min(1.0, effective_snow_for_salt / 6.0)
        melt_intensity = min(1.0, (current_temp - freezing) / 8.0)
        snow_salt = snow_factor * melt_intensity * 100

    # (b) Ice-based salt — freezing rain/sleet/ice triggers salt application
    ice_salt = 0.0
    is_ice_condition = ice_accum > 0 or any(kw in condition_text for kw in _ICE_KEYWORDS)
    recent_ice = ice_hours_ago < 12.0
    if current_temp >= freezing and (is_ice_condition or recent_ice):
        ice_factor = min(1.0, max(ice_accum, 0.1) / 0.5)  # saturates at 0.5" ice
        melt_intensity = min(1.0, (current_temp - freezing) / 8.0)
        ice_salt = ice_factor * melt_intensity * 100

    # (c) Residual salt — salt persists 24-48h after application, dissolves when warm
    residual_salt = 0.0
    if residual_salt_score > 0 and current_temp >= freezing:
        rain_amplifier = 1.0 + min(1.0, precip_rate / 0.3)  # rain washes salt into manholes
        residual_salt = residual_salt_score * 0.6 * rain_amplifier  # cap at 80% of active

    salt_melt = max(snow_salt, ice_salt, residual_salt)

    # --- Treatment data adjustment ---
    # Real salt/plow API data boosts or dampens weather-inferred salt_melt.
    # None (no data) preserves existing behavior exactly.
    if treatment_score is not None:
        if treatment_score > 0.5:
            # Active treatment confirmed — boost up to +30%
            salt_melt *= 1.0 + (treatment_score - 0.5) * 0.6
            # If treatment detected but weather inference missed it, inject minimum
            if salt_melt < 1.0 and snow_present:
                salt_melt = treatment_score * 40
                factors.append(
                    f"Salt treatment detected without weather signal "
                    f"(coverage {treatment_score * 100:.0f}%)"
                )
            else:
                factors.append(
                    f"Confirmed salt treatment (coverage {treatment_score * 100:.0f}%)"
                )
        elif treatment_score >= 0.1:
            # Some treatment activity — modest boost up to +10%
            salt_melt *= 1.0 + treatment_score * 0.2
        elif treatment_score == 0.0:
            # No treatment despite conditions — dampen by 15%
            salt_melt *= 0.85
    salt_melt = min(100.0, salt_melt)

    if salt_melt > 15:
        if ice_salt >= snow_salt and ice_salt >= residual_salt:
            factors.append(
                f"Salt-melt brine from ice treatment ({ice_accum:.2f} in ice, "
                f"{current_temp - freezing:.0f}F above freezing)"
            )
        elif residual_salt >= snow_salt:
            factors.append(
                f"Residual salt dissolving ({ice_hours_ago:.0f}h since treatment, "
                f"strength {residual_salt_score:.0f}%)"
            )
        else:
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

    # --- Sub-score 4: Rain infiltration (10%) ---
    # Two pathways: (a) rain-on-snow, (b) rain-on-frozen-ground
    rain_infiltration = 0.0

    # (a) Rain-on-snow — existing logic
    rain_on_snow_component = 0.0
    if precip_rate > 0 and snow_present and current_temp > freezing:
        precip_factor = min(1.0, precip_rate / 0.5)  # saturates at 0.5 in/hr
        depth_factor = min(1.0, effective_snow_depth / 6.0) if effective_snow_depth > 0 else 0.3
        rain_on_snow_component = precip_factor * (0.5 + 0.5 * depth_factor) * 100

    # (b) Rain-on-frozen-ground — prolonged cold impairs drainage
    frozen_ground_component = 0.0
    if precip_rate > 0 and current_temp > freezing and ground_frozen:
        precip_factor = min(1.0, precip_rate / 0.5)
        freeze_severity = min(1.0, cold_hours / 48.0)
        frozen_ground_component = precip_factor * freeze_severity * 100
        # Amplify if residual salt present (brine washes into manholes)
        if residual_salt_score > 30:
            frozen_ground_component = min(100.0, frozen_ground_component * 1.3)

    rain_infiltration = max(rain_on_snow_component, frozen_ground_component)
    if rain_infiltration > 0:
        if rain_on_snow_component >= frozen_ground_component:
            factors.append("Rain-on-snow accelerating melt")
        else:
            factors.append(
                f"Rain on frozen ground ({cold_hours}h below freezing, impaired drainage)"
            )

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

    # --- Cold-rain transition bonus (0-20 additive) ---
    # Rain after prolonged freeze: frozen ground prevents drainage,
    # salt residue washes into manholes as conductive brine.
    cold_rain_bonus = 0.0
    if ground_frozen and precip_rate > 0 and current_temp > freezing:
        freeze_duration_factor = min(1.0, cold_hours / 48.0)
        rain_factor = min(1.0, precip_rate / 0.3)
        cold_rain_bonus = freeze_duration_factor * rain_factor * 20.0
        # Triple threat amplifier: cold ground + rain + residual salt
        if residual_salt_score > 30:
            cold_rain_bonus = min(20.0, cold_rain_bonus * 1.4)
        cold_rain_bonus = min(20.0, cold_rain_bonus)
        if cold_rain_bonus > 3:
            factors.append(f"Cold-rain transition ({cold_hours}h frozen \u2192 rain, +{cold_rain_bonus:.0f}%)")

    # --- Weighted combination ---
    raw_score = (
        snow_cover_melt * 0.35
        + salt_melt * 0.25
        + melt_potential * 0.15
        + rain_infiltration * 0.10
        + temp_trend_score * 0.10
        + ftc_score * 0.05
    ) + rapid_warming_bonus + cold_rain_bonus

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
        rain_on_snow_risk=round(rain_infiltration, 1),
        salt_melt_risk=round(salt_melt, 1),
        snow_depth_in=round(effective_snow_depth, 1),
        freeze_thaw_cycles_48h=freeze_thaw_cycles,
        contributing_factors=factors,
    )
