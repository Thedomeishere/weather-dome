import json
from pathlib import Path

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from app.territory.definitions import ALL_ZONES, get_zones_for_territory, ZoneDefinition

router = APIRouter(prefix="/territory", tags=["territory"])

DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"


@router.get("/zones/")
async def list_zones(territory: str | None = Query(None, pattern="^(CONED|OR)$")):
    """List all zones with basic info."""
    zones = get_zones_for_territory(territory) if territory else ALL_ZONES
    return [
        {
            "zone_id": z.zone_id,
            "name": z.name,
            "territory": z.territory,
            "county": z.county,
            "latitude": z.latitude,
            "longitude": z.longitude,
            "nws_zone": z.nws_zone,
        }
        for z in zones
    ]


@router.get("/geojson/{territory}")
async def get_territory_geojson(territory: str):
    """Return GeoJSON for a territory's boundaries."""
    territory = territory.upper()
    filename = "coned_territory.geojson" if territory == "CONED" else "or_territory.geojson"
    filepath = DATA_DIR / filename
    if filepath.exists():
        data = json.loads(filepath.read_text())
        return JSONResponse(content=data)
    return JSONResponse(
        content={"type": "FeatureCollection", "features": []},
        status_code=200,
    )
