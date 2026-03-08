from fastapi import APIRouter, HTTPException, Query

from app.schemas.outage import OutageOverrideRequest, OutageOverrideResponse, ZoneOutageStatus
from app.services.outage_ingest import (
    clear_outage_override,
    get_active_overrides,
    get_all_cached_outages,
    get_cached_outages,
    get_territory_outages,
    set_outage_override,
)
from app.territory.definitions import get_zone

router = APIRouter(tags=["outages"])


@router.get("/outages/overrides", response_model=list[OutageOverrideResponse])
async def list_overrides():
    """List all active manual outage overrides."""
    return get_active_overrides()


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


@router.post("/outages/override", response_model=OutageOverrideResponse)
async def create_override(req: OutageOverrideRequest):
    """Set a manual outage override for a zone."""
    zone = get_zone(req.zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail=f"Zone {req.zone_id} not found")

    expires_at = set_outage_override(
        zone_id=req.zone_id,
        active_outages=req.active_outages,
        customers_affected=req.customers_affected,
        ttl_minutes=req.ttl_minutes,
    )
    return OutageOverrideResponse(
        zone_id=req.zone_id,
        active_outages=req.active_outages,
        customers_affected=req.customers_affected,
        expires_at=expires_at,
    )


@router.delete("/outages/override/{zone_id}")
async def delete_override(zone_id: str):
    """Clear a manual outage override for a zone."""
    zone = get_zone(zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail=f"Zone {zone_id} not found")

    removed = clear_outage_override(zone_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"No active override for {zone_id}")
    return {"status": "cleared", "zone_id": zone_id}
