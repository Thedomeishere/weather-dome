import type { ZoneImpact } from "../../api/types";

interface Props {
  zones: ZoneImpact[];
}

export default function LoadForecastCard({ zones }: Props) {
  const totalLoad = zones.reduce(
    (sum, z) => sum + (z.load_forecast?.load_mw ?? 0),
    0
  );
  const totalCapacity = zones.reduce(
    (sum, z) => sum + (z.load_forecast?.capacity_mw ?? 0),
    0
  );
  const pct = totalCapacity > 0 ? (totalLoad / totalCapacity) * 100 : 0;

  const maxLevel = zones.reduce((worst, z) => {
    const rank = riskRank(z.load_forecast?.risk_level);
    return rank > riskRank(worst) ? (z.load_forecast?.risk_level ?? "Low") : worst;
  }, "Low");

  return (
    <div className="bg-white rounded-lg shadow p-4">
      <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
        Load Forecast
      </h4>
      <div className={`text-2xl font-bold mt-1 ${riskColor(maxLevel)}`}>
        {pct.toFixed(1)}%
      </div>
      <div className="text-sm text-gray-600 mt-1">
        {totalLoad.toFixed(0)} / {totalCapacity.toFixed(0)} MW
      </div>
      <div className="w-full bg-gray-200 rounded-full h-2 mt-2">
        <div
          className={`h-2 rounded-full ${barColor(pct)}`}
          style={{ width: `${Math.min(100, pct)}%` }}
        />
      </div>
    </div>
  );
}

function riskRank(level?: string): number {
  switch (level) {
    case "Low":
      return 0;
    case "Moderate":
      return 1;
    case "High":
      return 2;
    case "Extreme":
      return 3;
    default:
      return -1;
  }
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
      return "text-gray-500";
  }
}

function barColor(pct: number): string {
  if (pct < 70) return "bg-green-500";
  if (pct < 85) return "bg-yellow-500";
  if (pct < 95) return "bg-orange-500";
  return "bg-red-500";
}
