"""Outage data ingestion: fetches from ODS, assigns to zones, caches and persists."""

import json
import logging
import math
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.outage import OutageSnapshot
from app.schemas.outage import OutageIncident, ZoneOutageStatus
from app.services import ods_client
from app.territory.definitions import ALL_ZONES, ZoneDefinition, get_zones_for_territory

logger = logging.getLogger(__name__)

# In-memory cache for latest outage status per zone
_outage_cache: dict[str, ZoneOutageStatus] = {}

# County/region name aliases → zone_id mapping
_REGION_ALIASES: dict[str, str] = {
    # Manhattan aliases
    "new york": "CONED-MAN",
    "manhattan": "CONED-MAN",
    "new york county": "CONED-MAN",
    # Bronx
    "bronx": "CONED-BRX",
    "bronx county": "CONED-BRX",
    # Brooklyn / Kings
    "brooklyn": "CONED-BKN",
    "kings": "CONED-BKN",
    "kings county": "CONED-BKN",
    # Queens
    "queens": "CONED-QNS",
    "queens county": "CONED-QNS",
    # Staten Island / Richmond
    "staten island": "CONED-SI",
    "richmond": "CONED-SI",
    "richmond county": "CONED-SI",
    # Westchester
    "westchester": "CONED-WST",
    "westchester county": "CONED-WST",
    # Orange & Rockland zones
    "orange": "OR-ORA",
    "orange county": "OR-ORA",
    "rockland": "OR-ROC",
    "rockland county": "OR-ROC",
    "sullivan": "OR-SUL",
    "sullivan county": "OR-SUL",
    "bergen": "OR-BER",
    "passaic": "OR-BER",
    "sussex": "OR-SSX",
    "sussex county": "OR-SSX",
}


def _assign_zone(incident: OutageIncident) -> str | None:
    """Assign an incident to a zone via region name or lat/lon fallback."""
    # Try region name matching first
    if incident.region:
        region_lower = incident.region.lower().strip()
        # Check direct match
        if region_lower in _REGION_ALIASES:
            return _REGION_ALIASES[region_lower]
        # Check the comma-separated parts of the region string for exact matches
        # e.g. "Queens, New York" → check "queens" then "new york"
        parts = [p.strip() for p in region_lower.split(",")]
        for part in parts:
            if part in _REGION_ALIASES:
                return _REGION_ALIASES[part]
        # Fallback: substring matching (longest alias first to avoid false positives)
        sorted_aliases = sorted(_REGION_ALIASES.keys(), key=len, reverse=True)
        for alias in sorted_aliases:
            if alias in region_lower:
                return _REGION_ALIASES[alias]

    # Fallback: Haversine nearest zone within 50km
    if incident.latitude is not None and incident.longitude is not None:
        return _nearest_zone(incident.latitude, incident.longitude, max_km=50)

    return None


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance in kilometers."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _nearest_zone(lat: float, lon: float, max_km: float = 50) -> str | None:
    """Find nearest zone by Haversine distance."""
    best: str | None = None
    best_dist = max_km
    for zone in ALL_ZONES:
        d = _haversine_km(lat, lon, zone.latitude, zone.longitude)
        if d < best_dist:
            best = zone.zone_id
            best_dist = d
    return best


async def ingest_outages():
    """Main ingest: fetch ODS → assign to zones → compute trend → cache + persist."""
    logger.info("Starting outage ingest")
    now = datetime.now(timezone.utc)

    incidents = await ods_client.fetch_incidents()

    # Group incidents by zone
    zone_incidents: dict[str, list[OutageIncident]] = {z.zone_id: [] for z in ALL_ZONES}
    unassigned = 0

    for inc in incidents:
        zone_id = _assign_zone(inc)
        if zone_id and zone_id in zone_incidents:
            zone_incidents[zone_id].append(inc)
        else:
            unassigned += 1

    if unassigned:
        logger.debug("Outage ingest: %d incidents unassigned to zones", unassigned)

    # Build status per zone and compute trend
    for zone in ALL_ZONES:
        zid = zone.zone_id
        zone_incs = zone_incidents[zid]
        active = len(zone_incs)
        customers = sum(i.customers_affected for i in zone_incs)

        # Compute trend vs previous cached value
        prev = _outage_cache.get(zid)
        if prev is None:
            trend = "stable"
        elif active > prev.active_outages:
            trend = "rising"
        elif active < prev.active_outages:
            trend = "falling"
        else:
            trend = "stable"

        status = ZoneOutageStatus(
            zone_id=zid,
            as_of=now,
            active_outages=active,
            customers_affected=customers,
            trend=trend,
            incidents=zone_incs,
        )
        _outage_cache[zid] = status

    # Persist snapshots
    _persist_snapshots(now, zone_incidents)
    logger.info("Outage ingest complete: %d incidents across %d zones",
                len(incidents), sum(1 for v in zone_incidents.values() if v))


def _persist_snapshots(snapshot_at: datetime, zone_incidents: dict[str, list[OutageIncident]]):
    """Persist one OutageSnapshot row per zone."""
    db: Session = SessionLocal()
    try:
        for zone_id, incs in zone_incidents.items():
            snapshot = OutageSnapshot(
                zone_id=zone_id,
                source="ods",
                snapshot_at=snapshot_at,
                outage_count=len(incs),
                customers_affected=sum(i.customers_affected for i in incs),
                active_incidents=len(incs),
                raw_json=json.dumps([i.model_dump(mode="json") for i in incs]) if incs else None,
            )
            db.add(snapshot)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("Failed to persist outage snapshots: %s", e)
    finally:
        db.close()


def get_cached_outages(zone_id: str) -> ZoneOutageStatus | None:
    return _outage_cache.get(zone_id)


def get_all_cached_outages() -> list[ZoneOutageStatus]:
    return list(_outage_cache.values())


def get_territory_outages(territory: str) -> list[ZoneOutageStatus]:
    zones = get_zones_for_territory(territory)
    return [_outage_cache[z.zone_id] for z in zones if z.zone_id in _outage_cache]
