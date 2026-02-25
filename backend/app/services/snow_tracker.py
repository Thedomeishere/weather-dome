"""Dynamic snow depth tracker.

Maintains a per-zone snow depth estimate that persists across restarts
and auto-decays based on actual temperature data each computation cycle.

Usage:
- Set initial depth: set_snow_depth("CONED-MAN", 20.0)  or set_all(20.0)
- Each impact cycle calls update_snow_depth(zone_id, temp_f, hours_elapsed)
  which applies temperature-based melt with urban acceleration
- get_snow_depth(zone_id) returns current tracked depth

State persists in a JSON file so it survives restarts.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# State file location (next to the SQLite DB)
_STATE_FILE = Path(__file__).parent.parent.parent / "snow_state.json"

# Urban melt multipliers (same as impact_engine)
_URBAN_MELT_MULT: dict[str, float] = {
    "CONED-MAN": 3.5, "CONED-BKN": 3.0, "CONED-QNS": 3.0,
    "CONED-BRX": 2.5, "CONED-SI": 2.0, "CONED-WST": 2.0,
    "OR-ORA": 1.5, "OR-ROC": 1.5, "OR-SUL": 1.2,
    "OR-BER": 1.5, "OR-SSX": 1.2,
}

# Per-zone effective melt threshold (imported at runtime to avoid circular)
_MELT_THRESHOLDS: dict[str, float] = {
    "CONED-MAN": 25.0, "CONED-BKN": 27.0, "CONED-QNS": 27.0,
    "CONED-BRX": 27.0, "CONED-SI": 29.0, "CONED-WST": 28.0,
    "OR-ORA": 31.0, "OR-ROC": 30.0, "OR-SUL": 31.0,
    "OR-BER": 30.0, "OR-SSX": 31.0,
}

# In-memory cache
_state: dict = {}


def _load_state() -> dict:
    """Load state from disk."""
    global _state
    if _state:
        return _state
    try:
        if _STATE_FILE.exists():
            _state = json.loads(_STATE_FILE.read_text())
            return _state
    except Exception as e:
        logger.warning("Failed to load snow state: %s", e)
    _state = {"zones": {}, "updated_at": None}
    return _state


def _save_state():
    """Persist state to disk."""
    try:
        _state["updated_at"] = datetime.now(timezone.utc).isoformat()
        _STATE_FILE.write_text(json.dumps(_state, indent=2))
    except Exception as e:
        logger.warning("Failed to save snow state: %s", e)


def get_snow_depth(zone_id: str) -> float | None:
    """Get tracked snow depth for a zone. Returns None if not tracked."""
    state = _load_state()
    zone_data = state.get("zones", {}).get(zone_id)
    if zone_data is None:
        return None
    return zone_data.get("depth_in", 0.0)


def get_all_depths() -> dict[str, float]:
    """Get all tracked snow depths."""
    state = _load_state()
    return {
        zid: zd.get("depth_in", 0.0)
        for zid, zd in state.get("zones", {}).items()
    }


def set_snow_depth(zone_id: str, depth_in: float):
    """Manually set snow depth for a zone."""
    state = _load_state()
    if "zones" not in state:
        state["zones"] = {}
    state["zones"][zone_id] = {
        "depth_in": round(depth_in, 1),
        "set_at": datetime.now(timezone.utc).isoformat(),
        "last_update": datetime.now(timezone.utc).isoformat(),
    }
    _save_state()
    logger.info("Snow depth set: %s = %.1f in", zone_id, depth_in)


def set_all_zones(depth_in: float):
    """Set the same snow depth for all zones."""
    from app.territory.definitions import ALL_ZONES
    for zone in ALL_ZONES:
        set_snow_depth(zone.zone_id, depth_in)


def update_snow_depth(zone_id: str, temp_f: float, hours_elapsed: float) -> float:
    """Apply temperature-based melt decay to tracked snow depth.

    Called each impact computation cycle (~30 min).
    Returns the updated depth.
    """
    state = _load_state()
    zone_data = state.get("zones", {}).get(zone_id)
    if zone_data is None:
        return 0.0

    depth = zone_data.get("depth_in", 0.0)
    if depth <= 0:
        return 0.0

    threshold = _MELT_THRESHOLDS.get(zone_id, 32.0)
    urban_mult = _URBAN_MELT_MULT.get(zone_id, 1.5)

    if temp_f > threshold and hours_elapsed > 0:
        # Base melt: 0.005 in/°F/hr × urban multiplier
        melt_rate = (temp_f - threshold) * 0.005 * urban_mult
        melted = melt_rate * hours_elapsed
        depth = max(0.0, depth - melted)

    # Also add new snowfall if below freezing and snowing
    # (handled by caller if needed)

    zone_data["depth_in"] = round(depth, 1)
    zone_data["last_update"] = datetime.now(timezone.utc).isoformat()
    _save_state()

    return depth


def add_snowfall(zone_id: str, inches: float):
    """Add new snowfall to tracked depth."""
    state = _load_state()
    zone_data = state.get("zones", {}).get(zone_id)
    if zone_data is None:
        set_snow_depth(zone_id, inches)
        return
    zone_data["depth_in"] = round(zone_data.get("depth_in", 0.0) + inches, 1)
    zone_data["last_update"] = datetime.now(timezone.utc).isoformat()
    _save_state()
