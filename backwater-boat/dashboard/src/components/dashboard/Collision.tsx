import { Fragment, useMemo, useState } from "react";
import { MapContainer, TileLayer, Marker, Polyline, Circle } from "react-leaflet";
import type { LatLngExpression } from "leaflet";
import L from "leaflet";
import {
  averageConfidence,
  futureSeparation,
  groupPath,
  haversine,
  recommendationTone,
  riskClass,
  type Boat,
  type Prediction,
  type Recommendation,
  type RiskLevel,
} from "@/lib/maritime";

const BOAT_COLORS = ["#06b6d4", "#a78bfa", "#fbbf24", "#34d399"];

function makeIcon(heading: number, level: RiskLevel) {
  const colors: Record<RiskLevel, string> = { safe: "#10b981", warning: "#f59e0b", danger: "#ef4444" };
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 32 32" style="transform:rotate(${heading}deg);"><polygon points="16,2 26,28 16,22 6,28" fill="${colors[level]}" stroke="#09090b" stroke-width="2" stroke-linejoin="miter"/></svg>`;
  return new L.DivIcon({ className: "", html: svg, iconSize: [28, 28], iconAnchor: [14, 14] });
}

type Props = {
  center: [number, number];
  latest: Boat[];
  telemetry: Boat[];
  groupedPredictions: Record<string, [number, number, number][]>;
  predictions: Prediction[];
  recommendations: Recommendation[];
};

export default function Collision({
  center,
  latest,
  telemetry,
  groupedPredictions,
  predictions,
  recommendations,
}: Props) {
  const safe = Array.isArray(latest) ? latest : [];
  const [boatA, boatB] = safe;
  const actualPaths = useMemo(() => groupPath(telemetry, "lat", "lon"), [telemetry]);

  const distance = useMemo(
    () => (boatA && boatB ? haversine(boatA.lat, boatA.lon, boatB.lat, boatB.lon) : 0),
    [boatA, boatB],
  );

  // Compute closing speed: component of relative velocity along the line of sight.
  // Uses each boat's actual heading to project its velocity toward the other.
  const { closingSpeed, ttc } = useMemo(() => {
    if (!boatA || !boatB || !distance) return { closingSpeed: 0, ttc: null as number | null };
    const toRad = (d: number) => (d * Math.PI) / 180;
    // Unit vector A → B in (lon, lat) space (flat-earth approximation, fine at short range)
    const dLat = boatB.lat - boatA.lat;
    const dLon = boatB.lon - boatA.lon;
    const norm = Math.sqrt(dLat * dLat + dLon * dLon);
    if (norm < 1e-12) return { closingSpeed: 0, ttc: 0 as number | null };
    const ux = dLon / norm; // east component of unit vector A→B
    const uy = dLat / norm; // north component
    // Velocity components (heading = degrees clockwise from north)
    const vAx = Number(boatA.speed) * Math.sin(toRad(Number(boatA.heading)));
    const vAy = Number(boatA.speed) * Math.cos(toRad(Number(boatA.heading)));
    const vBx = Number(boatB.speed) * Math.sin(toRad(Number(boatB.heading)));
    const vBy = Number(boatB.speed) * Math.cos(toRad(Number(boatB.heading)));
    // Closing speed = projection of (vA − vB) along A→B; positive means approaching
    const cs = (vAx - vBx) * ux + (vAy - vBy) * uy;
    if (cs <= 0) return { closingSpeed: 0, ttc: null as number | null }; // diverging
    return { closingSpeed: cs, ttc: distance / cs };
  }, [boatA, boatB, distance]);
  const futureDist = useMemo(
    () => futureSeparation(groupedPredictions[boatA?.boat_id ?? ""], groupedPredictions[boatB?.boat_id ?? ""]),
    [groupedPredictions, boatA, boatB],
  );
  const [ackState, setAckState] = useState<"idle" | "pending" | "done">("idle");
  const confidence = averageConfidence(predictions);

  const risk = boatA && boatB ? Math.max(Number(boatA.risk || 0), Number(boatB.risk || 0)) : 0;
  const level = riskClass(risk);
  const latestRec = Array.isArray(recommendations) ? recommendations[0] : null;
  const action = latestRec?.action || "MAINTAIN COURSE";
  const tone = recommendationTone(latestRec?.action);

  const headline =
    level === "danger" ? "Collision likely" : level === "warning" ? "Closing — stay alert" : "All clear";
  const subline =
    level === "danger"
      ? "Boats are on a converging path and will pass dangerously close."
      : level === "warning"
      ? "Distance is shrinking. Be ready to adjust heading or speed."
      : "Boats are well separated. No action needed.";

  const toneBg = tone === "danger" ? "bg-danger" : tone === "warning" ? "bg-warning" : "bg-safe";
  const toneText = tone === "danger" ? "text-danger" : tone === "warning" ? "text-warning" : "text-safe";
  const toneBorder =
    tone === "danger" ? "border-danger/40" : tone === "warning" ? "border-warning/40" : "border-safe/40";

  return (
    <div className="grid grid-cols-1 xl:grid-cols-[1fr_400px] gap-4 h-full min-h-0">
      <div className="relative rounded-xl overflow-hidden border border-white/5 bg-panel-2 min-h-[400px]">
        <MapContainer center={center} zoom={16} scrollWheelZoom className="h-full w-full">
          <TileLayer
            attribution="&copy; CartoDB"
            url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
          />
          {Object.entries(actualPaths).map(([id, pts], idx) => (
            <Polyline
              key={`a-${id}`}
              positions={pts.slice(-30)}
              pathOptions={{ color: BOAT_COLORS[idx % BOAT_COLORS.length], weight: 2.5, opacity: 0.4 }}
            />
          ))}
          {Object.entries(groupedPredictions).map(([id, pts], idx) => {
            if (pts.length < 2) return null;
            const color = BOAT_COLORS[idx % BOAT_COLORS.length];
            const solid = pts.slice(0, 5);
            const uncertain = pts.slice(4);
            return (
              <Fragment key={`p-${id}`}>
                <Polyline positions={solid.map((p) => [p[0], p[1]] as LatLngExpression) as LatLngExpression[]} pathOptions={{ color, weight: 3, opacity: 0.9 }} />
                <Polyline
                  positions={uncertain.map((p) => [p[0], p[1]] as LatLngExpression) as LatLngExpression[]}
                  pathOptions={{ color, weight: 2, opacity: 0.4, dashArray: "5 5" }}
                />
              </Fragment>
            );
          })}
          {safe.map((b) => (
            <Marker key={b.boat_id} position={[b.lat, b.lon]} icon={makeIcon(Number(b.heading || 0), riskClass(b.risk))} />
          ))}
          {risk > 0.65 && boatA && boatB && (
            <Circle
              center={[(boatA.lat + boatB.lat) / 2, (boatA.lon + boatB.lon) / 2]}
              radius={60}
              pathOptions={{ color: "#ef4444", fillColor: "#ef4444", fillOpacity: 0.15, weight: 2, dashArray: "4 6" }}
            />
          )}
        </MapContainer>
      </div>

      <aside className="rounded-xl bg-panel/80 backdrop-blur-2xl border border-white/5 ring-1 ring-black/5 flex flex-col overflow-hidden shadow-2xl min-h-0">
        {/* Status banner */}
        <div className={`${toneBg} px-4 py-3 shrink-0 text-zinc-950`}>
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-bold uppercase tracking-widest opacity-70">Collision Risk</span>
            <span className="text-[10px] font-mono opacity-70">LIVE</span>
          </div>
          <div className="flex items-end justify-between mt-0.5">
            <h2 className="text-xl font-bold leading-tight">{headline}</h2>
            <div className="text-right leading-none">
              <div className="text-2xl font-mono font-bold tabular-nums">{Math.round(risk * 100)}<span className="text-sm">%</span></div>
              <div className="text-[9px] font-mono opacity-70 uppercase">probability</div>
            </div>
          </div>
          <p className="text-[12px] opacity-90 mt-1.5 leading-snug">{subline}</p>
        </div>

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto min-h-0 p-4 space-y-4">

          {/* What to do */}
          <section>
            <p className="text-[10px] font-mono text-zinc-500 uppercase tracking-wider mb-1.5">What to do</p>
            <div className={`border ${toneBorder} rounded-lg p-3 bg-white/[0.02]`}>
              <div className="flex items-center gap-2">
                <div className={`${toneBg} px-2 py-1 rounded text-zinc-950 font-bold text-xs tracking-wider`}>
                  {action.split(" ")[0]}
                </div>
                <p className="text-sm text-zinc-100 font-medium truncate">{action}</p>
              </div>
              {latestRec?.alert_state && (
                <p className="text-[12px] text-zinc-400 mt-2 leading-snug">{latestRec.alert_state}</p>
              )}
            </div>
          </section>

          {/* Vessels */}
          <section>
            <p className="text-[10px] font-mono text-zinc-500 uppercase tracking-wider mb-1.5">Vessels involved</p>
            <div className="grid grid-cols-2 gap-2">
              <VesselCard boat={boatA} color={BOAT_COLORS[0]} label="A" />
              <VesselCard boat={boatB} color={BOAT_COLORS[1]} label="B" />
            </div>
          </section>

          {/* Distance now vs predicted */}
          <section>
            <p className="text-[10px] font-mono text-zinc-500 uppercase tracking-wider mb-1.5">Distance between them</p>
            <div className="rounded-lg border border-white/5 bg-white/[0.02] p-3 space-y-3">
              <DistanceRow
                label="Right now"
                value={distance ? `${distance.toFixed(0)} m` : "—"}
                state={distance < 80 ? "danger" : distance < 150 ? "warning" : "safe"}
                hint="Live gap between the two boats at this moment."
              />
              <DistanceRow
                label="Closest predicted"
                value={futureDist != null ? `${futureDist.toFixed(0)} m` : "—"}
                state={futureDist != null && futureDist < 60 ? "danger" : futureDist != null && futureDist < 120 ? "warning" : "safe"}
                hint="Tightest gap the AI expects over the next few seconds."
              />
              <div className="border-t border-white/5 pt-2.5 space-y-1">
                <div className="flex items-center justify-between text-[11px] font-mono">
                  <span className="text-zinc-500">Closing in</span>
                  <span className={ttc !== null && ttc < 15 ? "text-danger" : ttc !== null && ttc < 45 ? "text-warning" : "text-zinc-300"}>
                    {ttc === null ? "—" : ttc > 60 ? `${(ttc / 60).toFixed(1)} min` : `${ttc.toFixed(0)} sec`}
                  </span>
                </div>
                <p className="text-[10px] text-zinc-500 leading-snug">Time until the boats meet if neither changes course.</p>
              </div>
              <div className="space-y-1">
                <div className="flex items-center justify-between text-[11px] font-mono">
                  <span className="text-zinc-500">Closing speed</span>
                  <span className="text-zinc-300">{closingSpeed > 0 ? `${closingSpeed.toFixed(1)} m/s` : "diverging"}</span>
                </div>
                <p className="text-[10px] text-zinc-500 leading-snug">How fast the gap is shrinking. Higher = less reaction time.</p>
              </div>
            </div>
            <p className={`text-[11px] mt-1.5 leading-snug ${toneText}`}>
              {level === "danger"
                ? "Boats will pass within unsafe range — act now."
                : level === "warning"
                ? "Gap is closing. Decide on an action soon."
                : "Predicted pass is comfortable. Continue course."}
            </p>
          </section>

          {/* Confidence */}
          <section>
            <div className="flex items-center justify-between mb-1">
              <p className="text-[10px] font-mono text-zinc-500 uppercase tracking-wider">AI forecast confidence</p>
              <span className="text-[11px] font-mono text-zinc-300">{(confidence * 100).toFixed(0)}%</span>
            </div>
            <div className="h-1.5 rounded-full bg-white/5 overflow-hidden">
              <div
                className={`h-full ${confidence > 0.7 ? "bg-safe" : confidence > 0.4 ? "bg-warning" : "bg-danger"} transition-all`}
                style={{ width: `${Math.max(4, confidence * 100)}%` }}
              />
            </div>
            <p className="text-[11px] text-zinc-500 mt-1 leading-snug">
              How sure the model is about this prediction. Lower confidence means trust your own judgement more.
            </p>
          </section>
        </div>

        {/* Footer */}
        <div className="p-3 border-t border-white/5 shrink-0">
          <button
            disabled={ackState !== "idle"}
            onClick={async () => {
              if (!boatA || ackState !== "idle") return;
              setAckState("pending");
              try {
                const API_BASE =
                  (import.meta.env.VITE_API_BASE as string | undefined) || "http://localhost:8000";
                await fetch(`${API_BASE}/boats/${boatA.boat_id}/ack`, {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ action: latestRec?.action || "", accepted: true }),
                });
                setAckState("done");
                setTimeout(() => setAckState("idle"), 3000);
              } catch {
                setAckState("idle");
              }
            }}
            className={`w-full text-sm font-semibold py-2.5 rounded-lg flex items-center justify-center gap-2 transition ${
              ackState === "done"
                ? "bg-safe text-zinc-950 cursor-default"
                : ackState === "pending"
                ? "bg-zinc-400 text-zinc-950 cursor-wait opacity-70"
                : tone === "danger"
                ? "bg-danger text-zinc-950 hover:brightness-110"
                : "bg-zinc-100 text-zinc-950 hover:bg-white"
            }`}>
            {ackState === "done" ? "Alert acknowledged ✓" : ackState === "pending" ? "Acknowledging…" : "Acknowledge Alert"}
            {ackState === "idle" && <kbd className="text-[10px] bg-black/15 px-1.5 rounded">ENTER</kbd>}
          </button>
        </div>
      </aside>
    </div>
  );
}

function VesselCard({ boat, color, label }: { boat?: Boat; color: string; label: string }) {
  return (
    <div className="bg-white/[0.02] border border-white/5 rounded-lg p-2.5">
      <div className="flex items-center gap-2 mb-1.5">
        <svg width="14" height="14" viewBox="0 0 32 32" style={{ transform: `rotate(${Number(boat?.heading || 0)}deg)`, color }}>
          <polygon points="16,3 24,26 16,21 8,26" fill="currentColor" />
        </svg>
        <span className="text-[10px] font-mono text-zinc-400 truncate">{boat?.boat_id || `Boat ${label}`}</span>
      </div>
      <div className="font-mono text-[11px] text-zinc-300 leading-relaxed">
        <div>{boat ? `${Number(boat.speed).toFixed(1)} m/s` : "—"}</div>
        <div className="text-zinc-500">{boat ? `heading ${Number(boat.heading).toFixed(0)}°` : "—"}</div>
      </div>
    </div>
  );
}

function DistanceRow({ label, value, state, hint }: { label: string; value: string; state: RiskLevel; hint?: string }) {
  const dot = state === "danger" ? "bg-danger" : state === "warning" ? "bg-warning" : "bg-safe";
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`size-2 rounded-full ${dot}`} />
          <span className="text-[12px] text-zinc-300">{label}</span>
        </div>
        <span className="text-sm font-mono tabular-nums text-zinc-100">{value}</span>
      </div>
      {hint && <p className="text-[10px] text-zinc-500 leading-snug pl-4">{hint}</p>}
    </div>
  );
}