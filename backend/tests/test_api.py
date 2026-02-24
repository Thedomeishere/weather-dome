import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_zones_list(client):
    resp = await client.get("/api/v1/territory/zones/")
    assert resp.status_code == 200
    zones = resp.json()
    assert len(zones) == 11
    zone_ids = {z["zone_id"] for z in zones}
    assert "CONED-MAN" in zone_ids
    assert "OR-ORA" in zone_ids


@pytest.mark.asyncio
async def test_zones_filter_coned(client):
    resp = await client.get("/api/v1/territory/zones/", params={"territory": "CONED"})
    assert resp.status_code == 200
    zones = resp.json()
    assert len(zones) == 6
    assert all(z["territory"] == "CONED" for z in zones)


@pytest.mark.asyncio
async def test_zones_filter_or(client):
    resp = await client.get("/api/v1/territory/zones/", params={"territory": "OR"})
    assert resp.status_code == 200
    zones = resp.json()
    assert len(zones) == 5
    assert all(z["territory"] == "OR" for z in zones)


@pytest.mark.asyncio
async def test_dashboard_coned(client):
    resp = await client.get("/api/v1/dashboard/", params={"territory": "CONED"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["territory"] == "CONED"
    assert "overview" in data
    assert data["overview"]["total_zones"] == 6


@pytest.mark.asyncio
async def test_dashboard_has_forecast_impacts(client):
    resp = await client.get("/api/v1/dashboard/", params={"territory": "CONED"})
    assert resp.status_code == 200
    data = resp.json()
    assert "forecast_impacts" in data
    assert isinstance(data["forecast_impacts"], dict)


@pytest.mark.asyncio
async def test_dashboard_or(client):
    resp = await client.get("/api/v1/dashboard/", params={"territory": "OR"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["territory"] == "OR"
    assert data["overview"]["total_zones"] == 5


@pytest.mark.asyncio
async def test_weather_current(client):
    resp = await client.get("/api/v1/weather/current/")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_weather_alerts(client):
    resp = await client.get("/api/v1/weather/alerts/")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_impact_list(client):
    resp = await client.get("/api/v1/impact/")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_geojson_coned(client):
    resp = await client.get("/api/v1/territory/geojson/CONED")
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) == 6


@pytest.mark.asyncio
async def test_geojson_or(client):
    resp = await client.get("/api/v1/territory/geojson/OR")
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) == 5


@pytest.mark.asyncio
async def test_dashboard_has_outage_status(client):
    resp = await client.get("/api/v1/dashboard/", params={"territory": "CONED"})
    assert resp.status_code == 200
    data = resp.json()
    assert "outage_status" in data
    assert isinstance(data["outage_status"], list)


@pytest.mark.asyncio
async def test_dashboard_has_melt_risk_fields(client):
    resp = await client.get("/api/v1/dashboard/", params={"territory": "CONED"})
    assert resp.status_code == 200
    data = resp.json()
    assert "total_actual_outages" in data["overview"]
    assert "max_melt_risk_score" in data["overview"]
    assert "max_melt_risk_level" in data["overview"]


@pytest.mark.asyncio
async def test_dashboard_zones_have_melt_risk(client):
    resp = await client.get("/api/v1/dashboard/", params={"territory": "CONED"})
    assert resp.status_code == 200
    data = resp.json()
    for zone in data.get("zones", []):
        assert "melt_risk" in zone


@pytest.mark.asyncio
async def test_outages_endpoint(client):
    resp = await client.get("/api/v1/outages/")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_outages_territory_filter(client):
    resp = await client.get("/api/v1/outages/", params={"territory": "CONED"})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
