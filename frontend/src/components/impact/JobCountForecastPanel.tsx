import { useState, useMemo } from "react";
import {
  ResponsiveContainer,
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from "recharts";
import type { JobCountEstimate, ForecastImpactPoint } from "../../api/types";

const ZONE_GROUPS: Record<string, string[]> = {
  "Bronx/Westchester": ["CONED-BRX", "CONED-WST"],
  "Brooklyn/Queens": ["CONED-BKN", "CONED-QNS"],
};

interface Props {
  jobForecast: JobCountEstimate[];
  forecastImpacts: Record<string, ForecastImpactPoint[]>;
}

export default function JobCountForecastPanel({
  jobForecast,
  forecastImpacts,
}: Props) {
  const zoneIds = Object.keys(forecastImpacts);
  const [selected, setSelected] = useState(zoneIds[0] ?? "");

  // Territory-wide totals
  const totalLow = jobForecast.reduce((s, j) => s + j.estimated_jobs_low, 0);
  const totalMid = jobForecast.reduce((s, j) => s + j.estimated_jobs_mid, 0);
  const totalHigh = jobForecast.reduce((s, j) => s + j.estimated_jobs_high, 0);

  const isGroup = selected in ZONE_GROUPS;

  const chartData = useMemo(() => {
    const ids = isGroup ? ZONE_GROUPS[selected] : [selected];
    const present = ids.filter((id) => forecastImpacts[id]?.length);
    if (present.length === 0) return [];

    const byHour = new Map<
      number,
      { low: number; mid: number; high: number; time: string }
    >();
    for (const id of present) {
      for (const p of forecastImpacts[id]) {
        const existing = byHour.get(p.forecast_hour);
        if (existing) {
          existing.low += p.estimated_outages_low;
          existing.mid += p.estimated_outages;
          existing.high += p.estimated_outages_high;
        } else {
          byHour.set(p.forecast_hour, {
            low: p.estimated_outages_low,
            mid: p.estimated_outages,
            high: p.estimated_outages_high,
            time: new Date(p.forecast_for).toLocaleString("en-US", {
              weekday: "short",
              hour: "numeric",
            }),
          });
        }
      }
    }

    return Array.from(byHour.entries())
      .sort(([a], [b]) => a - b)
      .map(([, v]) => v);
  }, [forecastImpacts, selected, isGroup]);

  return (
    <div className="bg-white rounded-lg shadow p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-700">
          Predicted Outage Jobs
        </h3>
        {zoneIds.length > 0 && (
          <select
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
            className="text-sm border border-gray-300 rounded px-2 py-1"
          >
            {zoneIds.map((id) => (
              <option key={id} value={id}>
                {id}
              </option>
            ))}
            <optgroup label="Zone Groups">
              {Object.keys(ZONE_GROUPS).map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </optgroup>
          </select>
        )}
      </div>

      {/* Summary row */}
      <div className="grid grid-cols-3 gap-3 mb-4 text-center">
        <div className="bg-green-50 rounded p-2">
          <div className="text-xs text-gray-500">Low</div>
          <div className="text-lg font-bold text-green-700">
            {totalLow.toLocaleString()}
          </div>
        </div>
        <div className="bg-yellow-50 rounded p-2">
          <div className="text-xs text-gray-500">Mid</div>
          <div className="text-lg font-bold text-yellow-700">
            {totalMid.toLocaleString()}
          </div>
        </div>
        <div className="bg-red-50 rounded p-2">
          <div className="text-xs text-gray-500">High</div>
          <div className="text-lg font-bold text-red-700">
            {totalHigh.toLocaleString()}
          </div>
        </div>
      </div>

      {/* Forecast chart */}
      {chartData.length > 0 && (
        <ResponsiveContainer width="100%" height={250}>
          <ComposedChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="time" tick={{ fontSize: 10 }} interval={3} />
            <YAxis
              tick={{ fontSize: 10 }}
              label={{
                value: "Outages",
                angle: -90,
                position: "insideLeft",
                fontSize: 10,
              }}
            />
            <Tooltip />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Area
              type="monotone"
              dataKey="high"
              stroke="none"
              fill="#fca5a5"
              fillOpacity={0.4}
              name="High"
            />
            <Area
              type="monotone"
              dataKey="low"
              stroke="none"
              fill="#ffffff"
              fillOpacity={1}
              name="Low"
            />
            <Line
              type="monotone"
              dataKey="mid"
              stroke="#f59e0b"
              name="Mid Estimate"
              dot={false}
              strokeWidth={2}
            />
            <Line
              type="monotone"
              dataKey="high"
              stroke="#ef4444"
              name="High"
              dot={false}
              strokeWidth={1}
              strokeDasharray="4 2"
            />
            <Line
              type="monotone"
              dataKey="low"
              stroke="#22c55e"
              name="Low"
              dot={false}
              strokeWidth={1}
              strokeDasharray="4 2"
            />
          </ComposedChart>
        </ResponsiveContainer>
      )}

      {/* Per-zone table */}
      {jobForecast.length > 0 && (
        <div className="overflow-x-auto mt-4">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-gray-500 border-b">
                <th className="pb-2">Zone</th>
                <th className="pb-2 text-right">Low</th>
                <th className="pb-2 text-right">Mid</th>
                <th className="pb-2 text-right">High</th>
                <th className="pb-2 text-center">Risk Level</th>
              </tr>
            </thead>
            <tbody>
              {jobForecast.map((j) => (
                <tr key={j.zone_id} className="border-b border-gray-50">
                  <td className="py-2 font-medium">{j.zone_id}</td>
                  <td className="py-2 text-right">
                    {j.estimated_jobs_low.toLocaleString()}
                  </td>
                  <td className="py-2 text-right">
                    {j.estimated_jobs_mid.toLocaleString()}
                  </td>
                  <td className="py-2 text-right">
                    {j.estimated_jobs_high.toLocaleString()}
                  </td>
                  <td className="py-2 text-center">
                    <span
                      className={`text-xs px-2 py-0.5 rounded font-medium ${riskBadge(j.risk_level)}`}
                    >
                      {j.risk_level}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {jobForecast.length === 0 && (
        <p className="text-gray-400 text-sm text-center py-4">
          No job forecast data available yet.
        </p>
      )}
    </div>
  );
}

function riskBadge(level: string): string {
  switch (level) {
    case "Low":
      return "bg-green-100 text-green-700";
    case "Moderate":
      return "bg-yellow-100 text-yellow-700";
    case "High":
      return "bg-orange-100 text-orange-700";
    case "Extreme":
      return "bg-red-100 text-red-700";
    default:
      return "bg-gray-100 text-gray-700";
  }
}
