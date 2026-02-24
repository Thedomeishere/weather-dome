import type { AlertSchema } from "../../api/types";

interface Props {
  alerts: AlertSchema[];
}

const SEVERITY_STYLES: Record<string, string> = {
  Extreme: "bg-red-600 text-white",
  Severe: "bg-orange-500 text-white",
  Moderate: "bg-yellow-400 text-gray-900",
  Minor: "bg-blue-100 text-blue-800",
};

export default function AlertBanner({ alerts }: Props) {
  if (alerts.length === 0) return null;

  return (
    <div className="mb-6 space-y-2">
      {alerts.map((alert) => (
        <div
          key={alert.alert_id}
          className={`rounded-lg p-3 ${SEVERITY_STYLES[alert.severity] || "bg-gray-200 text-gray-800"}`}
        >
          <div className="flex items-center justify-between">
            <div className="font-semibold text-sm">
              {alert.event} — {alert.zone_id}
            </div>
            <span className="text-xs opacity-80">{alert.severity}</span>
          </div>
          {alert.headline && (
            <p className="text-sm mt-1 opacity-90">{alert.headline}</p>
          )}
        </div>
      ))}
    </div>
  );
}
