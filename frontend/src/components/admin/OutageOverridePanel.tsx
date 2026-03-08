import { useState } from "react";
import type { ZoneOutageStatus } from "../../api/types";
import { useOutageOverrides, useSetOverride, useClearOverride } from "../../hooks/useWeatherData";

interface Props {
  outageStatus: ZoneOutageStatus[];
  territory: string;
}

const CONED_ZONES = ["MAN", "BRX", "BKN", "QNS", "SI", "WST"];
const OR_ZONES = ["ORA", "ROC", "SUL", "BER", "SSX"];

const TTL_OPTIONS = [
  { label: "30m", value: 30 },
  { label: "1h", value: 60 },
  { label: "2h", value: 120 },
  { label: "4h", value: 240 },
  { label: "8h", value: 480 },
];

interface RowState {
  outages: string;
  customers: string;
  ttl: number;
}

export default function OutageOverridePanel({ outageStatus, territory }: Props) {
  const zones = territory === "CONED" ? CONED_ZONES : OR_ZONES;
  const { data: overrides } = useOutageOverrides();
  const setOverride = useSetOverride();
  const clearOverride = useClearOverride();

  const [rowState, setRowState] = useState<Record<string, RowState>>({});
  const [feedback, setFeedback] = useState<{ zone: string; msg: string; ok: boolean } | null>(null);

  const getRow = (zone: string): RowState =>
    rowState[zone] ?? { outages: "", customers: "", ttl: 120 };

  const updateRow = (zone: string, patch: Partial<RowState>) => {
    setRowState((prev) => ({ ...prev, [zone]: { ...getRow(zone), ...patch } }));
  };

  const overrideMap = new Map(
    (overrides ?? []).map((o) => [o.zone_id, o])
  );

  const activeCount = zones.filter((z) => overrideMap.has(z)).length;

  const handleApply = async (zone: string) => {
    const row = getRow(zone);
    const outages = parseInt(row.outages, 10);
    const customers = parseInt(row.customers, 10);
    if (isNaN(outages) || isNaN(customers) || outages < 0 || customers < 0) {
      setFeedback({ zone, msg: "Enter valid numbers", ok: false });
      setTimeout(() => setFeedback(null), 2000);
      return;
    }
    try {
      await setOverride.mutateAsync({
        zone_id: zone,
        active_outages: outages,
        customers_affected: customers,
        ttl_minutes: row.ttl,
      });
      setFeedback({ zone, msg: "Applied", ok: true });
      setRowState((prev) => {
        const next = { ...prev };
        delete next[zone];
        return next;
      });
    } catch {
      setFeedback({ zone, msg: "Failed", ok: false });
    }
    setTimeout(() => setFeedback(null), 2000);
  };

  const handleClear = async (zone: string) => {
    try {
      await clearOverride.mutateAsync(zone);
      setFeedback({ zone, msg: "Cleared", ok: true });
    } catch {
      setFeedback({ zone, msg: "Failed", ok: false });
    }
    setTimeout(() => setFeedback(null), 2000);
  };

  const statusMap = new Map(outageStatus.map((s) => [s.zone_id, s]));

  return (
    <div className="bg-slate-800/80 border border-slate-700/50 rounded-lg shadow-lg shadow-black/20 p-5 mb-6 animate-fade-in-up">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-slate-200">
          Outage Overrides
        </h2>
        {activeCount > 0 && (
          <span className="bg-amber-600/20 text-amber-400 text-xs font-medium px-2.5 py-1 rounded-full border border-amber-600/30">
            {activeCount} active
          </span>
        )}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-slate-400 text-left border-b border-slate-700/50">
              <th className="pb-2 pr-4 font-medium">Zone</th>
              <th className="pb-2 pr-4 font-medium">Current</th>
              <th className="pb-2 pr-4 font-medium">Override</th>
              <th className="pb-2 pr-4 font-medium">TTL</th>
              <th className="pb-2 font-medium">Action</th>
            </tr>
          </thead>
          <tbody>
            {zones.map((zone) => {
              const status = statusMap.get(zone);
              const override = overrideMap.get(zone);
              const row = getRow(zone);
              const fb = feedback?.zone === zone ? feedback : null;

              return (
                <tr
                  key={zone}
                  className="border-b border-slate-700/30 hover:bg-slate-700/20"
                >
                  <td className="py-2.5 pr-4">
                    <span className="font-mono font-medium text-slate-200">
                      {zone}
                    </span>
                    {override && (
                      <span className="ml-1.5 text-amber-400 text-xs" title="Override active">
                        *
                      </span>
                    )}
                  </td>
                  <td className="py-2.5 pr-4 text-slate-300 tabular-nums">
                    {status
                      ? `${status.active_outages} / ${status.customers_affected.toLocaleString()}`
                      : "— / —"}
                  </td>
                  <td className="py-2.5 pr-4">
                    <div className="flex items-center gap-1.5">
                      <input
                        type="number"
                        min="0"
                        placeholder="outages"
                        value={row.outages}
                        onChange={(e) => updateRow(zone, { outages: e.target.value })}
                        className="w-20 bg-slate-900 border border-slate-600 rounded px-2 py-1 text-sm text-slate-200 placeholder-slate-500 focus:border-blue-500 focus:outline-none"
                      />
                      <span className="text-slate-500">/</span>
                      <input
                        type="number"
                        min="0"
                        placeholder="customers"
                        value={row.customers}
                        onChange={(e) => updateRow(zone, { customers: e.target.value })}
                        className="w-24 bg-slate-900 border border-slate-600 rounded px-2 py-1 text-sm text-slate-200 placeholder-slate-500 focus:border-blue-500 focus:outline-none"
                      />
                    </div>
                  </td>
                  <td className="py-2.5 pr-4">
                    <select
                      value={row.ttl}
                      onChange={(e) => updateRow(zone, { ttl: Number(e.target.value) })}
                      className="bg-slate-900 border border-slate-600 rounded px-2 py-1 text-sm text-slate-200 focus:border-blue-500 focus:outline-none"
                    >
                      {TTL_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="py-2.5">
                    <div className="flex items-center gap-2">
                      {override ? (
                        <button
                          onClick={() => handleClear(zone)}
                          disabled={clearOverride.isPending}
                          className="px-3 py-1 text-xs font-medium rounded bg-red-600/20 text-red-400 border border-red-600/30 hover:bg-red-600/30 transition-colors disabled:opacity-50"
                        >
                          Clear
                        </button>
                      ) : null}
                      <button
                        onClick={() => handleApply(zone)}
                        disabled={setOverride.isPending}
                        className="px-3 py-1 text-xs font-medium rounded bg-blue-600/20 text-blue-400 border border-blue-600/30 hover:bg-blue-600/30 transition-colors disabled:opacity-50"
                      >
                        Apply
                      </button>
                      {fb && (
                        <span
                          className={`text-xs ${fb.ok ? "text-emerald-400" : "text-red-400"}`}
                        >
                          {fb.msg}
                        </span>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Active override details */}
      {(overrides ?? []).filter((o) => zones.includes(o.zone_id)).length > 0 && (
        <div className="mt-3 pt-3 border-t border-slate-700/30">
          <div className="flex flex-wrap gap-2">
            {(overrides ?? [])
              .filter((o) => zones.includes(o.zone_id))
              .map((o) => (
                <span
                  key={o.zone_id}
                  className="inline-flex items-center gap-1.5 bg-amber-600/10 text-amber-400 text-xs px-2.5 py-1 rounded-full border border-amber-600/20"
                >
                  <span className="font-mono font-medium">{o.zone_id}</span>
                  <span className="text-amber-400/60">
                    {o.active_outages}/{o.customers_affected}
                  </span>
                  <span className="text-amber-400/40">
                    exp {new Date(o.expires_at).toLocaleTimeString()}
                  </span>
                </span>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}
