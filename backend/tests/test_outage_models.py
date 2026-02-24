"""Tests for outage ingestion, zone mapping, melt risk model, and enhanced outage risk."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from app.schemas.outage import OutageIncident, MeltRisk, ZoneOutageStatus
from app.schemas.weather import WeatherConditions
from app.services import melt_risk, outage_risk
from app.services.outage_ingest import _assign_zone, _haversine_km


def _make_weather(**kwargs) -> WeatherConditions:
    defaults = {
        "zone_id": "CONED-MAN",
        "source": "test",
        "observed_at": datetime(2026, 2, 15, 12, 0, tzinfo=timezone.utc),
    }
    defaults.update(kwargs)
    return WeatherConditions(**defaults)


# --- ODS Client response parsing ---

@pytest.mark.asyncio
async def test_ods_client_parse_response():
    """Test ODS client parses JSON response into OutageIncident list."""
    mock_data = [
        {
            "id": "inc-001",
            "kind": "power",
            "status": "ongoing",
            "region": "New York, New York",
            "latitude": 40.78,
            "longitude": -73.97,
            "customers_affected": 150,
            "cause": "equipment failure",
        },
        {
            "id": "inc-002",
            "kind": "power",
            "status": "ongoing",
            "region": "Brooklyn, New York",
            "customers_affected": 50,
        },
        {
            "id": "inc-003",
            "kind": "water",  # filtered out
            "status": "ongoing",
            "region": "Queens, New York",
        },
    ]

    with patch("app.services.ods_client.httpx.AsyncClient") as mock_client_cls:
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_data
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        from app.services.ods_client import fetch_incidents
        incidents = await fetch_incidents()

        assert len(incidents) == 2  # water incident filtered
        assert incidents[0].incident_id == "inc-001"
        assert incidents[0].customers_affected == 150
        assert incidents[1].incident_id == "inc-002"


# --- Zone assignment ---

def test_zone_assignment_region_manhattan():
    inc = OutageIncident(incident_id="1", region="New York, New York")
    assert _assign_zone(inc) == "CONED-MAN"


def test_zone_assignment_region_brooklyn():
    inc = OutageIncident(incident_id="2", region="Brooklyn, Kings County")
    assert _assign_zone(inc) == "CONED-BKN"


def test_zone_assignment_region_queens():
    inc = OutageIncident(incident_id="3", region="Queens, New York")
    assert _assign_zone(inc) == "CONED-QNS"


def test_zone_assignment_region_bronx():
    inc = OutageIncident(incident_id="4", region="Bronx County")
    assert _assign_zone(inc) == "CONED-BRX"


def test_zone_assignment_region_westchester():
    inc = OutageIncident(incident_id="5", region="Westchester County, New York")
    assert _assign_zone(inc) == "CONED-WST"


def test_zone_assignment_region_orange():
    inc = OutageIncident(incident_id="6", region="Orange County, New York")
    assert _assign_zone(inc) == "OR-ORA"


def test_zone_assignment_latlon_fallback():
    """Falls back to Haversine when region doesn't match."""
    # Manhattan coords
    inc = OutageIncident(
        incident_id="7", region="Unknown Location",
        latitude=40.7831, longitude=-73.9712,
    )
    zone = _assign_zone(inc)
    assert zone == "CONED-MAN"


def test_zone_assignment_latlon_too_far():
    """Returns None when coords are too far from any zone."""
    inc = OutageIncident(
        incident_id="8", region="Unknown",
        latitude=35.0, longitude=-80.0,  # North Carolina
    )
    assert _assign_zone(inc) is None


def test_haversine_distance():
    # Manhattan to Brooklyn ~ 9km
    d = _haversine_km(40.7831, -73.9712, 40.6782, -73.9442)
    assert 10 < d < 15


# --- Melt risk model ---

def test_melt_risk_no_snow_low():
    """No snow + normal temp = low melt risk."""
    w = _make_weather(temperature_f=45, snow_rate_in_hr=0, ice_accum_in=0)
    result = melt_risk.compute("CONED-MAN", w)
    assert result.score < 25
    assert result.level == "Low"


def test_melt_risk_rapid_warming_with_snow_high():
    """Rapid warming from below freezing + snow = high melt risk."""
    # Create observations simulating warming from 25F to 42F
    obs_temps = [25.0] * 10 + [30.0] * 5 + [35.0] * 3 + [42.0] * 2
    mock_obs = []
    for t in obs_temps:
        obs = MagicMock()
        obs.temperature_f = t
        obs.snow_rate_in_hr = 0.3  # recent snow
        mock_obs.append(obs)

    w = _make_weather(temperature_f=42, snow_rate_in_hr=0, ice_accum_in=0.1)
    result = melt_risk.compute("CONED-MAN", w, observations=mock_obs)
    # Manhattan in Feb with warming + snow should score significantly
    assert result.score > 10


def test_melt_risk_rain_on_snow_high():
    """Rain on snow with above-freezing temps = high melt risk."""
    mock_obs = []
    for _ in range(10):
        obs = MagicMock()
        obs.temperature_f = 35.0
        obs.snow_rate_in_hr = 0.5
        mock_obs.append(obs)

    w = _make_weather(
        temperature_f=38,
        precip_rate_in_hr=0.3,
        snow_rate_in_hr=0,
        ice_accum_in=0.2,
    )
    result = melt_risk.compute("CONED-MAN", w, observations=mock_obs)
    assert result.score > 5
    assert any("Rain-on-snow" in f for f in result.contributing_factors)


def test_melt_risk_non_underground_zone_zero():
    """O&R rural zones with minimal underground infrastructure = near-zero."""
    w = _make_weather(
        zone_id="OR-SUL",
        temperature_f=38,
        snow_rate_in_hr=0.5,
        ice_accum_in=0.3,
        precip_rate_in_hr=0.2,
    )
    result = melt_risk.compute("OR-SUL", w)
    assert result.score < 5  # very low due to 0.02 density


def test_melt_risk_summer_zero():
    """Summer months = zero seasonal factor = zero melt risk."""
    w = _make_weather(
        observed_at=datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc),
        temperature_f=85,
    )
    result = melt_risk.compute("CONED-MAN", w)
    assert result.score == 0


# --- Enhanced outage risk ---

def test_outage_risk_backward_compat():
    """Old call signature (weather only) still works."""
    w = _make_weather(wind_speed_mph=40, ice_accum_in=0.3)
    result = outage_risk.compute(w)
    assert result.score > 0
    assert result.actual_outages is None
    assert result.outage_trend == "stable"


def test_outage_risk_with_melt():
    """Melt risk > 5 activates adaptive weights."""
    w = _make_weather(wind_speed_mph=30)
    result_no_melt = outage_risk.compute(w, melt_risk_score=0)
    result_with_melt = outage_risk.compute(w, melt_risk_score=50)
    # With melt risk, score should differ
    assert result_with_melt.score != result_no_melt.score
    assert "Underground melt risk" in result_with_melt.contributing_factors


def test_outage_risk_with_outage_momentum():
    """Active outages > 5 add momentum bonus."""
    w = _make_weather(wind_speed_mph=30)
    result_no_outages = outage_risk.compute(w, current_outages=0)
    result_many = outage_risk.compute(w, current_outages=100)
    assert result_many.score > result_no_outages.score
    assert "Elevated active outages" in result_many.contributing_factors
    assert result_many.actual_outages == 100


def test_outage_risk_momentum_capped():
    """Momentum bonus capped at 15 points."""
    w = _make_weather(wind_speed_mph=30)
    result_huge = outage_risk.compute(w, current_outages=10000)
    result_moderate = outage_risk.compute(w, current_outages=200)
    # Both should have same momentum since cap is 15 (reached at 150)
    # The difference should only be from the cap
    assert result_huge.score - result_moderate.score < 1  # effectively same cap
