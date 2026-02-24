from datetime import datetime

from pydantic import BaseModel

from app.schemas.weather import AlertSchema, WeatherConditions, ForecastPoint
from app.schemas.impact import ForecastImpactPoint, ZoneImpact, CrewRecommendation
from app.schemas.outage import ZoneOutageStatus


class TerritoryOverview(BaseModel):
    territory: str  # CONED or OR
    overall_risk_level: str = "Low"
    overall_risk_score: float = 0.0
    active_alert_count: int = 0
    zones_at_risk: int = 0
    total_zones: int = 0
    peak_load_pct: float = 0.0
    total_estimated_outages: int = 0
    total_actual_outages: int = 0
    max_melt_risk_score: float = 0.0
    max_melt_risk_level: str = "Low"


class DashboardResponse(BaseModel):
    territory: str
    as_of: datetime
    poll_interval_seconds: int = 60
    overview: TerritoryOverview
    zones: list[ZoneImpact] = []
    current_weather: list[WeatherConditions] = []
    alerts: list[AlertSchema] = []
    forecast_timeline: list[ForecastPoint] = []
    forecast_impacts: dict[str, list[ForecastImpactPoint]] = {}
    crew_summary: list[CrewRecommendation] = []
    outage_status: list[ZoneOutageStatus] = []
