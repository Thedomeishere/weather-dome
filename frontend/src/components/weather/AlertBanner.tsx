import type { AlertSchema } from "../../api/types";

interface Props {
  alerts: AlertSchema[];
}

const SEVERITY_STYLES: Record<string, string> = {
  Extreme: "bg-red-900/80 text-red-100 animate-pulse-glow",
  Severe: "bg-orange-900/70 text-orange-100 animate-pulse-glow-orange",
  Moderate: "bg-yellow-900/60 text-yellow-100",
  Minor: "bg-blue-900/50 text-blue-100",
};

export default function AlertBanner({ alerts }: Props) {
  if (alerts.length === 0) return null;

  return (
    <div className="mb-6 space-y-2">
      {alerts.map((alert) => {
        const content = (
          <div
            className={`rounded-lg p-3 border border-slate-700/50 ${SEVERITY_STYLES[alert.severity] || "bg-slate-800 text-slate-200"}`}
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
        );

        return alert.url ? (
          <a
            key={alert.alert_id}
            href={alert.url}
            target="_blank"
            rel="noopener noreferrer"
            className="block hover:brightness-110 hover:shadow-lg hover:-translate-y-0.5 transition-all duration-150 cursor-pointer"
          >
            {content}
          </a>
        ) : (
          <div key={alert.alert_id}>{content}</div>
        );
      })}
    </div>
  );
}
