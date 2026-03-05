import { ForecastPoint } from "../../api/types";

interface DaySummary {
  dayName: string;
  date: string;
  highTemp: number | null;
  lowTemp: number | null;
  maxWind: number | null;
  precipProb: number | null;
  condition: string | null;
}

function groupByDay(points: ForecastPoint[]): DaySummary[] {
  const dayMap = new Map<string, ForecastPoint[]>();

  for (const pt of points) {
    const date = new Date(pt.forecast_for);
    const key = date.toISOString().slice(0, 10);
    if (!dayMap.has(key)) dayMap.set(key, []);
    dayMap.get(key)!.push(pt);
  }

  const days: DaySummary[] = [];
  for (const [dateKey, pts] of dayMap) {
    const date = new Date(dateKey + "T12:00:00");
    const temps = pts.map((p) => p.temperature_f).filter((t): t is number => t !== null);
    const winds = pts.map((p) => p.wind_speed_mph).filter((w): w is number => w !== null);
    const precips = pts.map((p) => p.precip_probability_pct).filter((p): p is number => p !== null);

    // Use midday condition (noon-ish), fallback to first available
    const middayPt = pts.find((p) => {
      const h = new Date(p.forecast_for).getHours();
      return h >= 11 && h <= 14;
    });
    const condition = middayPt?.condition_text ?? pts.find((p) => p.condition_text)?.condition_text ?? null;

    days.push({
      dayName: date.toLocaleDateString("en-US", { weekday: "short" }),
      date: date.toLocaleDateString("en-US", { month: "short", day: "numeric" }),
      highTemp: temps.length > 0 ? Math.round(Math.max(...temps)) : null,
      lowTemp: temps.length > 0 ? Math.round(Math.min(...temps)) : null,
      maxWind: winds.length > 0 ? Math.round(Math.max(...winds)) : null,
      precipProb: precips.length > 0 ? Math.round(Math.max(...precips)) : null,
      condition,
    });
  }

  return days.slice(0, 5);
}

function weatherIcon(condition: string | null): string {
  if (!condition) return "\u2601\uFE0F";
  const c = condition.toLowerCase();
  if (c.includes("snow") || c.includes("blizzard")) return "\u2744\uFE0F";
  if (c.includes("rain") || c.includes("shower") || c.includes("drizzle")) return "\uD83C\uDF27\uFE0F";
  if (c.includes("thunder") || c.includes("storm")) return "\u26C8\uFE0F";
  if (c.includes("cloud") || c.includes("overcast")) return "\u2601\uFE0F";
  if (c.includes("fog") || c.includes("mist") || c.includes("haze")) return "\uD83C\uDF2B\uFE0F";
  if (c.includes("clear") || c.includes("sunny") || c.includes("fair")) return "\u2600\uFE0F";
  if (c.includes("partly") || c.includes("mostly sunny")) return "\u26C5";
  if (c.includes("wind")) return "\uD83D\uDCA8";
  if (c.includes("ice") || c.includes("freezing") || c.includes("sleet")) return "\uD83E\uDDCA";
  return "\u2601\uFE0F";
}

export default function FiveDayForecast({ points }: { points: ForecastPoint[] }) {
  if (!points || points.length === 0) return null;

  const days = groupByDay(points);
  if (days.length === 0) return null;

  return (
    <div className="mb-6">
      <h2 className="text-lg font-semibold text-slate-200 mb-3">5-Day Forecast</h2>
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-4">
        {days.map((day, i) => (
          <div
            key={day.date}
            className="bg-slate-800/80 border border-slate-700/50 rounded-lg shadow-lg shadow-black/20 p-4 text-center hover:border-slate-600 transition-colors animate-fade-in-up"
            style={{ animationDelay: `${i * 60}ms` }}
          >
            <div className="text-sm font-semibold text-slate-300">{day.dayName}</div>
            <div className="text-xs text-slate-500 mb-2">{day.date}</div>
            <div className="text-3xl mb-2">{weatherIcon(day.condition)}</div>
            <div className="text-xs text-slate-400 mb-2 h-8 flex items-center justify-center">
              {day.condition ?? "N/A"}
            </div>
            <div className="text-lg font-bold text-slate-200">
              {day.highTemp !== null ? `${day.highTemp}\u00B0` : "--"}
              <span className="text-sm font-normal text-slate-500 ml-1">
                {day.lowTemp !== null ? `${day.lowTemp}\u00B0` : "--"}
              </span>
            </div>
            <div className="mt-2 flex justify-center gap-3 text-xs text-slate-400">
              {day.maxWind !== null && (
                <span title="Max wind speed">{day.maxWind} mph</span>
              )}
              {day.precipProb !== null && (
                <span title="Precipitation probability">{day.precipProb}%</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
