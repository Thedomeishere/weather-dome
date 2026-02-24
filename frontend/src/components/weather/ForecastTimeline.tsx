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
    <div className="bg-white rounded-lg shadow p-4">
      <h3 className="text-sm font-semibold text-gray-700 mb-3">
        5-Day Forecast Timeline
      </h3>
      {chartData.length === 0 ? (
        <p className="text-gray-400 text-sm py-8 text-center">
          No forecast data available yet.
        </p>
      ) : (
        <ResponsiveContainer width="100%" height={250}>
          <ComposedChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis
              dataKey="time"
              tick={{ fontSize: 10 }}
              interval={11}
            />
            <YAxis
              yAxisId="left"
              tick={{ fontSize: 10 }}
              label={{ value: "°F / mph", angle: -90, position: "insideLeft", fontSize: 10 }}
            />
            <YAxis
              yAxisId="right"
              orientation="right"
              tick={{ fontSize: 10 }}
              domain={[0, 100]}
              label={{ value: "Risk / Precip %", angle: 90, position: "insideRight", fontSize: 10 }}
            />
            <Tooltip />
            <Legend wrapperStyle={{ fontSize: 11 }} />
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
