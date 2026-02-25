"""Vegetation risk model for overhead distribution systems.

Factors:
- Wind × foliage interaction (deciduous sail effect)
- Snow/ice loading on branches (major winter limb-break driver)
- Soil saturation (root failure, tree toppling)
- Ice accumulation on lines and branches
- Per-zone overhead line exposure (Manhattan ~0% overhead, Westchester ~85%)

In winter, heavy wet snow on branches causes more overhead outages than wind
alone. Even bare branches accumulate wet snow at 28-34°F, and the weight
causes limb failure onto overhead lines.
"""

from datetime import datetime, timezone

from app.schemas.impact import VegetationRisk
from app.schemas.weather import WeatherConditions


# Fraction of distribution system that is overhead (exposed to tree risk).
# Manhattan is almost entirely underground; Westchester/O&R heavily overhead.
OVERHEAD_EXPOSURE: dict[str, float] = {
    "CONED-MAN": 0.02,   # Almost 100% underground
    "CONED-BKN": 0.25,   # Southern Brooklyn has some overhead
    "CONED-QNS": 0.45,   # Eastern Queens significant overhead
    "CONED-BRX": 0.35,   # Mix of overhead and underground
    "CONED-SI": 0.70,    # Mostly overhead
    "CONED-WST": 0.85,   # Heavily overhead, dense tree canopy
    "OR-ORA": 0.90,
    "OR-ROC": 0.90,
    "OR-SUL": 0.95,
    "OR-BER": 0.85,
    "OR-SSX": 0.95,
}

# Tree canopy density per zone (affects branch-on-wire probability)
TREE_CANOPY_DENSITY: dict[str, float] = {
    "CONED-MAN": 0.10,
    "CONED-BKN": 0.30,
    "CONED-QNS": 0.45,
    "CONED-BRX": 0.40,
    "CONED-SI": 0.55,
    "CONED-WST": 0.80,   # Dense suburban canopy
    "OR-ORA": 0.75,
    "OR-ROC": 0.70,
    "OR-SUL": 0.85,      # Rural, heavy forest
    "OR-BER": 0.65,
    "OR-SSX": 0.85,
}


def compute(weather: WeatherConditions) -> VegetationRisk:
    zone_id = weather.zone_id
    month = datetime.now(timezone.utc).month
    foliage = _foliage_factor(month)
    overhead = OVERHEAD_EXPOSURE.get(zone_id, 0.5)
    canopy = TREE_CANOPY_DENSITY.get(zone_id, 0.5)

    wind_veg = _wind_vegetation_score(weather.wind_speed_mph, weather.wind_gust_mph, foliage)
    soil = _soil_saturation_score(weather.precip_rate_in_hr, weather.precip_probability_pct)
    ice_load = _ice_loading_score(weather.ice_accum_in)
    snow_load = _snow_loading_score(
        weather.snow_rate_in_hr, weather.snow_depth_in,
        weather.temperature_f, weather.condition_text,
    )

    # Weighted combination — snow loading is critical in winter
    raw_score = (
        wind_veg * 0.35
        + snow_load * 0.25
        + ice_load * 0.25
        + soil * 0.15
    )

    # Apply zone exposure: overhead lines + tree canopy = outage probability
    # Zones with no overhead lines have near-zero vegetation risk
    exposure_factor = overhead * (0.4 + 0.6 * canopy)
    score = min(100.0, raw_score * max(0.05, exposure_factor))

    soil_label = "normal"
    if soil > 60:
        soil_label = "saturated"
    elif soil > 30:
        soil_label = "moist"

    return VegetationRisk(
        zone_id=zone_id,
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


def _snow_loading_score(
    snow_rate: float | None,
    snow_depth: float | None,
    temp_f: float | None,
    condition_text: str | None,
) -> float:
    """Score snow loading on branches/lines.

    Heavy wet snow (28-34°F) is the most dangerous for branch breakage.
    Even bare winter branches accumulate wet snow weight.
    Existing snow on the ground implies recent accumulation on branches.
    """
    score = 0.0
    temp = temp_f or 32.0
    rate = snow_rate or 0.0
    depth = snow_depth or 0.0
    cond = (condition_text or "").lower()

    # Active snowfall loading on branches
    if rate > 0:
        # Wet snow (28-34°F) is 3x heavier than dry snow
        wet_factor = 1.0
        if 28 <= temp <= 34:
            wet_factor = 3.0  # wet heavy snow
        elif 25 <= temp < 28 or 34 < temp <= 37:
            wet_factor = 2.0  # partially wet
        # else dry/cold snow: lighter, blows off

        rate_score = min(100.0, rate * 40 * wet_factor)
        score = max(score, rate_score)

    # Snow conditions from forecast (even without rate data)
    if "heavy snow" in cond or "blizzard" in cond:
        wet_factor = 3.0 if 28 <= temp <= 34 else 1.5
        score = max(score, 70 * wet_factor / 3.0)
    elif "snow" in cond and "light" not in cond:
        wet_factor = 2.5 if 28 <= temp <= 34 else 1.2
        score = max(score, 50 * wet_factor / 2.5)
    elif "light snow" in cond:
        wet_factor = 2.0 if 28 <= temp <= 34 else 1.0
        score = max(score, 30 * wet_factor / 2.0)

    # Existing snow depth implies accumulated weight on branches
    # Branches shed snow over time, but recent heavy depth = heavy loading
    if depth > 2:
        depth_factor = min(1.0, depth / 12.0)  # saturates at 12"
        # Heavier loading when temps are in wet-snow range
        temp_factor = 1.5 if 28 <= temp <= 37 else 0.8
        branch_load = depth_factor * temp_factor * 60
        score = max(score, branch_load)

    return min(100.0, score)


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
