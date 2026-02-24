import type { WeatherConditions } from "../../api/types";

interface Props {
  weather: WeatherConditions[];
}

export default function WeatherPanel({ weather }: Props) {
  return (
    <div className="bg-white rounded-lg shadow p-4 h-full overflow-y-auto" style={{ maxHeight: 420 }}>
      <h3 className="text-sm font-semibold text-gray-700 mb-3">
        Current Conditions
      </h3>
      {weather.length === 0 && (
        <p className="text-gray-400 text-sm">No weather data available yet.</p>
      )}
      <div className="space-y-3">
        {weather.map((w) => (
          <div
            key={w.zone_id}
            className="border border-gray-100 rounded p-3 text-sm"
          >
            <div className="font-medium text-gray-800">{w.zone_id}</div>
            <div className="text-gray-500 text-xs mb-1">
              {w.condition_text || "N/A"}
            </div>
            <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
              <div>
                Temp: <span className="font-medium">{w.temperature_f ?? "--"}°F</span>
              </div>
              <div>
                Feels: <span className="font-medium">{w.feels_like_f ?? "--"}°F</span>
              </div>
              <div>
                Wind: <span className="font-medium">{w.wind_speed_mph ?? "--"} mph</span>
              </div>
              <div>
                Gusts: <span className="font-medium">{w.wind_gust_mph ?? "--"} mph</span>
              </div>
              <div>
                Humidity: <span className="font-medium">{w.humidity_pct ?? "--"}%</span>
              </div>
              <div>
                Precip: <span className="font-medium">{w.precip_probability_pct ?? "--"}%</span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
