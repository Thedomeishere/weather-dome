"""ConEd per-borough outage scraper wrapper.

Runs the Puppeteer scraper script and returns per-borough OutageIncident list.
Caches results for 5 minutes to avoid repeated scrapes.
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from app.schemas.outage import OutageIncident

logger = logging.getLogger(__name__)

SCRAPER_SCRIPT = str(Path(__file__).resolve().parents[3] / "scripts" / "scrape_coned_outages.mjs")
CACHE_TTL_SECONDS = 300  # 5 minutes
NODE_PATH = "/usr/lib/node_modules"

# In-memory cache: (timestamp, results)
_scraper_cache: tuple[float, list[OutageIncident]] | None = None

# Map borough display names to zone IDs (self-contained to avoid circular import)
_BOROUGH_NAME_TO_ZONE: dict[str, str] = {
    "manhattan": "CONED-MAN",
    "bronx": "CONED-BRX",
    "the bronx": "CONED-BRX",
    "brooklyn": "CONED-BKN",
    "queens": "CONED-QNS",
    "staten island": "CONED-SI",
    "westchester": "CONED-WST",
}


def _map_area_to_zone(area_name: str) -> str | None:
    """Map a ConEd area name to a zone ID."""
    lower = area_name.lower().strip()
    return _BOROUGH_NAME_TO_ZONE.get(lower)


async def fetch_borough_outages() -> list[OutageIncident]:
    """Run Puppeteer scraper and return per-borough OutageIncident list.

    Returns cached results if within TTL. Falls back to empty list on any error.
    """
    global _scraper_cache

    # Check cache
    if _scraper_cache is not None:
        cached_at, cached_results = _scraper_cache
        if time.monotonic() - cached_at < CACHE_TTL_SECONDS:
            logger.debug("ConEd scraper: returning cached results (%d items)", len(cached_results))
            return cached_results

    try:
        proc = await asyncio.create_subprocess_exec(
            "node", SCRAPER_SCRIPT,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={"NODE_PATH": NODE_PATH, "PATH": "/usr/bin:/usr/local/bin"},
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)

        if proc.returncode != 0:
            logger.warning("ConEd scraper exited with code %d: %s", proc.returncode, stderr.decode().strip())
            return []

        raw = json.loads(stdout.decode())
        now = datetime.now(timezone.utc)
        incidents: list[OutageIncident] = []

        for entry in raw:
            area_name = entry.get("area", "")
            zone_id = _map_area_to_zone(area_name)
            if not zone_id:
                logger.debug("ConEd scraper: unmapped area '%s'", area_name)
                continue

            outages = int(entry.get("outages", 0))
            customers = int(entry.get("customers", 0))

            incidents.append(OutageIncident(
                incident_id=f"coned-scrape-{zone_id}-{int(now.timestamp())}",
                source="coned",
                status="ongoing" if outages > 0 else "none",
                started_at=now,
                region=area_name,
                customers_affected=customers,
                outage_count=outages,
            ))

        _scraper_cache = (time.monotonic(), incidents)
        logger.info("ConEd scraper: fetched %d borough entries", len(incidents))
        return incidents

    except asyncio.TimeoutError:
        logger.warning("ConEd scraper timed out after 30s")
        return []
    except Exception as e:
        logger.warning("ConEd scraper failed: %s", e)
        return []
