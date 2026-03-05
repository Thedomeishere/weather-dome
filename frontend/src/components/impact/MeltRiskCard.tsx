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

  const glowClass =
    level === "Extreme"
      ? "border-red-700/70 animate-pulse-glow"
      : level === "High"
        ? "border-orange-700/50 animate-pulse-glow-orange"
        : "border-slate-700/50";

  return (
    <div className={`bg-slate-800/80 rounded-lg shadow-lg shadow-black/20 border p-4 hover:border-slate-600 transition-colors ${glowClass}`}>
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-slate-300">Melt Risk</h3>
        <span
          className={`text-xs font-medium px-2 py-0.5 rounded ${levelBadge(level)}`}
        >
          {level}
        </span>
      </div>
      <div className={`text-3xl font-bold ${levelColor(level)} ${level === "Extreme" ? "animate-pulse-alert" : ""}`}>
        {score.toFixed(0)}
      </div>
      <p className="text-xs text-slate-500 mt-1">Underground melt risk score</p>

      {maxMelt && maxMelt.contributing_factors.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1">
          {maxMelt.contributing_factors.map((f, i) => (
            <span
              key={i}
              className="text-xs bg-cyan-900/50 text-cyan-300 px-2 py-0.5 rounded"
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
                <span className="text-slate-400">{z.zone_name}</span>
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
      return "text-emerald-400";
    case "Moderate":
      return "text-yellow-400";
    case "High":
      return "text-orange-400";
    case "Extreme":
      return "text-red-400";
    default:
      return "text-slate-400";
  }
}

function levelBadge(level: string): string {
  switch (level) {
    case "Low":
      return "bg-emerald-900/50 text-emerald-300";
    case "Moderate":
      return "bg-yellow-900/50 text-yellow-300";
    case "High":
      return "bg-orange-900/50 text-orange-300";
    case "Extreme":
      return "bg-red-900/50 text-red-300";
    default:
      return "bg-slate-700 text-slate-300";
  }
}
