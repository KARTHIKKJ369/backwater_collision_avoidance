import { formatPercent, formatValue, riskClass } from "@/lib/maritime";
import type { Boat } from "@/lib/maritime";

type Props = {
  evaluation: Record<string, unknown>;
  timeline: { t?: string; risk?: number; alert?: string }[];
  telemetry: Boat[];
};

export default function Analytics({ evaluation, timeline, telemetry }: Props) {
  const cards: [string, string | number][] = [
    ["Alerts Sent", Number(evaluation.alerts || 0)],
    ["Predictions", Number(evaluation.predictions || 0)],
    ["Collisions", Number(evaluation.collisions || 0)],
    ["Precision", formatPercent(evaluation.precision)],
    ["Latency", `${Number(evaluation.latency || 0)} ms`],
  ];
  const tl = Array.isArray(timeline) ? timeline : [];
  const tel = Array.isArray(telemetry) ? telemetry : [];

  return (
    <div className="flex flex-col gap-4 h-full overflow-y-auto pb-4">
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {cards.map(([label, value]) => (
          <div key={label} className="rounded-xl bg-panel/70 backdrop-blur-md border border-white/5 ring-1 ring-black/5 p-4">
            <div className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">{label}</div>
            <div className="mt-2 text-2xl font-mono text-cyan tabular-nums">{value}</div>
          </div>
        ))}
      </div>

      <Panel title="Collision Timeline">
        <div className="flex flex-col gap-1.5 max-h-[320px] overflow-y-auto pr-2">
          {tl.slice(-80).map((p, i) => {
            const lvl = riskClass(p.risk || 0);
            return (
              <div key={`${p.t}-${i}`} className="flex items-center gap-3 text-xs">
                <span className="w-20 font-mono text-zinc-500 truncate">{formatValue(p.t)}</span>
                <div className="flex-1 h-1.5 rounded-full bg-white/[0.04] overflow-hidden border border-white/[0.04]">
                  <div
                    className={`h-full ${lvl === "danger" ? "bg-danger" : lvl === "warning" ? "bg-warning" : "bg-safe"}`}
                    style={{ width: `${Math.max(4, Math.min(100, Number(p.risk || 0) * 100))}%` }}
                  />
                </div>
                <strong className={`w-24 text-right text-[10px] font-mono uppercase ${lvl === "danger" ? "text-danger" : lvl === "warning" ? "text-warning" : "text-safe"}`}>
                  {p.alert || "SAFE"}
                </strong>
              </div>
            );
          })}
          {tl.length === 0 && <p className="text-xs text-zinc-600 font-mono">No timeline data yet.</p>}
        </div>
      </Panel>

      <Panel title="Live Telemetry">
        <div className="overflow-x-auto -mx-4">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-[10px] uppercase tracking-wider text-zinc-500 border-b border-white/5">
                {["Boat", "Time", "Lat", "Lon", "Speed", "Heading", "Risk"].map((h) => (
                  <th key={h} className="text-left font-semibold px-4 py-2.5">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="font-mono">
              {tel.slice(0, 60).map((r, i) => {
                const lvl = riskClass(r.risk || 0);
                return (
                  <tr key={i} className="border-b border-white/[0.04] hover:bg-white/[0.02]">
                    <td className="px-4 py-2 text-zinc-200">{r.boat_id}</td>
                    <td className="px-4 py-2 text-zinc-500">{formatValue(r.timestamp)}</td>
                    <td className="px-4 py-2 text-zinc-400">{Number(r.lat).toFixed(5)}</td>
                    <td className="px-4 py-2 text-zinc-400">{Number(r.lon).toFixed(5)}</td>
                    <td className="px-4 py-2 text-zinc-200">{Number(r.speed).toFixed(2)}</td>
                    <td className="px-4 py-2 text-zinc-200">{Number(r.heading).toFixed(0)}°</td>
                    <td className={`px-4 py-2 ${lvl === "danger" ? "text-danger" : lvl === "warning" ? "text-warning" : "text-safe"}`}>
                      {Number(r.risk).toFixed(3)}
                    </td>
                  </tr>
                );
              })}
              {tel.length === 0 && (
                <tr><td colSpan={7} className="px-4 py-6 text-center text-zinc-600">No telemetry rows.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl bg-panel/70 backdrop-blur-md border border-white/5 ring-1 ring-black/5 p-4">
      <h3 className="text-xs font-bold uppercase tracking-widest text-zinc-400 mb-3">{title}</h3>
      {children}
    </div>
  );
}
