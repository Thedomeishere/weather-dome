import type { WeatherConditions } from "../../api/types";

interface Props {
  weather: WeatherConditions[];
}

export default function WeatherPanel({ weather }: Props) {
  return (
    <div className="bg-slate-800/80 border border-slate-700/50 rounded-lg shadow-lg shadow-black/20 p-4 h-full overflow-y-auto hover:border-slate-600 transition-colors" style={{ maxHeight: 420 }}>
      <h3 className="text-sm font-semibold text-slate-300 mb-3">
        Current Conditions
      </h3>
      {weather.length === 0 && (
        <p className="text-slate-500 text-sm">No weather data available yet.</p>
      )}
      <div className="space-y-3">
        {weather.map((w) => (
          <div
            key={w.zone_id}
            className="bg-slate-900/50 border border-slate-700/30 rounded p-3 text-sm"
          >
            <div className="font-medium text-slate-200">{w.zone_id}</div>
            <div className="text-slate-500 text-xs mb-1">
              {w.condition_text || "N/A"}
            </div>
            <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs text-slate-400">
              <div>
                Temp: <span className="font-medium text-slate-200">{w.temperature_f ?? "--"}°F</span>
              </div>
              <div>
                Feels: <span className="font-medium text-slate-200">{w.feels_like_f ?? "--"}°F</span>
              </div>
              <div>
                Wind: <span className="font-medium text-slate-200">{w.wind_speed_mph ?? "--"} mph</span>
              </div>
              <div>
                Gusts: <span className="font-medium text-slate-200">{w.wind_gust_mph ?? "--"} mph</span>
              </div>
              <div>
                Humidity: <span className="font-medium text-slate-200">{w.humidity_pct ?? "--"}%</span>
              </div>
              <div>
                Precip: <span className="font-medium text-slate-200">{w.precip_probability_pct ?? "--"}%</span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
