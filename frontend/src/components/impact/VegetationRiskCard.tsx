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
        Vegetation Risk
      </h4>
      <div className={`text-2xl font-bold mt-1 ${riskColor(level)} ${level === "Extreme" ? "animate-pulse-alert" : ""}`}>
        {maxRisk?.level ?? "N/A"}
      </div>
      <div className="text-sm text-slate-400 mt-1">
        Score: {maxRisk?.score?.toFixed(1) ?? "--"} / 100
      </div>
      <div className="text-sm text-slate-400">
        Foliage: {maxRisk?.foliage_factor?.toFixed(1) ?? "--"} | Soil:{" "}
        {maxRisk?.soil_saturation ?? "--"}
      </div>
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
