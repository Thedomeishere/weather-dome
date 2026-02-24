from fastapi import APIRouter, Query

from app.schemas.impact import ZoneImpact
from app.services.impact_engine import get_cached_impact, get_territory_impacts
from app.territory.definitions import ALL_ZONES

router = APIRouter(prefix="/impact", tags=["impact"])


@router.get("/", response_model=list[ZoneImpact])
async def get_all_impacts(territory: str | None = Query(None, pattern="^(CONED|OR)$")):
    """Get impact assessments for all zones or filtered by territory."""
    if territory:
        return get_territory_impacts(territory)
    return [
        imp for z in ALL_ZONES
        if (imp := get_cached_impact(z.zone_id)) is not None
    ]


@router.get("/{zone_id}", response_model=ZoneImpact | None)
async def get_zone_impact(zone_id: str):
    return get_cached_impact(zone_id)
