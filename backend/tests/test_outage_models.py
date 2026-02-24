"""Tests for outage ingestion, zone mapping, melt risk model, and enhanced outage risk."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from app.schemas.outage import OutageIncident, MeltRisk, ZoneOutageStatus
from app.schemas.weather import WeatherConditions
from app.services import melt_risk, outage_risk
from app.services.outage_ingest import _assign_zone, _BOROUGH_TO_ZONE, _haversine_km
from app.services.coned_client import _parse_summary
from app.services.poweroutage_us_client import _OUTAGE_PATTERN, _distribute


def _make_weather(**kwargs) -> WeatherConditions:
    defaults = {
        "zone_id": "CONED-MAN",
        "source": "test",
        "observed_at": datetime(2026, 2, 15, 12, 0, tzinfo=timezone.utc),
    }
    defaults.update(kwargs)
    return WeatherConditions(**defaults)


# --- NYC 311 Client response parsing ---

@pytest.mark.asyncio
async def test_nyc311_client_parse_response():
    """Test NYC 311 client parses SODA JSON response into OutageIncident list."""
    mock_rows = [
        {
            "unique_key": "62000001",
            "created_date": "2026-02-24T08:30:00.000",
            "descriptor": "Lights Flickering",
            "borough": "MANHATTAN",
            "incident_address": "123 BROADWAY",
            "latitude": "40.7128",
            "longitude": "-74.0060",
            "status": "Open",
        },
        {
            "unique_key": "62000002",
            "created_date": "2026-02-24T09:15:00.000",
            "descriptor": "Entire Building",
            "borough": "BROOKLYN",
            "incident_address": "456 ATLANTIC AVE",
            "latitude": "40.6862",
            "longitude": "-73.9776",
            "status": "Open",
        },
    ]

    with patch("app.services.nyc311_client.httpx.AsyncClient") as mock_client_cls:
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_rows
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        from app.services.nyc311_client import fetch_incidents
        incidents = await fetch_incidents()

        assert len(incidents) == 2
        assert incidents[0].incident_id == "62000001"
        assert incidents[0].source == "nyc311"
        assert incidents[0].region == "MANHATTAN"
        assert incidents[0].cause == "Lights Flickering"
        assert incidents[1].incident_id == "62000002"
        assert incidents[1].latitude == 40.6862


# --- Zone assignment ---

def test_zone_assignment_borough_all():
    """NYC 311 borough field maps to correct ConEd zones."""
    for borough, expected_zone in _BOROUGH_TO_ZONE.items():
        inc = OutageIncident(incident_id="b1", source="nyc311", region=borough)
        assert _assign_zone(inc) == expected_zone, f"{borough} → {expected_zone}"


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


def test_melt_risk_salt_melt_heavy_snow():
    """Heavy snow accumulation + above-freezing temps → salt brine infiltration."""
    w = _make_weather(
        temperature_f=38,  # 6F above freezing, actively melting
        snow_rate_in_hr=3.0,  # heavy recent snow → heavy salt application
    )
    result = melt_risk.compute("CONED-MAN", w)
    assert result.salt_melt_risk > 20
    assert any("Salt-melt brine" in f for f in result.contributing_factors)


def test_melt_risk_salt_melt_cold_no_risk():
    """Snow below freezing → no melt → salt not dissolving → no salt-melt risk."""
    w = _make_weather(
        temperature_f=25,  # below freezing, no melt
        snow_rate_in_hr=4.0,
    )
    result = melt_risk.compute("CONED-MAN", w)
    assert result.salt_melt_risk == 0


def test_melt_risk_salt_melt_manhattan_vs_rural():
    """Manhattan (density 1.0) should have much higher salt-melt than rural O&R."""
    w = _make_weather(
        temperature_f=40,
        snow_rate_in_hr=3.0,
    )
    man_result = melt_risk.compute("CONED-MAN", w)
    # Same weather but rural zone
    rural_w = _make_weather(zone_id="OR-SUL", temperature_f=40, snow_rate_in_hr=3.0)
    rural_result = melt_risk.compute("OR-SUL", rural_w)
    assert man_result.score > rural_result.score * 10  # Manhattan >> rural


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


# --- ConEd Outage Map client ---

def test_coned_client_parse_summary():
    """ConEd client parses summaryFileData and distributes across 6 zones."""
    data = {
        "summaryFileData": {
            "total_outages": 293,
            "total_cust_a": {"val": 2395},
            "total_cust_s": 3626606,
            "date_generated": "2026-02-24T22:21:00",
        }
    }
    incidents = _parse_summary(data)
    assert len(incidents) == 6
    # All should be source="coned"
    assert all(i.source == "coned" for i in incidents)
    # Zone names should cover all ConEd zones
    zone_names = {i.region for i in incidents}
    assert zone_names == {"Manhattan", "Bronx", "Brooklyn", "Queens", "Staten Island", "Westchester"}
    # Customers should sum to total (allowing for rounding)
    total_cust = sum(i.customers_affected for i in incidents)
    assert abs(total_cust - 2395) <= 6  # rounding tolerance
    # Outage counts should sum to total (allowing for rounding)
    total_outages = sum(i.outage_count for i in incidents)
    assert abs(total_outages - 293) <= 6
    # Manhattan (30% share) should get ~88 outages
    man = [i for i in incidents if i.region == "Manhattan"][0]
    assert man.outage_count == round(293 * 0.30)


def test_coned_client_parse_summary_plain_int():
    """ConEd client handles total_cust_a as plain integer."""
    data = {
        "summaryFileData": {
            "total_outages": 10,
            "total_cust_a": 500,
            "date_generated": "2026-02-24T12:00:00",
        }
    }
    incidents = _parse_summary(data)
    assert len(incidents) == 6
    total_cust = sum(i.customers_affected for i in incidents)
    assert abs(total_cust - 500) <= 6
    total_outages = sum(i.outage_count for i in incidents)
    assert abs(total_outages - 10) <= 6


@pytest.mark.asyncio
async def test_coned_client_fetch():
    """ConEd client fetches metadata then data and returns incidents."""
    meta_json = {"directory": "2026_02_24_22_21_00"}
    data_json = {
        "summaryFileData": {
            "total_outages": 100,
            "total_cust_a": {"val": 1000},
            "total_cust_s": 3626606,
            "date_generated": "2026-02-24T22:21:00",
        }
    }

    mock_meta_resp = MagicMock()
    mock_meta_resp.json.return_value = meta_json
    mock_meta_resp.raise_for_status = MagicMock()

    mock_data_resp = MagicMock()
    mock_data_resp.json.return_value = data_json
    mock_data_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=[mock_meta_resp, mock_data_resp])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.coned_client.httpx.AsyncClient", return_value=mock_client):
        from app.services.coned_client import fetch_incidents
        incidents = await fetch_incidents()

    assert len(incidents) == 6
    assert all(i.source == "coned" for i in incidents)


# --- PowerOutage.us client ---

def test_poweroutage_us_scrape_parse():
    """Regex correctly parses 'X homes and businesses are without power'."""
    html = """
    <div class="report-container">
        <h2>Con Edison</h2>
        <p>12,345 homes and businesses are without power in the service area.</p>
    </div>
    """
    match = _OUTAGE_PATTERN.search(html)
    assert match is not None
    assert int(match.group(1).replace(",", "")) == 12345


def test_poweroutage_us_distribute():
    """Distribute creates 6 ConEd zone incidents proportional to peak_load_share."""
    incidents = _distribute(10000)
    assert len(incidents) == 6
    assert all(i.source == "poweroutage_us" for i in incidents)
    # Manhattan gets 30%
    man = [i for i in incidents if i.region == "Manhattan"][0]
    assert man.customers_affected == 3000
    # Total should sum to ~10000
    total = sum(i.customers_affected for i in incidents)
    assert abs(total - 10000) <= 6


@pytest.mark.asyncio
async def test_poweroutage_us_scrape_fetch():
    """PowerOutage.us scrape mode parses HTML and returns incidents."""
    html = '<p>5,678 homes and businesses are without power</p>'

    mock_resp = MagicMock()
    mock_resp.text = html
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.poweroutage_us_client.httpx.AsyncClient", return_value=mock_client), \
         patch("app.services.poweroutage_us_client.settings") as mock_settings:
        mock_settings.poweroutage_us_api_key = ""
        mock_settings.poweroutage_us_api_url = ""
        from app.services.poweroutage_us_client import fetch_incidents
        incidents = await fetch_incidents()

    assert len(incidents) == 6
    total = sum(i.customers_affected for i in incidents)
    assert abs(total - 5678) <= 6


@pytest.mark.asyncio
async def test_poweroutage_us_no_key_no_scrape_returns_empty():
    """Failed scrape returns empty list gracefully."""
    mock_resp = MagicMock()
    mock_resp.text = "<html>No outage info here</html>"
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.poweroutage_us_client.httpx.AsyncClient", return_value=mock_client), \
         patch("app.services.poweroutage_us_client.settings") as mock_settings:
        mock_settings.poweroutage_us_api_key = ""
        mock_settings.poweroutage_us_api_url = ""
        from app.services.poweroutage_us_client import fetch_incidents
        incidents = await fetch_incidents()

    assert incidents == []


# --- Multi-source ingest ---

@pytest.mark.asyncio
async def test_multi_source_ingest():
    """All 3 sources merge into a single incident list assigned to zones."""
    nyc_incidents = [
        OutageIncident(incident_id="nyc-1", source="nyc311", region="MANHATTAN"),
        OutageIncident(incident_id="nyc-2", source="nyc311", region="BROOKLYN"),
    ]
    coned_incidents = [
        OutageIncident(incident_id="ce-1", source="coned", region="Manhattan", customers_affected=100, outage_count=88),
        OutageIncident(incident_id="ce-2", source="coned", region="Bronx", customers_affected=50, outage_count=29),
    ]
    pous_incidents = [
        OutageIncident(incident_id="po-1", source="poweroutage_us", region="Manhattan", customers_affected=200),
    ]

    with patch("app.services.outage_ingest.nyc311_client.fetch_incidents", new_callable=AsyncMock, return_value=nyc_incidents), \
         patch("app.services.outage_ingest.coned_client.fetch_incidents", new_callable=AsyncMock, return_value=coned_incidents), \
         patch("app.services.outage_ingest.poweroutage_us_client.fetch_incidents", new_callable=AsyncMock, return_value=pous_incidents), \
         patch("app.services.outage_ingest._persist_snapshots"):
        from app.services.outage_ingest import ingest_outages, _outage_cache
        await ingest_outages()

    # Manhattan should have incidents from all 3 sources
    man = _outage_cache.get("CONED-MAN")
    assert man is not None
    sources = {i.source for i in man.incidents}
    assert "nyc311" in sources
    assert "coned" in sources
    assert "poweroutage_us" in sources
    assert man.customers_affected == 300  # 0 + 100 + 200
    # active_outages should sum outage_count: nyc311(1) + coned(88) + pous(1)
    assert man.active_outages == 90

    # Brooklyn should have nyc311 incident
    bkn = _outage_cache.get("CONED-BKN")
    assert bkn is not None
    assert any(i.source == "nyc311" for i in bkn.incidents)
    assert bkn.active_outages == 1  # just the one nyc311 complaint

    # Bronx should have coned incident with real outage count
    brx = _outage_cache.get("CONED-BRX")
    assert brx is not None
    assert any(i.source == "coned" for i in brx.incidents)
    assert brx.active_outages == 29  # from coned outage_count
