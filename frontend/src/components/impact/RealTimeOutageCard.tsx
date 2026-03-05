import type { ZoneOutageStatus } from "../../api/types";

interface Props {
  outageStatus: ZoneOutageStatus[];
}

export default function RealTimeOutageCard({ outageStatus }: Props) {
  const totalOutages = outageStatus.reduce((s, o) => s + o.active_outages, 0);
  const totalCustomers = outageStatus.reduce(
    (s, o) => s + o.customers_affected,
    0
  );
  const risingZones = outageStatus.filter((o) => o.trend === "rising");

  return (
    <div className="bg-slate-800/80 border border-slate-700/50 rounded-lg shadow-lg shadow-black/20 p-4 hover:border-slate-600 transition-colors">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-slate-300">Active Outages</h3>
        {risingZones.length > 0 && (
          <span className="text-xs font-medium px-2 py-0.5 rounded bg-red-900/50 text-red-300 animate-pulse-alert">
            {risingZones.length} zone{risingZones.length > 1 ? "s" : ""} rising
          </span>
        )}
      </div>
      <div
        className={`text-3xl font-bold ${totalOutages > 0 ? "text-red-400" : "text-emerald-400"}`}
      >
        {totalOutages}
      </div>
      <p className="text-xs text-slate-500 mt-1">
        {totalCustomers.toLocaleString()} customers affected
      </p>

      {outageStatus.filter((o) => o.active_outages > 0).length > 0 && (
        <div className="mt-3 space-y-1">
          {outageStatus
            .filter((o) => o.active_outages > 0)
            .sort((a, b) => b.active_outages - a.active_outages)
            .slice(0, 4)
            .map((o) => (
              <div key={o.zone_id} className="flex justify-between text-xs">
                <span className="text-slate-400">{o.zone_id}</span>
                <span className="flex items-center gap-1">
                  <span className="text-slate-200 font-medium">
                    {o.active_outages}
                  </span>
                  {o.trend === "rising" && (
                    <span className="text-red-400">&#9650;</span>
                  )}
                  {o.trend === "falling" && (
                    <span className="text-emerald-400">&#9660;</span>
                  )}
                </span>
              </div>
            ))}
        </div>
      )}
    </div>
  );
}
