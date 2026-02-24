from datetime import datetime

from pydantic import BaseModel


class OutageIncident(BaseModel):
    incident_id: str
    source: str = "nyc311"
    status: str = "ongoing"
    started_at: datetime | None = None
    region: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    customers_affected: int = 0
    cause: str | None = None


class ZoneOutageStatus(BaseModel):
    zone_id: str
    as_of: datetime | None = None
    active_outages: int = 0
    customers_affected: int = 0
    trend: str = "stable"  # rising, falling, stable
    incidents: list[OutageIncident] = []


class MeltRisk(BaseModel):
    zone_id: str
    score: float = 0.0  # 0-100
    level: str = "Low"
    temperature_trend_f_per_hr: float = 0.0
    melt_potential: float = 0.0
    rain_on_snow_risk: float = 0.0
    freeze_thaw_cycles_48h: int = 0
    contributing_factors: list[str] = []
