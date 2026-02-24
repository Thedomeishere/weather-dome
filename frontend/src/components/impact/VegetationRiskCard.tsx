import type { ZoneImpact } from "../../api/types";

interface Props {
  zones: ZoneImpact[];
}

export default function VegetationRiskCard({ zones }: Props) {
  const maxRisk = zones.reduce(
    (best, z) =>
      z.vegetation_risk && z.vegetation_risk.score > (best?.score ?? 0)
        ? z.vegetation_risk
        : best,
    zones[0]?.vegetation_risk ?? null
  );

  return (
    <div className="bg-white rounded-lg shadow p-4">
      <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
        Vegetation Risk
      </h4>
      <div className={`text-2xl font-bold mt-1 ${riskColor(maxRisk?.level)}`}>
        {maxRisk?.level ?? "N/A"}
      </div>
      <div className="text-sm text-gray-600 mt-1">
        Score: {maxRisk?.score?.toFixed(1) ?? "--"} / 100
      </div>
      <div className="text-sm text-gray-600">
        Foliage: {maxRisk?.foliage_factor?.toFixed(1) ?? "--"} | Soil:{" "}
        {maxRisk?.soil_saturation ?? "--"}
      </div>
    </div>
  );
}

function riskColor(level?: string): string {
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
