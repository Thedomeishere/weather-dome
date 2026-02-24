from fastapi import APIRouter, HTTPException, Query

from app.schemas.outage import ZoneOutageStatus
from app.services.outage_ingest import get_cached_outages, get_all_cached_outages, get_territory_outages
from app.territory.definitions import get_zone

router = APIRouter(tags=["outages"])


@router.get("/outages/", response_model=list[ZoneOutageStatus])
async def list_outages(territory: str | None = Query(None, pattern="^(CONED|OR)$")):
    """Get outage status for all zones, optionally filtered by territory."""
    if territory:
        return get_territory_outages(territory)
    return get_all_cached_outages()


@router.get("/outages/{zone_id}", response_model=ZoneOutageStatus)
async def get_zone_outages(zone_id: str):
    """Get outage status for a single zone."""
    zone = get_zone(zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail=f"Zone {zone_id} not found")

    status = get_cached_outages(zone_id)
    if status is None:
        return ZoneOutageStatus(zone_id=zone_id)
    return status
