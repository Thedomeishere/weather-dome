import type { ZoneImpact } from "../../api/types";

interface Props {
  zones: ZoneImpact[];
}

export default function EquipmentStressCard({ zones }: Props) {
  const maxStress = zones.reduce(
    (best, z) =>
      z.equipment_stress && z.equipment_stress.score > (best?.score ?? 0)
        ? z.equipment_stress
        : best,
    zones[0]?.equipment_stress ?? null
  );

  const level = maxStress?.level;
  const glowClass =
    level === "Extreme"
      ? "border-red-700/70 animate-pulse-glow"
      : level === "High"
        ? "border-orange-700/50 animate-pulse-glow-orange"
        : "border-slate-700/50";

  return (
    <div className={`bg-slate-800/80 rounded-lg shadow-lg shadow-black/20 border p-4 hover:border-slate-600 transition-colors ${glowClass}`}>
      <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wide">
        Equipment Stress
      </h4>
      <div className={`text-2xl font-bold mt-1 ${riskColor(level)} ${level === "Extreme" ? "animate-pulse-alert" : ""}`}>
        {maxStress?.level ?? "N/A"}
      </div>
      <div className="text-sm text-slate-400 mt-1">
        Score: {maxStress?.score?.toFixed(1) ?? "--"} / 100
      </div>
      <div className="grid grid-cols-2 gap-2 mt-2 text-xs">
        <div className="bg-slate-900/60 border border-slate-700/30 rounded p-2">
          <div className="text-slate-500">Transformer</div>
          <div className="font-semibold text-slate-200">
            {maxStress?.transformer_risk?.toFixed(1) ?? "--"}
          </div>
        </div>
        <div className="bg-slate-900/60 border border-slate-700/30 rounded p-2">
          <div className="text-slate-500">Line Sag</div>
          <div className="font-semibold text-slate-200">
            {maxStress?.line_sag_risk?.toFixed(1) ?? "--"}
          </div>
        </div>
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
