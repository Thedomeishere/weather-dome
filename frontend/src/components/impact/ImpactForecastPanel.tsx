import { useState, useMemo } from "react";
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceArea,
} from "recharts";
import type { ForecastImpactPoint } from "../../api/types";

const ZONE_GROUPS: Record<string, string[]> = {
  "Bronx/Westchester": ["CONED-BRX", "CONED-WST"],
  "Brooklyn/Queens": ["CONED-BKN", "CONED-QNS"],
};

function outageRangeLabel(outages: number): string {
  if (outages < 50) return "Low";
  if (outages <= 200) return "Mid";
  return "High";
}

function aggregatePoints(
  forecastImpacts: Record<string, ForecastImpactPoint[]>,
  zoneIds: string[],
): ForecastImpactPoint[] {
  const present = zoneIds.filter((id) => forecastImpacts[id]?.length);
  if (present.length === 0) return [];

  const byHour = new Map<number, ForecastImpactPoint[]>();
  for (const id of present) {
    for (const p of forecastImpacts[id]) {
      const arr = byHour.get(p.forecast_hour);
      if (arr) arr.push(p);
      else byHour.set(p.forecast_hour, [p]);
    }
  }

  return Array.from(byHour.entries())
    .sort(([a], [b]) => a - b)
    .map(([, pts]) => {
      const n = pts.length;
      const avg = (fn: (p: ForecastImpactPoint) => number) =>
        Math.round(pts.reduce((s, p) => s + fn(p), 0) / n);
      const sum = (fn: (p: ForecastImpactPoint) => number) =>
        pts.reduce((s, p) => s + fn(p), 0);
      const maxOverall = pts.reduce((mx, p) =>
        p.overall_risk_score > mx.overall_risk_score ? p : mx,
      );
      return {
        forecast_for: maxOverall.forecast_for,
        forecast_hour: maxOverall.forecast_hour,
        overall_risk_score: avg((p) => p.overall_risk_score),
        overall_risk_level: maxOverall.overall_risk_level,
        outage_risk_score: avg((p) => p.outage_risk_score),
        estimated_outages: sum((p) => p.estimated_outages),
        vegetation_risk_score: avg((p) => p.vegetation_risk_score),
        load_pct_capacity: avg((p) => p.load_pct_capacity),
        equipment_stress_score: avg((p) => p.equipment_stress_score),
      };
    });
}

interface Props {
  forecastImpacts: Record<string, ForecastImpactPoint[]>;
}

export default function ImpactForecastPanel({ forecastImpacts }: Props) {
  const zoneIds = Object.keys(forecastImpacts);
  const [selected, setSelected] = useState(zoneIds[0] ?? "");

  const isGroup = selected in ZONE_GROUPS;

  const points = useMemo(() => {
    if (isGroup) {
      return aggregatePoints(forecastImpacts, ZONE_GROUPS[selected]);
    }
    return forecastImpacts[selected] ?? [];
  }, [forecastImpacts, selected, isGroup]);

  const chartData = useMemo(
    () =>
      points.map((p) => ({
        time: new Date(p.forecast_for).toLocaleString("en-US", {
          weekday: "short",
          hour: "numeric",
        }),
        overall: p.overall_risk_score,
        outage: p.outage_risk_score,
        equipment: p.equipment_stress_score,
        load: p.load_pct_capacity,
      })),
    [points],
  );

  const peakRisk = useMemo(() => {
    if (!points.length) return null;
    return points.reduce((max, p) =>
      p.overall_risk_score > max.overall_risk_score ? p : max,
    );
  }, [points]);

  if (zoneIds.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow p-4">
        <h3 className="text-sm font-semibold text-gray-700 mb-3">
          Impact Forecast
        </h3>
        <p className="text-gray-400 text-sm py-8 text-center">
          No forecast impact data available yet.
        </p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg shadow p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-700">
          5-Day Impact Forecast
        </h3>
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
      </div>

      {peakRisk && (
        <p className="text-xs text-gray-500 mb-2">
          Peak risk:{" "}
          <span className={`font-semibold ${riskColor(peakRisk.overall_risk_level)}`}>
            {peakRisk.overall_risk_level} ({peakRisk.overall_risk_score})
          </span>{" "}
          at hour +{peakRisk.forecast_hour} —{" "}
          {new Date(peakRisk.forecast_for).toLocaleString("en-US", {
            weekday: "short",
            month: "short",
            day: "numeric",
            hour: "numeric",
          })}
          {" | Est. Outages: "}
          {outageRangeLabel(peakRisk.estimated_outages)}
          {` (${peakRisk.estimated_outages})`}
        </p>
      )}

      <ResponsiveContainer width="100%" height={280}>
        <ComposedChart data={chartData}>
          {/* Risk band backgrounds */}
          <ReferenceArea yAxisId="left" y1={0} y2={25} fill="#22c55e" fillOpacity={0.07} />
          <ReferenceArea yAxisId="left" y1={25} y2={50} fill="#eab308" fillOpacity={0.07} />
          <ReferenceArea yAxisId="left" y1={50} y2={75} fill="#f97316" fillOpacity={0.07} />
          <ReferenceArea yAxisId="left" y1={75} y2={100} fill="#ef4444" fillOpacity={0.07} />

          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="time" tick={{ fontSize: 10 }} interval={3} />
          <YAxis
            yAxisId="left"
            tick={{ fontSize: 10 }}
            domain={[0, 100]}
            label={{ value: "Score / %", angle: -90, position: "insideLeft", fontSize: 10 }}
          />
          <Tooltip />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          <Line
            yAxisId="left"
            type="monotone"
            dataKey="overall"
            stroke="#ef4444"
            name="Overall Risk"
            dot={false}
            strokeWidth={2}
          />
          <Line
            yAxisId="left"
            type="monotone"
            dataKey="outage"
            stroke="#f97316"
            name="Outage Risk"
            dot={false}
            strokeWidth={1.5}
            strokeDasharray="4 2"
          />
          <Line
            yAxisId="left"
            type="monotone"
            dataKey="equipment"
            stroke="#8b5cf6"
            name="Equipment Stress"
            dot={false}
            strokeWidth={1.5}
            strokeDasharray="4 2"
          />
          <Line
            yAxisId="left"
            type="monotone"
            dataKey="load"
            stroke="#3b82f6"
            name="Load % Capacity"
            dot={false}
            strokeWidth={1.5}
          />
        </ComposedChart>
      </ResponsiveContainer>
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
