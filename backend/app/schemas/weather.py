from datetime import datetime

from pydantic import BaseModel


class WeatherConditions(BaseModel):
    zone_id: str
    source: str = "aggregated"
    observed_at: datetime | None = None
    temperature_f: float | None = None
    feels_like_f: float | None = None
    humidity_pct: float | None = None
    wind_speed_mph: float | None = None
    wind_gust_mph: float | None = None
    wind_direction_deg: float | None = None
    precip_rate_in_hr: float | None = None
    precip_probability_pct: float | None = None
    snow_rate_in_hr: float | None = None
    snow_depth_in: float | None = None
    ice_accum_in: float | None = None
    visibility_mi: float | None = None
    cloud_cover_pct: float | None = None
    pressure_mb: float | None = None
    lightning_probability_pct: float | None = None
    condition_text: str | None = None


class ForecastPoint(BaseModel):
    forecast_for: datetime
    temperature_f: float | None = None
    feels_like_f: float | None = None
    humidity_pct: float | None = None
    wind_speed_mph: float | None = None
    wind_gust_mph: float | None = None
    precip_probability_pct: float | None = None
    precip_amount_in: float | None = None
    snow_amount_in: float | None = None
    snow_depth_in: float | None = None
    ice_accum_in: float | None = None
    lightning_probability_pct: float | None = None
    condition_text: str | None = None


class ZoneForecast(BaseModel):
    zone_id: str
    source: str = "aggregated"
    fetched_at: datetime | None = None
    points: list[ForecastPoint] = []


class AlertSchema(BaseModel):
    alert_id: str
    zone_id: str
    event: str
    severity: str
    urgency: str | None = None
    certainty: str | None = None
    headline: str | None = None
    description: str | None = None
    instruction: str | None = None
    onset: datetime | None = None
    expires: datetime | None = None
    source: str = "nws"
    url: str | None = None

    model_config = {"from_attributes": True}
