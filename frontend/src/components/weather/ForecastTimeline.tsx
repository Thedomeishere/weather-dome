import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  Bar,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from "recharts";
import type { ForecastPoint, ForecastImpactPoint } from "../../api/types";

interface Props {
  points: ForecastPoint[];
  forecastImpacts?: Record<string, ForecastImpactPoint[]>;
}

export default function ForecastTimeline({ points, forecastImpacts }: Props) {
  // Build a risk lookup from the first zone's forecast impacts
  const riskByHour: Record<string, number> = {};
  if (forecastImpacts) {
    const firstZone = Object.values(forecastImpacts)[0];
    if (firstZone) {
      for (const fi of firstZone) {
        const key = new Date(fi.forecast_for).toISOString().slice(0, 13);
        riskByHour[key] = fi.overall_risk_score;
      }
    }
  }

  const chartData = points.map((p) => {
    const dt = new Date(p.forecast_for);
    const hourKey = dt.toISOString().slice(0, 13);
    return {
      time: dt.toLocaleString("en-US", {
        weekday: "short",
        hour: "numeric",
      }),
      temp: p.temperature_f,
      wind: p.wind_speed_mph,
      precipProb: p.precip_probability_pct,
      risk: riskByHour[hourKey] ?? null,
    };
  });

  return (
    <div className="bg-slate-800/80 border border-slate-700/50 rounded-lg shadow-lg shadow-black/20 p-4 hover:border-slate-600 transition-colors">
      <h3 className="text-sm font-semibold text-slate-300 mb-3">
        5-Day Forecast Timeline
      </h3>
      {chartData.length === 0 ? (
        <p className="text-slate-500 text-sm py-8 text-center">
          No forecast data available yet.
        </p>
      ) : (
        <ResponsiveContainer width="100%" height={250}>
          <ComposedChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis
              dataKey="time"
              tick={{ fontSize: 10, fill: "#94a3b8" }}
              interval={11}
              stroke="#475569"
            />
            <YAxis
              yAxisId="left"
              tick={{ fontSize: 10, fill: "#94a3b8" }}
              stroke="#475569"
              label={{ value: "°F / mph", angle: -90, position: "insideLeft", fontSize: 10, fill: "#94a3b8" }}
            />
            <YAxis
              yAxisId="right"
              orientation="right"
              tick={{ fontSize: 10, fill: "#94a3b8" }}
              stroke="#475569"
              domain={[0, 100]}
              label={{ value: "Risk / Precip %", angle: 90, position: "insideRight", fontSize: 10, fill: "#94a3b8" }}
            />
            <Tooltip />
            <Legend wrapperStyle={{ fontSize: 11, color: "#94a3b8" }} />
            <Area
              yAxisId="right"
              type="monotone"
              dataKey="risk"
              stroke="#dc2626"
              fill="#fca5a5"
              name="Risk Score"
              fillOpacity={0.3}
              connectNulls
              dot={false}
            />
            <Line
              yAxisId="left"
              type="monotone"
              dataKey="temp"
              stroke="#ef4444"
              name="Temp (°F)"
              dot={false}
              strokeWidth={2}
            />
            <Line
              yAxisId="left"
              type="monotone"
              dataKey="wind"
              stroke="#3b82f6"
              name="Wind (mph)"
              dot={false}
              strokeWidth={2}
            />
            <Bar
              yAxisId="right"
              dataKey="precipProb"
              fill="#93c5fd"
              name="Precip %"
              opacity={0.5}
            />
          </ComposedChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
