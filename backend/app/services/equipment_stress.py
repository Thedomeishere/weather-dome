"""Equipment stress model.

Transformer heat: ambient + load^2 - wind cooling
Line sag: temperature + load
"""

from app.schemas.impact import EquipmentStress
from app.schemas.weather import WeatherConditions
from app.territory.definitions import ZoneDefinition


def compute(
    weather: WeatherConditions,
    zone: ZoneDefinition,
    load_pct: float = 0.5,
) -> EquipmentStress:
    transformer = _transformer_stress(
        ambient_f=weather.temperature_f or 70,
        load_pct=load_pct,
        wind_mph=weather.wind_speed_mph or 0,
    )
    line_sag = _line_sag_risk(
        temp_f=weather.temperature_f or 70,
        load_pct=load_pct,
        wind_mph=weather.wind_speed_mph or 0,
        ice_in=weather.ice_accum_in or 0,
    )

    # Overall: transformers slightly more critical
    score = transformer * 0.55 + line_sag * 0.45

    return EquipmentStress(
        zone_id=weather.zone_id,
        score=round(score, 1),
        level=_score_to_level(score),
        transformer_risk=round(transformer, 1),
        line_sag_risk=round(line_sag, 1),
    )


def _transformer_stress(ambient_f: float, load_pct: float, wind_mph: float) -> float:
    """Transformer hot-spot temperature estimate.
    High ambient + high load squared heating - wind cooling effect.
    """
    # Temperature contribution: stress rises above 85F
    temp_stress = max(0, (ambient_f - 85) / 30) * 40

    # Load heating: quadratic (I²R losses)
    load_stress = (load_pct ** 2) * 60

    # Wind cooling benefit
    wind_cooling = min(20, wind_mph * 0.5)

    score = max(0, temp_stress + load_stress - wind_cooling)
    return min(100.0, score)


def _line_sag_risk(
    temp_f: float, load_pct: float, wind_mph: float, ice_in: float
) -> float:
    """Conductor sag risk from thermal expansion + ice weight.
    High temp = expansion/sag, ice = weight/sag, wind = galloping.
    """
    # Thermal sag: conductors expand above ~90F
    thermal = max(0, (temp_f - 90) / 25) * 30

    # Load current heating
    load_heat = (load_pct ** 1.5) * 25

    # Ice weight loading
    ice_weight = min(40, ice_in * 160) if ice_in else 0

    # Wind galloping with ice
    galloping = 0
    if ice_in and ice_in > 0.05 and wind_mph > 15:
        galloping = min(30, wind_mph * 0.5 * ice_in * 20)

    score = thermal + load_heat + ice_weight + galloping
    return min(100.0, score)


def _score_to_level(score: float) -> str:
    if score < 25:
        return "Low"
    if score < 50:
        return "Moderate"
    if score < 75:
        return "High"
    return "Extreme"
