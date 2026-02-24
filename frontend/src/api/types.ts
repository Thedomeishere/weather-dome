export interface WeatherConditions {
  zone_id: string;
  source: string;
  observed_at: string | null;
  temperature_f: number | null;
  feels_like_f: number | null;
  humidity_pct: number | null;
  wind_speed_mph: number | null;
  wind_gust_mph: number | null;
  wind_direction_deg: number | null;
  precip_rate_in_hr: number | null;
  precip_probability_pct: number | null;
  snow_rate_in_hr: number | null;
  ice_accum_in: number | null;
  visibility_mi: number | null;
  cloud_cover_pct: number | null;
  pressure_mb: number | null;
  lightning_probability_pct: number | null;
  condition_text: string | null;
}

export interface ForecastPoint {
  forecast_for: string;
  temperature_f: number | null;
  feels_like_f: number | null;
  humidity_pct: number | null;
  wind_speed_mph: number | null;
  wind_gust_mph: number | null;
  precip_probability_pct: number | null;
  precip_amount_in: number | null;
  snow_amount_in: number | null;
  ice_accum_in: number | null;
  lightning_probability_pct: number | null;
  condition_text: string | null;
}

export interface AlertSchema {
  alert_id: string;
  zone_id: string;
  event: string;
  severity: string;
  urgency: string | null;
  certainty: string | null;
  headline: string | null;
  description: string | null;
  instruction: string | null;
  onset: string | null;
  expires: string | null;
  source: string;
}

export interface OutageRisk {
  zone_id: string;
  score: number;
  level: string;
  estimated_outages: number;
  contributing_factors: string[];
}

export interface VegetationRisk {
  zone_id: string;
  score: number;
  level: string;
  foliage_factor: number;
  soil_saturation: string;
}

export interface LoadForecast {
  zone_id: string;
  territory: string;
  load_mw: number;
  capacity_mw: number;
  pct_capacity: number;
  risk_level: string;
  peak_hour: number | null;
}

export interface EquipmentStress {
  zone_id: string;
  score: number;
  level: string;
  transformer_risk: number;
  line_sag_risk: number;
}

export interface CrewRecommendation {
  zone_id: string;
  territory: string;
  line_crews: number;
  tree_crews: number;
  service_crews: number;
  total_crews: number;
  mutual_aid_needed: boolean;
  pre_stage: boolean;
  notes: string[];
}

export interface ZoneImpact {
  zone_id: string;
  zone_name: string;
  territory: string;
  assessed_at: string | null;
  overall_risk_score: number;
  overall_risk_level: string;
  outage_risk: OutageRisk | null;
  vegetation_risk: VegetationRisk | null;
  load_forecast: LoadForecast | null;
  equipment_stress: EquipmentStress | null;
  crew_recommendation: CrewRecommendation | null;
  summary_text: string;
}

export interface ForecastImpactPoint {
  forecast_for: string;
  forecast_hour: number;
  overall_risk_score: number;
  overall_risk_level: string;
  outage_risk_score: number;
  estimated_outages: number;
  vegetation_risk_score: number;
  load_pct_capacity: number;
  equipment_stress_score: number;
}

export interface TerritoryOverview {
  territory: string;
  overall_risk_level: string;
  overall_risk_score: number;
  active_alert_count: number;
  zones_at_risk: number;
  total_zones: number;
  peak_load_pct: number;
  total_estimated_outages: number;
}

export interface DashboardResponse {
  territory: string;
  as_of: string;
  poll_interval_seconds: number;
  overview: TerritoryOverview;
  zones: ZoneImpact[];
  current_weather: WeatherConditions[];
  alerts: AlertSchema[];
  forecast_timeline: ForecastPoint[];
  forecast_impacts: Record<string, ForecastImpactPoint[]>;
  crew_summary: CrewRecommendation[];
}

export interface ZoneInfo {
  zone_id: string;
  name: string;
  territory: string;
  county: string;
  latitude: number;
  longitude: number;
  nws_zone: string;
}
