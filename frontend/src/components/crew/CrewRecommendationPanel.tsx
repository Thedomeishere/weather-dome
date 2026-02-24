import type { CrewRecommendation } from "../../api/types";

interface Props {
  crews: CrewRecommendation[];
}

export default function CrewRecommendationPanel({ crews }: Props) {
  const totalLine = crews.reduce((s, c) => s + c.line_crews, 0);
  const totalTree = crews.reduce((s, c) => s + c.tree_crews, 0);
  const totalService = crews.reduce((s, c) => s + c.service_crews, 0);
  const totalAll = crews.reduce((s, c) => s + c.total_crews, 0);
  const anyMutualAid = crews.some((c) => c.mutual_aid_needed);
  const anyPreStage = crews.some((c) => c.pre_stage);

  return (
    <div className="bg-white rounded-lg shadow p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-700">
          Crew Deployment Recommendations
        </h3>
        <div className="flex gap-2">
          {anyMutualAid && (
            <span className="text-xs bg-red-100 text-red-700 px-2 py-1 rounded font-medium">
              Mutual Aid Needed
            </span>
          )}
          {anyPreStage && (
            <span className="text-xs bg-yellow-100 text-yellow-700 px-2 py-1 rounded font-medium">
              Pre-Stage
            </span>
          )}
        </div>
      </div>

      {/* Summary row */}
      <div className="grid grid-cols-4 gap-3 mb-4 text-center">
        <div className="bg-blue-50 rounded p-2">
          <div className="text-xs text-gray-500">Line Crews</div>
          <div className="text-lg font-bold text-blue-700">{totalLine}</div>
        </div>
        <div className="bg-green-50 rounded p-2">
          <div className="text-xs text-gray-500">Tree Crews</div>
          <div className="text-lg font-bold text-green-700">{totalTree}</div>
        </div>
        <div className="bg-purple-50 rounded p-2">
          <div className="text-xs text-gray-500">Service Crews</div>
          <div className="text-lg font-bold text-purple-700">{totalService}</div>
        </div>
        <div className="bg-gray-50 rounded p-2">
          <div className="text-xs text-gray-500">Total</div>
          <div className="text-lg font-bold text-gray-700">{totalAll}</div>
        </div>
      </div>

      {/* Per-zone table */}
      {crews.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-gray-500 border-b">
                <th className="pb-2">Zone</th>
                <th className="pb-2 text-center">Line</th>
                <th className="pb-2 text-center">Tree</th>
                <th className="pb-2 text-center">Service</th>
                <th className="pb-2 text-center">Total</th>
                <th className="pb-2">Flags</th>
              </tr>
            </thead>
            <tbody>
              {crews.map((c) => (
                <tr key={c.zone_id} className="border-b border-gray-50">
                  <td className="py-2 font-medium">{c.zone_id}</td>
                  <td className="py-2 text-center">{c.line_crews}</td>
                  <td className="py-2 text-center">{c.tree_crews}</td>
                  <td className="py-2 text-center">{c.service_crews}</td>
                  <td className="py-2 text-center font-medium">{c.total_crews}</td>
                  <td className="py-2">
                    <div className="flex gap-1">
                      {c.mutual_aid_needed && (
                        <span className="text-xs bg-red-100 text-red-600 px-1.5 py-0.5 rounded">
                          MA
                        </span>
                      )}
                      {c.pre_stage && (
                        <span className="text-xs bg-yellow-100 text-yellow-600 px-1.5 py-0.5 rounded">
                          PS
                        </span>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {crews.length === 0 && (
        <p className="text-gray-400 text-sm text-center py-4">
          No crew recommendations available yet.
        </p>
      )}
    </div>
  );
}
