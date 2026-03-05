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

  // Compute peak forecast jobs per zone (next 48h) for the summary table
  const peakByZone = useMemo(() => {
    const peaks: Record<
      string,
      { low: number; mid: number; high: number; peakHour: number }
    > = {};
    for (const [zoneId, pts] of Object.entries(forecastImpacts)) {
      let best = { low: 0, mid: 0, high: 0, peakHour: 0 };
      for (const p of pts) {
        if (p.forecast_hour > 48) continue;
        const mid = p.estimated_jobs_mid ?? p.estimated_outages ?? 0;
        if (mid > best.mid) {
          best = {
            low: p.estimated_jobs_low ?? 0,
            mid,
            high: p.estimated_jobs_high ?? p.estimated_outages_high ?? 0,
            peakHour: p.forecast_hour,
          };
        }
      }
      peaks[zoneId] = best;
    }
    return peaks;
  }, [forecastImpacts]);

  // Territory-wide totals from peak forecast (not just current snapshot)
  const totalLow = Object.values(peakByZone).reduce((s, p) => s + p.low, 0);
  const totalMid = Object.values(peakByZone).reduce((s, p) => s + p.mid, 0);
  const totalHigh = Object.values(peakByZone).reduce((s, p) => s + p.high, 0);

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
        const jLow = p.estimated_jobs_low ?? p.estimated_outages_low;
        const jMid = p.estimated_jobs_mid ?? p.estimated_outages;
        const jHigh = p.estimated_jobs_high ?? p.estimated_outages_high;
        const existing = byHour.get(p.forecast_hour);
        if (existing) {
          existing.low += jLow;
          existing.mid += jMid;
          existing.high += jHigh;
        } else {
          byHour.set(p.forecast_hour, {
            low: jLow,
            mid: jMid,
            high: jHigh,
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
    <div className="bg-slate-800/80 border border-slate-700/50 rounded-lg shadow-lg shadow-black/20 p-4 hover:border-slate-600 transition-colors">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-slate-300">
          Predicted Outage Jobs
        </h3>
        {zoneIds.length > 0 && (
          <select
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
            className="text-sm bg-slate-900 border border-slate-600 text-slate-200 rounded px-2 py-1"
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
        <div className="bg-emerald-900/30 border border-emerald-800/40 rounded p-2">
          <div className="text-xs text-slate-400">Low</div>
          <div className="text-lg font-bold text-emerald-400">
            {totalLow.toLocaleString()}
          </div>
        </div>
        <div className="bg-yellow-900/30 border border-yellow-800/40 rounded p-2">
          <div className="text-xs text-slate-400">Mid</div>
          <div className="text-lg font-bold text-yellow-400">
            {totalMid.toLocaleString()}
          </div>
        </div>
        <div className="bg-red-900/30 border border-red-800/40 rounded p-2">
          <div className="text-xs text-slate-400">High</div>
          <div className="text-lg font-bold text-red-400">
            {totalHigh.toLocaleString()}
          </div>
        </div>
      </div>

      {/* Forecast chart */}
      {chartData.length > 0 && (
        <ResponsiveContainer width="100%" height={250}>
          <ComposedChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis dataKey="time" tick={{ fontSize: 10, fill: "#94a3b8" }} interval={3} stroke="#475569" />
            <YAxis
              tick={{ fontSize: 10, fill: "#94a3b8" }}
              stroke="#475569"
              label={{
                value: "Outages",
                angle: -90,
                position: "insideLeft",
                fontSize: 10,
                fill: "#94a3b8",
              }}
            />
            <Tooltip />
            <Legend wrapperStyle={{ fontSize: 11, color: "#94a3b8" }} />
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
              fill="#0f172a"
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

      {/* Per-zone peak forecast table */}
      {Object.keys(peakByZone).length > 0 && (
        <div className="overflow-x-auto mt-4">
          <p className="text-xs text-slate-500 mb-1">Peak predicted jobs (next 48h)</p>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-slate-500 border-b border-slate-700">
                <th className="pb-2">Zone</th>
                <th className="pb-2 text-right">Low</th>
                <th className="pb-2 text-right">Mid</th>
                <th className="pb-2 text-right">High</th>
                <th className="pb-2 text-center">Peak Hr</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(peakByZone)
                .sort(([, a], [, b]) => b.mid - a.mid)
                .map(([zoneId, peak]) => (
                <tr key={zoneId} className="border-b border-slate-700/50 hover:bg-slate-700/30 transition-colors">
                  <td className="py-2 font-medium text-slate-200">{zoneId}</td>
                  <td className="py-2 text-right text-slate-400">
                    {peak.low.toLocaleString()}
                  </td>
                  <td className="py-2 text-right font-semibold text-slate-200">
                    {peak.mid.toLocaleString()}
                  </td>
                  <td className="py-2 text-right text-slate-400">
                    {peak.high.toLocaleString()}
                  </td>
                  <td className="py-2 text-center">
                    <span className="text-xs text-slate-500">
                      +{peak.peakHour}h
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {Object.keys(peakByZone).length === 0 && jobForecast.length === 0 && (
        <p className="text-slate-500 text-sm text-center py-4">
          No job forecast data available yet.
        </p>
      )}
    </div>
  );
}
