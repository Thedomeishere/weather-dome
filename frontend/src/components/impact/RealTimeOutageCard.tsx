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
    <div className="bg-white rounded-lg shadow p-4">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-gray-700">Active Outages</h3>
        {risingZones.length > 0 && (
          <span className="text-xs font-medium px-2 py-0.5 rounded bg-red-100 text-red-700">
            {risingZones.length} zone{risingZones.length > 1 ? "s" : ""} rising
          </span>
        )}
      </div>
      <div
        className={`text-3xl font-bold ${totalOutages > 0 ? "text-red-600" : "text-green-600"}`}
      >
        {totalOutages}
      </div>
      <p className="text-xs text-gray-500 mt-1">
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
                <span className="text-gray-600">{o.zone_id}</span>
                <span className="flex items-center gap-1">
                  <span className="text-gray-800 font-medium">
                    {o.active_outages}
                  </span>
                  {o.trend === "rising" && (
                    <span className="text-red-500">&#9650;</span>
                  )}
                  {o.trend === "falling" && (
                    <span className="text-green-500">&#9660;</span>
                  )}
                </span>
              </div>
            ))}
        </div>
      )}
    </div>
  );
}
