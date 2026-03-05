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

  const level = maxRisk?.level;
  const glowClass =
    level === "Extreme"
      ? "border-red-700/70 animate-pulse-glow"
      : level === "High"
        ? "border-orange-700/50 animate-pulse-glow-orange"
        : "border-slate-700/50";

  return (
    <div className={`bg-slate-800/80 rounded-lg shadow-lg shadow-black/20 border p-4 hover:border-slate-600 transition-colors ${glowClass}`}>
      <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wide">
        Outage Risk
      </h4>
      <div className={`text-2xl font-bold mt-1 ${riskColor(level)} ${level === "Extreme" ? "animate-pulse-alert" : ""}`}>
        {maxRisk?.level ?? "N/A"}
      </div>
      <div className="text-sm text-slate-400 mt-1">
        Score: {maxRisk?.score?.toFixed(1) ?? "--"} / 100
      </div>
      <div className="text-sm text-slate-400">
        Est. Outages: {totalOutages.toLocaleString()}
      </div>
      {maxRisk?.contributing_factors && maxRisk.contributing_factors.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {maxRisk.contributing_factors.map((f, i) => (
            <span
              key={i}
              className="text-xs bg-slate-700/70 text-slate-300 px-2 py-0.5 rounded"
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
      return "text-emerald-400";
    case "Moderate":
      return "text-yellow-400";
    case "High":
      return "text-orange-400";
    case "Extreme":
      return "text-red-400";
    default:
      return "text-slate-500";
  }
}
