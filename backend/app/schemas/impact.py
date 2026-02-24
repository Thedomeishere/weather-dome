from datetime import datetime

from pydantic import BaseModel


class ForecastImpactPoint(BaseModel):
    forecast_for: datetime
    forecast_hour: int
    overall_risk_score: float = 0.0
    overall_risk_level: str = "Low"
    outage_risk_score: float = 0.0
    estimated_outages: int = 0
    vegetation_risk_score: float = 0.0
    load_pct_capacity: float = 0.0
    equipment_stress_score: float = 0.0
    melt_risk_score: float = 0.0


class OutageRisk(BaseModel):
    zone_id: str
    score: float  # 0-100
    level: str  # Low, Moderate, High, Extreme
    estimated_outages: int = 0
    contributing_factors: list[str] = []
    actual_outages: int | None = None
    outage_trend: str = "stable"


class VegetationRisk(BaseModel):
    zone_id: str
    score: float
    level: str
    foliage_factor: float = 1.0
    soil_saturation: str = "normal"


class LoadForecast(BaseModel):
    zone_id: str
    territory: str
    load_mw: float
    capacity_mw: float
    pct_capacity: float
    risk_level: str
    peak_hour: int | None = None


class EquipmentStress(BaseModel):
    zone_id: str
    score: float
    level: str
    transformer_risk: float = 0.0
    line_sag_risk: float = 0.0


class CrewRecommendation(BaseModel):
    zone_id: str
    territory: str
    line_crews: int = 0
    tree_crews: int = 0
    service_crews: int = 0
    total_crews: int = 0
    mutual_aid_needed: bool = False
    pre_stage: bool = False
    notes: list[str] = []


class ZoneImpact(BaseModel):
    zone_id: str
    zone_name: str
    territory: str
    assessed_at: datetime | None = None
    overall_risk_score: float = 0.0
    overall_risk_level: str = "Low"
    outage_risk: OutageRisk | None = None
    vegetation_risk: VegetationRisk | None = None
    load_forecast: LoadForecast | None = None
    equipment_stress: EquipmentStress | None = None
    crew_recommendation: CrewRecommendation | None = None
    melt_risk: "MeltRisk | None" = None
    summary_text: str = ""


# Deferred import to avoid circular dependency
from app.schemas.outage import MeltRisk  # noqa: E402

ZoneImpact.model_rebuild()
