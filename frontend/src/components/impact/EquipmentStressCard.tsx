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

  return (
    <div className="bg-white rounded-lg shadow p-4">
      <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
        Equipment Stress
      </h4>
      <div className={`text-2xl font-bold mt-1 ${riskColor(maxStress?.level)}`}>
        {maxStress?.level ?? "N/A"}
      </div>
      <div className="text-sm text-gray-600 mt-1">
        Score: {maxStress?.score?.toFixed(1) ?? "--"} / 100
      </div>
      <div className="grid grid-cols-2 gap-2 mt-2 text-xs">
        <div className="bg-gray-50 rounded p-2">
          <div className="text-gray-400">Transformer</div>
          <div className="font-semibold">
            {maxStress?.transformer_risk?.toFixed(1) ?? "--"}
          </div>
        </div>
        <div className="bg-gray-50 rounded p-2">
          <div className="text-gray-400">Line Sag</div>
          <div className="font-semibold">
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
