import { useState } from "react";
import { useDashboard } from "./hooks/useWeatherData";
import TerritoryMap from "./components/map/TerritoryMap";
import WeatherPanel from "./components/weather/WeatherPanel";
import AlertBanner from "./components/weather/AlertBanner";
import ForecastTimeline from "./components/weather/ForecastTimeline";
import FiveDayForecast from "./components/weather/FiveDayForecast";
import OutageRiskCard from "./components/impact/OutageRiskCard";
import VegetationRiskCard from "./components/impact/VegetationRiskCard";
import LoadForecastCard from "./components/impact/LoadForecastCard";
import EquipmentStressCard from "./components/impact/EquipmentStressCard";
import MeltRiskCard from "./components/impact/MeltRiskCard";
import RealTimeOutageCard from "./components/impact/RealTimeOutageCard";
import ImpactForecastPanel from "./components/impact/ImpactForecastPanel";
import JobCountForecastPanel from "./components/impact/JobCountForecastPanel";
import OutageOverridePanel from "./components/admin/OutageOverridePanel";

function App() {
  const [territory, setTerritory] = useState<"CONED" | "OR">("CONED");
  const [showAdmin, setShowAdmin] = useState(false);
  const { data, isLoading, error } = useDashboard(territory);

  return (
    <div className="min-h-screen bg-slate-950 text-gray-100">
      {/* Header */}
      <header className="bg-slate-900/80 backdrop-blur-sm text-white px-6 py-4 shadow-lg border-b border-slate-800">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">Weather-Dome</h1>
            <p className="text-slate-400 text-sm">
              Weather Impact Prediction Dashboard
            </p>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex bg-slate-800 rounded-lg p-1">
              <button
                onClick={() => setTerritory("CONED")}
                className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                  territory === "CONED"
                    ? "bg-blue-600 text-white shadow-lg shadow-blue-600/30"
                    : "text-slate-400 hover:text-white"
                }`}
              >
                Con Edison
              </button>
              <button
                onClick={() => setTerritory("OR")}
                className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                  territory === "OR"
                    ? "bg-blue-600 text-white shadow-lg shadow-blue-600/30"
                    : "text-slate-400 hover:text-white"
                }`}
              >
                O&R
              </button>
            </div>
            <button
              onClick={() => setShowAdmin((v) => !v)}
              className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                showAdmin
                  ? "bg-amber-600 text-white shadow-lg shadow-amber-600/30"
                  : "bg-slate-800 text-slate-400 hover:text-white"
              }`}
            >
              Admin
            </button>
            {data && (
              <div className="text-sm text-slate-400">
                Updated: {new Date(data.as_of).toLocaleTimeString()}
              </div>
            )}
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-6">
        {/* Loading / Error states */}
        {isLoading && (
          <div className="text-center py-20 text-slate-500">
            Loading dashboard data...
          </div>
        )}
        {error && (
          <div className="bg-red-950/50 border border-red-800/50 text-red-400 p-4 rounded-lg mb-6">
            Failed to load dashboard. The backend may not be running.
          </div>
        )}

        {data && (
          <>
            {/* Alerts */}
            {data.alerts.length > 0 && (
              <AlertBanner alerts={data.alerts} />
            )}

            {/* Admin Panel */}
            {showAdmin && (
              <OutageOverridePanel
                outageStatus={data.outage_status}
                territory={territory}
              />
            )}

            {/* Overview Cards */}
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
              <OverviewCard
                label="Overall Risk"
                value={data.overview.overall_risk_level}
                color={riskColor(data.overview.overall_risk_level)}
                index={0}
              />
              <OverviewCard
                label="Active Alerts"
                value={data.overview.active_alert_count.toString()}
                color={data.overview.active_alert_count > 0 ? "text-orange-400" : "text-emerald-400"}
                index={1}
              />
              <OverviewCard
                label="Est. Outages"
                value={data.overview.total_estimated_outages.toLocaleString()}
                color={data.overview.total_estimated_outages > 100 ? "text-red-400" : "text-emerald-400"}
                index={2}
              />
              <OverviewCard
                label="Active Outages"
                value={data.overview.total_actual_outages.toLocaleString()}
                color={data.overview.total_actual_outages > 0 ? "text-red-400" : "text-emerald-400"}
                index={3}
              />
              <OverviewCard
                label="Peak Load"
                value={`${data.overview.peak_load_pct}%`}
                color={data.overview.peak_load_pct > 85 ? "text-red-400" : "text-emerald-400"}
                index={4}
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

            {/* 5-Day Forecast */}
            <FiveDayForecast points={data.forecast_timeline} />

            {/* Impact Cards */}
            <h2 className="text-lg font-semibold text-slate-200 mb-3">
              Impact Assessment
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-4 mb-6">
              {[
                <OutageRiskCard key="outage" zones={data.zones} />,
                <VegetationRiskCard key="veg" zones={data.zones} />,
                <LoadForecastCard key="load" zones={data.zones} />,
                <EquipmentStressCard key="equip" zones={data.zones} />,
                <MeltRiskCard key="melt" zones={data.zones} />,
              ].map((card, i) => (
                <div
                  key={i}
                  className="animate-fade-in-up"
                  style={{ animationDelay: `${i * 60}ms` }}
                >
                  {card}
                </div>
              ))}
            </div>

            {/* Real-Time Outage Card */}
            {data.outage_status.length > 0 && (
              <div className="mb-6">
                <RealTimeOutageCard outageStatus={data.outage_status} />
              </div>
            )}

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

            {/* Job Count Forecast */}
            <JobCountForecastPanel
              jobForecast={data.job_forecast}
              forecastImpacts={data.forecast_impacts}
            />
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
  index,
}: {
  label: string;
  value: string;
  color: string;
  index: number;
}) {
  return (
    <div
      className="bg-slate-800/80 border border-slate-700/50 rounded-lg shadow-lg shadow-black/20 p-4 hover:border-slate-600 transition-colors animate-fade-in-up"
      style={{ animationDelay: `${index * 60}ms` }}
    >
      <div className="text-sm text-slate-400">{label}</div>
      <div className={`text-2xl font-bold ${color}`}>{value}</div>
    </div>
  );
}

function riskColor(level: string): string {
  switch (level) {
    case "Low":
      return "text-emerald-400";
    case "Moderate":
      return "text-yellow-400";
    case "High":
      return "text-orange-400";
    case "Extreme":
      return "text-red-400";
    default:
      return "text-slate-400";
  }
}

export default App;
