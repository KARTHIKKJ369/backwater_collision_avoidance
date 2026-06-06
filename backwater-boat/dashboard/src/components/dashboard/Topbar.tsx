import { useEffect, useState } from "react";
import { Cloud, CloudFog, CloudLightning, CloudRain, Eye, Sun, Wind } from "lucide-react";
import type { Weather } from "@/lib/maritime";
import type { TabId } from "./Sidebar";

const TITLES: Record<TabId, string> = {
  map: "Live Map / Backwater Sector",
  collision: "Collision Risk Console",
  analytics: "Analytics / Evaluation",
  logs: "Event Log",
};

export default function Topbar({
  active,
  weather,
  error,
}: {
  active: TabId;
  weather: Weather | null;
  error: string;
}) {
  return (
    <header className="h-14 border-b border-white/5 bg-panel/30 backdrop-blur-md flex items-center justify-between px-6 z-40 shrink-0">
      <div className="flex items-center gap-6 min-w-0">
        <h1 className="text-sm font-medium tracking-tight text-zinc-100 uppercase truncate">
          {TITLES[active]}
        </h1>
        <div className="h-4 w-px bg-white/10 hidden md:block" />
        <div className="hidden md:flex items-center gap-4 text-[11px] font-mono tracking-wider">
          <span
            className={`flex items-center gap-1.5 ${error ? "text-danger" : "text-safe"}`}
          >
            <span
              className={`size-1.5 rounded-full ${error ? "bg-danger" : "bg-safe animate-pulse"}`}
            />
            {error ? "OFFLINE" : "SYSTEM LIVE"}
          </span>
          <WeatherInline weather={weather} />
        </div>
      </div>
      <div className="flex items-center gap-3">
        <ClockBadge />
      </div>
    </header>
  );
}

function ClockBadge() {
  const [t, setT] = useState<Date | null>(null);
  useEffect(() => {
    setT(new Date());
    const i = setInterval(() => setT(new Date()), 1000);
    return () => clearInterval(i);
  }, []);
  return (
    <div className="bg-white/[0.04] px-3 py-1 rounded ring-1 ring-white/5">
      <span className="text-xs font-mono text-zinc-100 tabular-nums">
        {t ? t.toLocaleTimeString() : "--:--:--"}
      </span>
    </div>
  );
}

function WeatherInline({ weather }: { weather: Weather | null }) {
  if (!weather) return <span className="text-zinc-600">WX: —</span>;
  let Icon = Sun;
  const id = weather.condition_id || 800;
  if (id >= 200 && id < 300) Icon = CloudLightning;
  else if (id >= 300 && id < 600) Icon = CloudRain;
  else if (id >= 700 && id < 800) Icon = CloudFog;
  else if (id > 800) Icon = Cloud;
  return (
    <span className="flex items-center gap-3 text-zinc-500">
      <span className="flex items-center gap-1.5 text-zinc-300">
        <Icon className="size-3.5 text-cyan" />
        <span className="capitalize">{weather.description}</span>
      </span>
      <span className="flex items-center gap-1"><Wind className="size-3" /> {weather.wind_speed?.toFixed?.(1) ?? "—"} m/s</span>
      <span className="flex items-center gap-1"><Eye className="size-3" /> {(weather.visibility_m / 1000).toFixed(1)} km</span>
    </span>
  );
}
