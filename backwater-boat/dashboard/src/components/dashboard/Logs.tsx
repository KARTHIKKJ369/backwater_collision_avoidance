import { AlertTriangle, ShieldAlert, Info } from "lucide-react";
import { riskClass } from "@/lib/maritime";
import type { Alert, Boat } from "@/lib/maritime";

function fmtTime(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  const d = new Date(typeof v === "number" ? v : String(v));
  if (Number.isNaN(d.getTime())) return String(v);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export default function Logs({ alerts, telemetry }: { alerts: Alert[]; telemetry: Boat[] }) {
  const a = Array.isArray(alerts) ? alerts : [];
  const t = Array.isArray(telemetry) ? telemetry.slice(0, 40) : [];

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[1.2fr_1fr] grid-rows-[minmax(0,1fr)_minmax(0,1fr)] lg:grid-rows-1 gap-4 h-full min-h-0 overflow-hidden">
      <Panel title="System Alerts" count={a.length}>
        <div className="flex flex-col gap-2 overflow-y-auto pr-2 h-full">

          {a.length === 0 && (
            <div className="text-xs text-zinc-600 font-mono px-1 py-6 text-center">
              No alerts — all clear.
            </div>
          )}
          {a.map((al, idx) => {
            const sev = (al.severity || "").toLowerCase();
            const Icon = sev === "danger" ? ShieldAlert : sev === "warning" ? AlertTriangle : Info;
            const cls =
              sev === "danger"
                ? "border-danger/40 bg-danger/[0.06] text-danger"
                : sev === "warning"
                ? "border-warning/40 bg-warning/[0.06] text-warning"
                : "border-white/10 bg-white/[0.02] text-zinc-300";
            return (
              <article key={al.id ?? `al-${idx}`} className={`flex items-start gap-3 p-3 rounded-lg border ${cls}`}>
                <Icon className="size-4 mt-0.5 shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-3">
                    <strong className="text-xs uppercase tracking-wider">{al.severity || "EVENT"}</strong>
                    <span className="text-[10px] font-mono text-zinc-500 shrink-0">{fmtTime(al.timestamp)}</span>
                  </div>
                  <p className="text-xs text-zinc-400 mt-1 leading-relaxed break-words">
                    {al.message || `Vessel ${al.boat_id ?? "—"}`}
                  </p>
                </div>
              </article>
            );
          })}
        </div>
      </Panel>

      <Panel title="Recent Telemetry" count={t.length}>
        <div className="flex flex-col gap-1 font-mono text-[11px] overflow-y-auto pr-2 h-full">
          {t.map((r, i) => {
            const lvl = riskClass(r.risk || 0);
            return (
              <div key={i} className="flex items-center gap-3 py-1.5 border-b border-white/[0.04]">
                <span className="w-20 text-zinc-500 truncate">{fmtTime(r.timestamp)}</span>
                <span className="w-20 text-zinc-200 truncate">{r.boat_id}</span>
                <span className="flex-1 text-zinc-500">
                  {Number(r.speed).toFixed(2)}m/s · {Number(r.heading).toFixed(0)}°
                </span>
                <span className={lvl === "danger" ? "text-danger" : lvl === "warning" ? "text-warning" : "text-safe"}>
                  {Number(r.risk).toFixed(2)}
                </span>
              </div>
            );
          })}
          {t.length === 0 && <p className="text-zinc-600 py-6 text-center">No telemetry yet.</p>}
        </div>
      </Panel>
    </div>
  );
}

function Panel({ title, count, children }: { title: string; count: number; children: React.ReactNode }) {
  return (
    <div className="rounded-xl bg-panel/70 backdrop-blur-md border border-white/5 ring-1 ring-black/5 p-4 flex flex-col min-h-0">
      <div className="flex items-center justify-between mb-3 shrink-0">
        <h3 className="text-xs font-bold uppercase tracking-widest text-zinc-400">{title}</h3>
        <span className="text-[10px] font-mono text-zinc-500">{count}</span>
      </div>
      <div className="flex-1 min-h-0">{children}</div>
    </div>
  );
}