import type { ZoneImpact } from "../../api/types";

interface Props {
  zones: ZoneImpact[];
}

export default function MeltRiskCard({ zones }: Props) {
  // Only show zones with underground infrastructure (melt_risk present and non-zero)
  const undergroundZones = zones.filter(
    (z) => z.melt_risk && z.melt_risk.score > 0
  );

  const maxMelt = undergroundZones.reduce(
    (max, z) => (z.melt_risk && z.melt_risk.score > (max?.score ?? 0) ? z.melt_risk : max),
    undergroundZones[0]?.melt_risk ?? null
  );

  const score = maxMelt?.score ?? 0;
  const level = maxMelt?.level ?? "Low";

  return (
    <div className="bg-white rounded-lg shadow p-4">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-gray-700">Melt Risk</h3>
        <span
          className={`text-xs font-medium px-2 py-0.5 rounded ${levelBadge(level)}`}
        >
          {level}
        </span>
      </div>
      <div className={`text-3xl font-bold ${levelColor(level)}`}>
        {score.toFixed(0)}
      </div>
      <p className="text-xs text-gray-500 mt-1">Underground melt risk score</p>

      {maxMelt && maxMelt.contributing_factors.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1">
          {maxMelt.contributing_factors.map((f, i) => (
            <span
              key={i}
              className="text-xs bg-cyan-50 text-cyan-700 px-2 py-0.5 rounded"
            >
              {f}
            </span>
          ))}
        </div>
      )}

      {undergroundZones.length > 0 && (
        <div className="mt-3 space-y-1">
          {undergroundZones
            .sort((a, b) => (b.melt_risk?.score ?? 0) - (a.melt_risk?.score ?? 0))
            .slice(0, 3)
            .map((z) => (
              <div key={z.zone_id} className="flex justify-between text-xs">
                <span className="text-gray-600">{z.zone_name}</span>
                <span className={levelColor(z.melt_risk?.level ?? "Low")}>
                  {z.melt_risk?.score.toFixed(0) ?? 0}
                </span>
              </div>
            ))}
        </div>
      )}
    </div>
  );
}

function levelColor(level: string): string {
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

function levelBadge(level: string): string {
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
