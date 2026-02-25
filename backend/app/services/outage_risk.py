"""Outage risk scoring model.

Weighted scoring with snow component:
  Normal:    wind(0.35) + ice(0.25) + snow(0.13) + lightning(0.12) + precip(0.15)
  With melt: wind(0.30) + ice(0.22) + snow(0.10) + lightning(0.10) + precip(0.12) + melt(0.16)

Synergy bonuses for wind+ice and wind+snow.

Enhanced with:
- Dedicated snow scoring for wet/heavy snow loading
- Underground melt risk integration (adaptive weights when melt > 5)
- Outage momentum bonus from live outage data
"""

from app.config import settings
from app.schemas.impact import OutageRisk
from app.schemas.weather import WeatherConditions


# Baseline outage floor per zone: utility systems have non-zero outage rates
# even in fair weather due to equipment aging, animal contact, vehicle strikes,
# dig-ins, etc. Derived from observed outage snapshot averages.
BASELINE_OUTAGES: dict[str, int] = {
    "CONED-MAN": 60,
    "CONED-BKN": 35,
    "CONED-QNS": 30,
    "CONED-BRX": 20,
    "CONED-SI": 8,
    "CONED-WST": 40,
    "OR-ORA": 5,
    "OR-ROC": 3,
    "OR-SUL": 2,
    "OR-BER": 3,
    "OR-SSX": 2,
}


def compute(
    weather: WeatherConditions,
    current_outages: int | None = None,
    melt_risk_score: float = 0.0,
) -> OutageRisk:
    wind_score = _wind_score(weather.wind_speed_mph, weather.wind_gust_mph)
    ice_score = _ice_score(weather.ice_accum_in)
    snow_score = _snow_score(weather.snow_rate_in_hr)
    lightning_score = _lightning_score(weather.lightning_probability_pct)
    precip_score = _precip_score(
        weather.precip_rate_in_hr,
        weather.snow_rate_in_hr,
        weather.precip_probability_pct,
    )

    # Adaptive weights: when melt risk is present, allocate weight to it
    if melt_risk_score > 5:
        base_score = (
            wind_score * 0.30
            + ice_score * 0.22
            + snow_score * 0.10
            + lightning_score * 0.10
            + precip_score * 0.12
            + melt_risk_score * 0.16
        )
    else:
        base_score = (
            wind_score * 0.35
            + ice_score * 0.25
            + snow_score * 0.13
            + lightning_score * 0.12
            + precip_score * 0.15
        )

    # Synergy bonus: wind + ice together are disproportionately dangerous
    synergy = 0.0
    if wind_score > 30 and ice_score > 30:
        synergy = min(wind_score, ice_score) * 0.25

    # Synergy bonus: wind + snow = branch snap + line galloping
    snow_wind_synergy = 0.0
    if snow_score > 20 and wind_score > 20:
        snow_wind_synergy = min(snow_score, wind_score) * 0.2

    score = min(100.0, base_score + synergy + snow_wind_synergy)

    # Outage momentum: active outages indicate infrastructure stress the
    # weather model may not fully capture (e.g. ongoing restoration, cascading
    # failures). Cap at 25 points — even 150 outages shouldn't overwhelm.
    momentum = 0.0
    if current_outages is not None and current_outages > 5:
        momentum = min(25, current_outages * 0.2)
        score = min(100.0, score + momentum)

    factors = []
    if wind_score > 20:
        factors.append(f"Wind ({weather.wind_speed_mph or 0:.0f} mph)")
    if ice_score > 20:
        factors.append(f"Ice ({weather.ice_accum_in or 0:.2f} in)")
    if snow_score > 20:
        factors.append(f"Snow ({weather.snow_rate_in_hr or 0:.1f} in/hr)")
    if lightning_score > 20:
        factors.append("Lightning risk")
    if precip_score > 20:
        factors.append("Heavy precipitation")
    if synergy > 0:
        factors.append("Wind+Ice synergy")
    if snow_wind_synergy > 0:
        factors.append("Wind+Snow synergy")
    if melt_risk_score > 5:
        factors.append("Underground melt risk")
    if momentum > 0:
        factors.append("Elevated active outages")

    level = _score_to_level(score)
    estimated = _estimate_outages(score, weather.zone_id)

    # Determine trend from current_outages
    outage_trend = "stable"
    if current_outages is not None and current_outages > 10:
        outage_trend = "rising"

    return OutageRisk(
        zone_id=weather.zone_id,
        score=round(score, 1),
        level=level,
        estimated_outages=estimated,
        contributing_factors=factors,
        actual_outages=current_outages,
        outage_trend=outage_trend,
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


def _snow_score(snow_rate: float | None) -> float:
    """Score snow accumulation impact on infrastructure.

    < 2 in/hr: no risk (light snow)
    2-4 in/hr: ramp 0→40 (moderate wet snow loading)
    4-6 in/hr: ramp 40→70 (heavy, branch breakage)
    >= 6 in/hr: ramp 70→100 (extreme)
    """
    if not snow_rate or snow_rate < 2:
        return 0.0
    if snow_rate < 4:
        return ((snow_rate - 2) / 2) * 40
    if snow_rate < 6:
        return 40 + ((snow_rate - 4) / 2) * 30
    return min(100.0, 70 + ((snow_rate - 6) / 2) * 30)


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


def _estimate_outages(score: float, zone_id: str | None = None) -> int:
    """Estimate per-zone outages based on risk score.

    Includes a baseline floor — utility systems always have some outages
    from equipment aging, animal contact, vehicle strikes, dig-ins, etc.
    Weather-driven outages add on top of baseline.

    Applies calibration correction factor if available from the 2x/day
    calibration service (stored in outage_weather_correlations table).
    """
    baseline = BASELINE_OUTAGES.get(zone_id or "", 5)

    if score < 3:
        weather_outages = 0
    elif score < 25:
        # Smooth ramp: avoids cliff at old threshold of 10
        weather_outages = int((score - 3) * 1.8)
    elif score < 50:
        weather_outages = int(score * 10)
    elif score < 75:
        weather_outages = int(score * 40)
    else:
        weather_outages = int(score * 100)

    # Apply calibration correction if available
    correction = _get_calibration_correction(zone_id)
    return baseline + int(weather_outages * correction)


def _get_calibration_correction(zone_id: str | None) -> float:
    """Read latest calibration correction ratio for a zone.

    Cached in-memory to avoid DB reads on every call.
    Refreshed when calibration service runs.
    """
    if not zone_id:
        return 1.0
    cached = _calibration_cache.get(zone_id)
    if cached is not None:
        return cached
    try:
        from app.services.calibration import get_latest_calibration
        cal = get_latest_calibration(zone_id)
        if cal and "outage_correction_ratio" in cal:
            ratio = cal["outage_correction_ratio"]
            _calibration_cache[zone_id] = ratio
            return ratio
    except Exception:
        pass
    _calibration_cache[zone_id] = 1.0
    return 1.0


# In-memory cache for calibration corrections (refreshed on calibration runs)
_calibration_cache: dict[str, float] = {}
