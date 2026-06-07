import { useEffect, useState } from "react";

const API_BASE =
  (import.meta.env.VITE_API_BASE as string | undefined) || "http://localhost:8000";

// ─── Types ───────────────────────────────────────────────────────────────────

interface ScenarioDef {
  id: string;
  label: string;
  description: string;
  duration: number;
  boats: string[];
}

interface SimStatus {
  running: boolean;
  scenario: string | null;
  tick: number;
  duration?: number;
}

// ─── Scenario icon SVGs ───────────────────────────────────────────────────────

const ScenarioIcon = ({ id }: { id: string }) => {
  const cls = "w-full h-full";
  if (id === "HEAD_ON")
    return (
      <svg viewBox="0 0 48 24" className={cls}>
        <polygon points="4,12 14,7 14,17" fill="currentColor" opacity=".9" />
        <polygon points="44,12 34,7 34,17" fill="currentColor" opacity=".9" />
        <line x1="15" y1="12" x2="33" y2="12" stroke="currentColor" strokeWidth="1.5" strokeDasharray="3 2" opacity=".5" />
      </svg>
    );
  if (id === "CROSSING")
    return (
      <svg viewBox="0 0 48 48" className={cls}>
        <polygon points="4,24 14,19 14,29" fill="currentColor" opacity=".9" />
        <polygon points="24,44 19,34 29,34" fill="currentColor" opacity=".9" />
        <line x1="15" y1="24" x2="24" y2="33" stroke="currentColor" strokeWidth="1.5" strokeDasharray="3 2" opacity=".5" />
      </svg>
    );
  if (id === "BLIND_TURN")
    return (
      <svg viewBox="0 0 48 48" className={cls}>
        <path d="M8 40 Q8 8 40 8" stroke="currentColor" strokeWidth="2" fill="none" opacity=".35" />
        <polygon points="8,40 3,30 13,30" fill="currentColor" opacity=".9" />
        <polygon points="40,8 30,3 30,13" fill="currentColor" opacity=".9" />
      </svg>
    );
  // SUDDEN_STOP
  return (
    <svg viewBox="0 0 48 24" className={cls}>
      <polygon points="4,12 14,7 14,17" fill="currentColor" opacity=".9" />
      <polygon points="30,12 20,7 20,17" fill="currentColor" opacity=".9" />
      <rect x="34" y="6" width="10" height="12" rx="2" fill="currentColor" opacity=".7" />
      <line x1="15" y1="12" x2="19" y2="12" stroke="currentColor" strokeWidth="1.5" strokeDasharray="3 2" opacity=".5" />
    </svg>
  );
};

// ─── Progress bar ─────────────────────────────────────────────────────────────

function ProgressBar({ tick, duration }: { tick: number; duration: number }) {
  const pct = Math.min(100, Math.round((tick / Math.max(1, duration)) * 100));
  return (
    <div className="mt-3 space-y-1">
      <div className="flex justify-between text-[10px] font-mono text-zinc-500">
        <span>tick {tick}</span>
        <span>{pct}%</span>
      </div>
      <div className="h-1 w-full rounded-full bg-white/5 overflow-hidden">
        <div
          className="h-full rounded-full bg-cyan transition-all duration-700"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

// ─── Risk badge hints ─────────────────────────────────────────────────────────

const RISK_HINTS: Record<string, { label: string; color: string }> = {
  HEAD_ON:     { label: "DANGER",  color: "text-red-400 bg-red-500/10 border-red-500/20" },
  CROSSING:    { label: "WARNING", color: "text-yellow-400 bg-yellow-500/10 border-yellow-500/20" },
  BLIND_TURN:  { label: "WARNING", color: "text-yellow-400 bg-yellow-500/10 border-yellow-500/20" },
  SUDDEN_STOP: { label: "DANGER",  color: "text-red-400 bg-red-500/10 border-red-500/20" },
};

// ─── Main component ───────────────────────────────────────────────────────────

export default function ScenarioSelector() {
  const [scenarios, setScenarios] = useState<ScenarioDef[]>([]);
  const [status, setStatus] = useState<SimStatus>({ running: false, scenario: null, tick: 0 });
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Fetch scenario list once on mount
  useEffect(() => {
    fetch(`${API_BASE}/scenarios`)
      .then((r) => r.json())
      .then(setScenarios)
      .catch(() => setError("Could not reach backend — is it running?"));
  }, []);

  // Poll status at 1 Hz (faster when running to keep progress bar smooth)
  useEffect(() => {
    const poll = () =>
      fetch(`${API_BASE}/scenarios/status`)
        .then((r) => r.json())
        .then(setStatus)
        .catch(() => {});
    poll();
    const id = setInterval(poll, 1000);
    return () => clearInterval(id);
  }, []);

  const handleRun = async (id: string) => {
    setLoading(id);
    setError(null);
    try {
      await fetch(`${API_BASE}/scenarios/${id}/run`, { method: "POST" });
    } catch {
      setError("Failed to start scenario.");
    } finally {
      setLoading(null);
    }
  };

  const handleStop = async () => {
    setLoading("STOP");
    try {
      await fetch(`${API_BASE}/scenarios/stop`, { method: "POST" });
      setStatus({ running: false, scenario: null, tick: 0 });
    } finally {
      setLoading(null);
    }
  };

  return (
    <div className="h-full overflow-y-auto px-1 py-2 space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-sm font-semibold text-zinc-100 tracking-tight">Demo Scenarios</h2>
          <p className="text-[11px] text-zinc-500 mt-0.5">
            Start a built-in simulation. The backend publishes sensor data via MQTT so every tab
            updates live — no simulator container needed.
          </p>
        </div>
        {status.running && (
          <button
            onClick={handleStop}
            disabled={loading === "STOP"}
            className="shrink-0 text-[11px] font-semibold px-3 py-1.5 rounded-md border border-white/10 text-zinc-300 hover:bg-white/5 transition disabled:opacity-50"
          >
            {loading === "STOP" ? "Stopping…" : "■ Stop"}
          </button>
        )}
      </div>

      {error && (
        <div className="text-[11px] text-red-400 bg-red-500/10 border border-red-500/20 rounded-md px-3 py-2">
          {error}
        </div>
      )}

      {/* Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {(scenarios.length
          ? scenarios
          : (["HEAD_ON", "CROSSING", "BLIND_TURN", "SUDDEN_STOP"] as const).map((id) => ({
              id,
              label: id.replace("_", " "),
              description: "…",
              duration: 60,
              boats: ["B01", "B02"],
            }))
        ).map((sc) => {
          const isActive = status.running && status.scenario === sc.id;
          const hint = RISK_HINTS[sc.id];

          return (
            <div
              key={sc.id}
              className={`relative rounded-xl border p-4 flex flex-col gap-3 transition-all ${
                isActive
                  ? "border-cyan/40 bg-cyan/[0.04] shadow-[0_0_20px_rgba(6,182,212,0.08)]"
                  : "border-white/[0.06] bg-white/[0.02] hover:bg-white/[0.035]"
              }`}
            >
              {/* Active pulse dot */}
              {isActive && (
                <span className="absolute top-3 right-3 flex items-center gap-1.5 text-[10px] font-mono text-cyan">
                  <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan opacity-75" />
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan" />
                  </span>
                  LIVE
                </span>
              )}

              {/* Icon + title row */}
              <div className="flex items-center gap-3">
                <div
                  className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0 p-2 ${
                    isActive ? "text-cyan bg-cyan/10" : "text-zinc-400 bg-white/[0.04]"
                  }`}
                >
                  <ScenarioIcon id={sc.id} />
                </div>
                <div className="min-w-0">
                  <div className="text-[13px] font-semibold text-zinc-100 leading-tight">{sc.label}</div>
                  <div className="flex items-center gap-1.5 mt-0.5">
                    <span className="text-[10px] font-mono text-zinc-600">{sc.duration}s</span>
                    <span className="text-zinc-700">·</span>
                    <span className="text-[10px] font-mono text-zinc-600">{sc.boats.join(", ")}</span>
                    {hint && (
                      <>
                        <span className="text-zinc-700">·</span>
                        <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded border ${hint.color}`}>
                          {hint.label}
                        </span>
                      </>
                    )}
                  </div>
                </div>
              </div>

              {/* Description */}
              <p className="text-[11px] text-zinc-500 leading-relaxed">{sc.description}</p>

              {/* Progress bar when active */}
              {isActive && status.duration != null && (
                <ProgressBar tick={status.tick} duration={status.duration} />
              )}

              {/* Run button */}
              <button
                onClick={() => handleRun(sc.id)}
                disabled={loading === sc.id}
                className={`mt-auto text-[12px] font-semibold py-2 rounded-lg transition ${
                  isActive
                    ? "bg-cyan/15 text-cyan border border-cyan/20 hover:bg-cyan/20"
                    : "bg-white/[0.05] text-zinc-300 border border-white/[0.08] hover:bg-white/[0.08] hover:text-white"
                } disabled:opacity-50 disabled:cursor-wait`}
              >
                {loading === sc.id ? "Starting…" : isActive ? "↺ Restart" : "▶ Run"}
              </button>
            </div>
          );
        })}
      </div>

      {/* Footer note */}
      <p className="text-[10px] text-zinc-600 text-center pb-2">
        Scenarios publish to MQTT at 1 Hz and stop automatically when the time limit is reached.
        Switch to the Map or Collision tab to watch the boats in real time.
      </p>
    </div>
  );
}