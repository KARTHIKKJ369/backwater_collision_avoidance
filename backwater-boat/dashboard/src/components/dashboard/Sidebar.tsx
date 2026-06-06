import { Activity, AlertTriangle, Anchor, Clock, Map as MapIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export type TabId = "map" | "collision" | "analytics" | "logs";

const tabs: { id: TabId; label: string; icon: typeof MapIcon }[] = [
  { id: "map", label: "Live Map", icon: MapIcon },
  { id: "collision", label: "Collision", icon: AlertTriangle },
  { id: "analytics", label: "Analytics", icon: Activity },
  { id: "logs", label: "Logs", icon: Clock },
];

type Props = {
  active: TabId;
  onChange: (t: TabId) => void;
  dangerAlerts: number;
  fleetCount: number;
  alertCount: number;
  predCount: number;
};

export default function Sidebar({ active, onChange, dangerAlerts, fleetCount, alertCount, predCount }: Props) {
  return (
    <nav className="w-16 lg:w-20 flex flex-col items-center py-5 border-r border-white/5 bg-panel/60 backdrop-blur-xl z-50 shrink-0">
      <div className="size-10 rounded-md bg-cyan/15 ring-1 ring-cyan/30 flex items-center justify-center mb-10 shadow-[0_0_20px_rgba(6,182,212,0.25)]">
        <Anchor className="size-5 text-cyan" />
      </div>

      <div className="flex flex-col gap-2 w-full px-2">
        {tabs.map((t) => {
          const Icon = t.icon;
          const isActive = active === t.id;
          const showBadge = t.id === "collision" && dangerAlerts > 0;
          return (
            <button
              key={t.id}
              onClick={() => onChange(t.id)}
              title={t.label}
              className={cn(
                "group relative h-12 rounded-md flex flex-col items-center justify-center gap-0.5 transition-all",
                isActive
                  ? "bg-white/[0.04] text-cyan ring-1 ring-cyan/20"
                  : "text-zinc-500 hover:text-zinc-200 hover:bg-white/[0.03]",
              )}
            >
              {isActive && (
                <span className="absolute left-0 top-2 bottom-2 w-0.5 rounded-r bg-cyan shadow-[0_0_8px_var(--color-cyan)]" />
              )}
              <Icon className="size-[18px] shrink-0" />
              <span className="text-[9px] font-medium uppercase tracking-wider hidden lg:block">{t.label}</span>
              {showBadge && (
                <span className="absolute top-1.5 right-2 min-w-4 h-4 px-1 rounded-full bg-danger text-[9px] font-bold text-zinc-50 flex items-center justify-center ring-2 ring-panel">
                  {dangerAlerts}
                </span>
              )}
            </button>
          );
        })}
      </div>

      <div className="mt-auto w-full px-2 space-y-1 hidden lg:block font-mono text-[10px]">
        <Stat label="FLT" value={fleetCount} />
        <Stat label="ALT" value={alertCount} />
        <Stat label="PRD" value={predCount} />
      </div>
    </nav>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center justify-between px-2 py-1.5 rounded bg-white/[0.02] border border-white/[0.04]">
      <span className="text-zinc-600">{label}</span>
      <span className="text-zinc-200">{value}</span>
    </div>
  );
}
