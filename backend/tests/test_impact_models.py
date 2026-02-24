from datetime import datetime, timezone

from app.schemas.weather import WeatherConditions
from app.schemas.impact import OutageRisk
from app.services import outage_risk, vegetation_risk, load_forecast, equipment_stress, crew_deployment
from app.territory.definitions import CONED_ZONES, OR_ZONES


def _make_weather(**kwargs) -> WeatherConditions:
    defaults = {
        "zone_id": "CONED-MAN",
        "source": "test",
        "observed_at": datetime.now(timezone.utc),
    }
    defaults.update(kwargs)
    return WeatherConditions(**defaults)


def test_outage_risk_calm():
    w = _make_weather(wind_speed_mph=5, ice_accum_in=0)
    result = outage_risk.compute(w)
    assert result.level == "Low"
    assert result.score < 10


def test_outage_risk_high_wind():
    w = _make_weather(wind_speed_mph=60, wind_gust_mph=75)
    result = outage_risk.compute(w)
    assert result.level in ("Moderate", "High", "Extreme")
    assert result.score > 25


def test_outage_risk_ice_storm():
    w = _make_weather(wind_speed_mph=40, ice_accum_in=0.5)
    result = outage_risk.compute(w)
    assert result.score > 50  # Wind + ice synergy
    assert "Wind+Ice synergy" in result.contributing_factors


def test_vegetation_risk_low():
    w = _make_weather(wind_speed_mph=10)
    result = vegetation_risk.compute(w)
    assert result.level == "Low"


def test_vegetation_risk_high_wind():
    w = _make_weather(wind_speed_mph=55, wind_gust_mph=70)
    result = vegetation_risk.compute(w)
    assert result.score > 10  # at least some risk


def test_load_forecast_mild():
    w = _make_weather(temperature_f=65)
    zone = CONED_ZONES[0]  # Manhattan
    result = load_forecast.compute(w, zone)
    assert result.risk_level == "Low"
    assert result.load_mw > 0


def test_load_forecast_hot():
    w = _make_weather(temperature_f=100)
    zone = CONED_ZONES[0]
    result = load_forecast.compute(w, zone)
    assert result.pct_capacity > 60  # high load


def test_load_forecast_or_territory():
    w = _make_weather(zone_id="OR-ORA", temperature_f=95)
    zone = OR_ZONES[0]
    result = load_forecast.compute(w, zone)
    assert result.territory == "OR"
    assert result.capacity_mw < 1000  # OR peak * share


def test_equipment_stress_normal():
    w = _make_weather(temperature_f=70, wind_speed_mph=10)
    zone = CONED_ZONES[0]
    result = equipment_stress.compute(w, zone, load_pct=0.5)
    assert result.level == "Low"


def test_equipment_stress_hot_loaded():
    w = _make_weather(temperature_f=105, wind_speed_mph=2)
    zone = CONED_ZONES[0]
    result = equipment_stress.compute(w, zone, load_pct=0.95)
    assert result.score > 30


def test_crew_deployment_low_risk():
    o = OutageRisk(zone_id="CONED-MAN", score=10, level="Low", estimated_outages=5)
    v = vegetation_risk.compute(_make_weather(wind_speed_mph=5))
    zone = CONED_ZONES[0]
    result = crew_deployment.compute(zone, o, v)
    assert result.total_crews > 0
    assert not result.mutual_aid_needed


def test_crew_deployment_extreme():
    o = OutageRisk(zone_id="CONED-MAN", score=85, level="Extreme", estimated_outages=5000)
    v = vegetation_risk.compute(_make_weather(wind_speed_mph=60, ice_accum_in=0.3))
    zone = CONED_ZONES[0]
    result = crew_deployment.compute(zone, o, v)
    assert result.mutual_aid_needed
    assert result.pre_stage
    assert result.total_crews > 10
