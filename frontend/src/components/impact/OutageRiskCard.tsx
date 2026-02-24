import type { ZoneImpact } from "../../api/types";

interface Props {
  zones: ZoneImpact[];
}

export default function OutageRiskCard({ zones }: Props) {
  const maxRisk = zones.reduce(
    (best, z) =>
      z.outage_risk && z.outage_risk.score > (best?.score ?? 0) ? z.outage_risk : best,
    zones[0]?.outage_risk ?? null
  );

  const totalOutages = zones.reduce(
    (sum, z) => sum + (z.outage_risk?.estimated_outages ?? 0),
    0
  );

  return (
    <div className="bg-white rounded-lg shadow p-4">
      <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
        Outage Risk
      </h4>
      <div className={`text-2xl font-bold mt-1 ${riskColor(maxRisk?.level)}`}>
        {maxRisk?.level ?? "N/A"}
      </div>
      <div className="text-sm text-gray-600 mt-1">
        Score: {maxRisk?.score?.toFixed(1) ?? "--"} / 100
      </div>
      <div className="text-sm text-gray-600">
        Est. Outages: {totalOutages.toLocaleString()}
      </div>
      {maxRisk?.contributing_factors && maxRisk.contributing_factors.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {maxRisk.contributing_factors.map((f, i) => (
            <span
              key={i}
              className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded"
            >
              {f}
            </span>
          ))}
        </div>
      )}
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
