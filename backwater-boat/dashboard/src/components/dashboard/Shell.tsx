import { useMemo, useState } from "react";
import { useApiData } from "@/lib/useApiData";
import { riskClass } from "@/lib/maritime";
import Sidebar, { type TabId } from "./Sidebar";
import Topbar from "./Topbar";
import LiveMap from "./LiveMap";
import Collision from "./Collision";
import Analytics from "./Analytics";
import Logs from "./Logs";

export default function Shell() {
  const [active, setActive] = useState<TabId>("map");
  const data = useApiData();

  const center: [number, number] =
    Array.isArray(data.latest) && data.latest[0]
      ? [data.latest[0].lat, data.latest[0].lon]
      : [9.591, 76.522];

  const groupedPredictions = useMemo(() => {
    const out: Record<string, [number, number, number][]> = {};
    if (!Array.isArray(data.predictions)) return out;
    for (const p of data.predictions) {
      (out[p.boat_id] ||= []).push([p.pred_lat, p.pred_lon, p.confidence]);
    }
    return out;
  }, [data.predictions]);

  const dangerAlerts = useMemo(
    () => (Array.isArray(data.alerts) ? data.alerts.filter((a) => (a.severity || "").toLowerCase() === "danger").length : 0),
    [data.alerts],
  );

  // Surface global risk via a top "threat rail" color when in danger.
  const globalRisk = useMemo(() => {
    if (!Array.isArray(data.latest) || data.latest.length === 0) return 0;
    return data.latest.reduce((m, b) => Math.max(m, Number(b.risk || 0)), 0);
  }, [data.latest]);
  const globalLevel = riskClass(globalRisk);

  return (
    <div className="flex h-screen w-full bg-canvas text-zinc-300 font-sans overflow-hidden">
      <Sidebar
        active={active}
        onChange={setActive}
        dangerAlerts={dangerAlerts}
        fleetCount={Array.isArray(data.latest) ? data.latest.length : 0}
        alertCount={Array.isArray(data.alerts) ? data.alerts.length : 0}
        predCount={Array.isArray(data.predictions) ? data.predictions.length : 0}
      />

      <div className="flex-1 flex flex-col min-w-0">
        {/* Threat rail */}
        <div
          className={`h-0.5 w-full shrink-0 transition-colors ${
            globalLevel === "danger"
              ? "bg-danger animate-danger-pulse"
              : globalLevel === "warning"
              ? "bg-warning"
              : "bg-safe/40"
          }`}
        />
        <Topbar active={active} weather={data.weather} error={data.error} />

        <main className="flex-1 min-h-0 p-4 overflow-hidden">
          {active === "map" && (
            <LiveMap center={center} latest={data.latest} predictions={groupedPredictions} telemetry={data.telemetry} />
          )}
          {active === "collision" && (
            <Collision
              center={center}
              latest={data.latest}
              telemetry={data.telemetry}
              groupedPredictions={groupedPredictions}
              predictions={data.predictions}
              recommendations={data.recommendations}
            />
          )}
          {active === "analytics" && (
            <Analytics evaluation={data.evaluation} timeline={data.timeline} telemetry={data.telemetry} />
          )}
          {active === "logs" && <Logs alerts={data.alerts} telemetry={data.telemetry} />}
        </main>
      </div>
    </div>
  );
}
