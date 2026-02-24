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
