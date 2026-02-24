import { useState } from "react";
import { useDashboard } from "./hooks/useWeatherData";
import TerritoryMap from "./components/map/TerritoryMap";
import WeatherPanel from "./components/weather/WeatherPanel";
import AlertBanner from "./components/weather/AlertBanner";
import ForecastTimeline from "./components/weather/ForecastTimeline";
import OutageRiskCard from "./components/impact/OutageRiskCard";
import VegetationRiskCard from "./components/impact/VegetationRiskCard";
import LoadForecastCard from "./components/impact/LoadForecastCard";
import EquipmentStressCard from "./components/impact/EquipmentStressCard";
import ImpactForecastPanel from "./components/impact/ImpactForecastPanel";
import CrewRecommendationPanel from "./components/crew/CrewRecommendationPanel";

function App() {
  const [territory, setTerritory] = useState<"CONED" | "OR">("CONED");
  const { data, isLoading, error } = useDashboard(territory);

  return (
    <div className="min-h-screen bg-gray-100">
      {/* Header */}
      <header className="bg-gray-900 text-white px-6 py-4 shadow-lg">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">Weather-Dome</h1>
            <p className="text-gray-400 text-sm">
              Weather Impact Prediction Dashboard
            </p>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex bg-gray-800 rounded-lg p-1">
              <button
                onClick={() => setTerritory("CONED")}
                className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                  territory === "CONED"
                    ? "bg-blue-600 text-white"
                    : "text-gray-400 hover:text-white"
                }`}
              >
                Con Edison
              </button>
              <button
                onClick={() => setTerritory("OR")}
                className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                  territory === "OR"
                    ? "bg-blue-600 text-white"
                    : "text-gray-400 hover:text-white"
                }`}
              >
                O&R
              </button>
            </div>
            {data && (
              <div className="text-sm text-gray-400">
                Updated: {new Date(data.as_of).toLocaleTimeString()}
              </div>
            )}
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-6">
        {/* Loading / Error states */}
        {isLoading && (
          <div className="text-center py-20 text-gray-500">
            Loading dashboard data...
          </div>
        )}
        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 p-4 rounded-lg mb-6">
            Failed to load dashboard. The backend may not be running.
          </div>
        )}

        {data && (
          <>
            {/* Alerts */}
            {data.alerts.length > 0 && (
              <AlertBanner alerts={data.alerts} />
            )}

            {/* Overview Cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
              <OverviewCard
                label="Overall Risk"
                value={data.overview.overall_risk_level}
                color={riskColor(data.overview.overall_risk_level)}
              />
              <OverviewCard
                label="Active Alerts"
                value={data.overview.active_alert_count.toString()}
                color={data.overview.active_alert_count > 0 ? "text-orange-600" : "text-green-600"}
              />
              <OverviewCard
                label="Est. Outages"
                value={data.overview.total_estimated_outages.toLocaleString()}
                color={data.overview.total_estimated_outages > 100 ? "text-red-600" : "text-green-600"}
              />
              <OverviewCard
                label="Peak Load"
                value={`${data.overview.peak_load_pct}%`}
                color={data.overview.peak_load_pct > 85 ? "text-red-600" : "text-green-600"}
              />
            </div>

            {/* Map + Weather Panel */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
              <div className="lg:col-span-2">
                <TerritoryMap zones={data.zones} territory={territory} />
              </div>
              <div>
                <WeatherPanel weather={data.current_weather} />
              </div>
            </div>

            {/* Impact Cards */}
            <h2 className="text-lg font-semibold text-gray-800 mb-3">
              Impact Assessment
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
              <OutageRiskCard zones={data.zones} />
              <VegetationRiskCard zones={data.zones} />
              <LoadForecastCard zones={data.zones} />
              <EquipmentStressCard zones={data.zones} />
            </div>

            {/* Impact Forecast */}
            {Object.keys(data.forecast_impacts).length > 0 && (
              <div className="mb-6">
                <ImpactForecastPanel forecastImpacts={data.forecast_impacts} />
              </div>
            )}

            {/* Forecast Timeline */}
            <div className="mb-6">
              <ForecastTimeline
                points={data.forecast_timeline}
                forecastImpacts={data.forecast_impacts}
              />
            </div>

            {/* Crew Deployment */}
            <CrewRecommendationPanel crews={data.crew_summary} />
          </>
        )}
      </main>
    </div>
  );
}

function OverviewCard({
  label,
  value,
  color,
}: {
  label: string;
  value: string;
  color: string;
}) {
  return (
    <div className="bg-white rounded-lg shadow p-4">
      <div className="text-sm text-gray-500">{label}</div>
      <div className={`text-2xl font-bold ${color}`}>{value}</div>
    </div>
  );
}

function riskColor(level: string): string {
  switch (level) {
    case "Low":
      return "text-green-600";
    case "Moderate":
      return "text-yellow-600";
    case "High":
      return "text-orange-600";
    case "Extreme":
      return "text-red-600";
    default:
      return "text-gray-600";
  }
}

export default App;
