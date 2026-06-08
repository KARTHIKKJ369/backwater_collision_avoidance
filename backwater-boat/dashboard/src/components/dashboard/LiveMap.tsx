import { Fragment, useMemo, useState } from "react";
import { MapContainer, TileLayer, Marker, Polyline, Circle, Popup, Tooltip } from "react-leaflet";
import type { LatLngExpression } from "leaflet";
import L from "leaflet";
import { Layers } from "lucide-react";
import { haversine, riskClass, type Boat, type RiskLevel } from "@/lib/maritime";

const BOAT_COLORS = ["#06b6d4", "#a78bfa", "#fbbf24", "#34d399"];

const iconCache = new Map<string, L.DivIcon>();
function boatIcon(heading = 0, level: RiskLevel = "safe") {
  const key = `${heading}|${level}`;
  const hit = iconCache.get(key);
  if (hit) return hit;
  const colors: Record<RiskLevel, string> = {
    safe: "#10b981",
    warning: "#f59e0b",
    danger: "#ef4444",
  };
  const color = colors[level];
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 32 32" style="transform:rotate(${heading}deg);"><polygon points="16,2 26,28 16,22 6,28" fill="${color}" stroke="#09090b" stroke-width="2" stroke-linejoin="miter"/></svg>`;
  const icon = new L.DivIcon({ className: "", html: svg, iconSize: [28, 28], iconAnchor: [14, 14] });
  iconCache.set(key, icon);
  return icon;
}

type Props = {
  center: [number, number];
  latest: Boat[];
  predictions: Record<string, [number, number, number][]>;
  telemetry: Boat[];
};

export default function LiveMap({ center, latest, predictions, telemetry }: Props) {
  const [showPreds, setShowPreds] = useState(true);
  const safe = Array.isArray(latest) ? latest : [];

  const collisionPairs = useMemo(() => {
    const pairs: { a: Boat; b: Boat; dist: number }[] = [];
    for (let i = 0; i < safe.length; i++) {
      for (let j = i + 1; j < safe.length; j++) {
        const d = haversine(safe[i].lat, safe[i].lon, safe[j].lat, safe[j].lon);
        if (d < 80) pairs.push({ a: safe[i], b: safe[j], dist: d });
      }
    }
    return pairs;
  }, [safe]);




  return (
    <div className="relative h-full w-full rounded-xl overflow-hidden border border-white/5 bg-panel-2">
      <div className="absolute inset-0 tactical-grid opacity-30 pointer-events-none z-[400]" />

      <MapContainer center={center} zoom={16} scrollWheelZoom className="h-full w-full">
        <TileLayer
          attribution="&copy; CartoDB"
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
        />



        {showPreds &&
          safe.map((b, idx) => {
            const pts = predictions[b.boat_id] || [];
            if (pts.length < 2) return null;
            const color = BOAT_COLORS[idx % BOAT_COLORS.length];
            const solid = pts.slice(0, 5);
            const uncertain = pts.slice(4);
            return (
              <Fragment key={`pred-${b.boat_id}`}>
                <Polyline positions={solid.map((p) => [p[0], p[1]] as LatLngExpression) as LatLngExpression[]} pathOptions={{ color, weight: 3, opacity: 0.9 }} />
                <Polyline positions={uncertain.map((p) => [p[0], p[1]] as LatLngExpression) as LatLngExpression[]} pathOptions={{ color, weight: 2, opacity: 0.4, dashArray: "5 5" }} />
                {(() => {
                  const end = pts[pts.length - 1];
                  if (!end) return null;
                  const avgConf =
                    pts.reduce((s, p) => s + (p[2] || 0.5), 0) / pts.length;
                  // Radius grows with uncertainty (lower confidence = bigger zone)
                  const radius = Math.max(8, 30 * (1 - avgConf));
                  return (
                    <Circle
                      center={[end[0], end[1]]}
                      radius={radius}
                      pathOptions={{ color, weight: 1.5, fillColor: color, fillOpacity: 0.12, dashArray: "2 4" }}
                    >
                      <Tooltip direction="top" offset={[0, -4]} opacity={0.95}>
                        <span style={{ fontSize: 11 }}>
                          {b.boat_id} · predicted zone
                          <br />
                          confidence {(avgConf * 100).toFixed(0)}%
                        </span>
                      </Tooltip>
                    </Circle>
                  );
                })()}
              </Fragment>
            );
          })}

        {collisionPairs.map(({ a, b }, i) => (
          <Circle
            key={`col-${i}`}
            center={[(a.lat + b.lat) / 2, (a.lon + b.lon) / 2]}
            radius={50}
            pathOptions={{ color: "#ef4444", fillColor: "#ef4444", fillOpacity: 0.15, weight: 2, dashArray: "4 6" }}
          />
        ))}

        {safe.map((b) => {
          const level = riskClass(b.risk);
          const riskLabel = level === "danger" ? "High — act now" : level === "warning" ? "Caution" : "Safe";
          const riskColor = level === "danger" ? "#ef4444" : level === "warning" ? "#f59e0b" : "#10b981";
          return (
            <Marker key={b.boat_id} position={[b.lat, b.lon]} icon={boatIcon(Number(b.heading || 0), level)}>
              <Popup>
                <div style={{ minWidth: 160, fontSize: 12 }}>
                  <strong style={{ fontSize: 13 }}>{b.boat_id}</strong>
                  <div style={{ marginTop: 6, color: "#52525b" }}>Speed <span style={{ color: "#18181b", float: "right" }}>{Number(b.speed).toFixed(2)} m/s</span></div>
                  <div style={{ color: "#52525b" }}>Heading <span style={{ color: "#18181b", float: "right" }}>{Number(b.heading).toFixed(0)}°</span></div>
                  <div style={{ color: "#52525b" }}>Risk <span style={{ color: riskColor, float: "right", fontWeight: 600 }}>{riskLabel}</span></div>
                  <div style={{ marginTop: 6, fontSize: 10, color: "#71717a", lineHeight: 1.4 }}>
                    Arrow points where the boat is going. Color shows current danger level.
                  </div>
                </div>
              </Popup>
            </Marker>
          );
        })}
      </MapContainer>

      {/* Map controls */}
      <div className="absolute top-4 right-4 z-[450] flex flex-col gap-2">
        <button
          onClick={() => setShowPreds((s) => !s)}
          className={`flex items-center gap-2 px-3 py-2 rounded-md text-xs font-medium backdrop-blur-md border ring-1 transition-all ${
            showPreds
              ? "bg-cyan/10 text-cyan border-cyan/40 ring-cyan/20"
              : "bg-panel/80 text-zinc-300 border-white/10 ring-black/5 hover:text-zinc-100"
          }`}
        >
          <Layers className="size-3.5" /> AI Predictions
        </button>
        <div className="px-3 py-2 rounded-md text-[10px] font-mono bg-panel/70 backdrop-blur-md border border-white/10 text-zinc-400 max-w-[200px] leading-snug space-y-1.5">
          <div className="text-zinc-300 font-semibold">Map legend</div>
          <div><span className="text-zinc-200">▲ arrow</span> — boat, points to heading</div>
          <div><span className="text-safe">●</span> safe <span className="text-warning ml-1">●</span> caution <span className="text-danger ml-1">●</span> danger</div>
          <div><span className="text-zinc-200">— solid line</span> — path for next ~5s</div>
          <div><span className="text-zinc-200">-- dashed</span> — longer forecast (less sure)</div>
          <div><span className="text-zinc-200">○ circle</span> — where boat may end up</div>
          <div><span className="text-danger">○ red ring</span> — collision risk zone</div>
        </div>
      </div>


      {/* Fleet strip */}
      <div className="absolute bottom-4 left-4 right-4 z-[450] flex gap-3 overflow-x-auto pb-2 scrollbar-hide">
        {safe.map((b, idx) => {
          const level = riskClass(b.risk);
          const color = BOAT_COLORS[idx % BOAT_COLORS.length];
          return (
            <div
              key={b.boat_id}
              className="min-w-[200px] bg-panel/80 backdrop-blur-md border border-white/10 ring-1 ring-black/5 rounded-lg p-3 shadow-2xl"
            >
              <div className="flex items-center gap-3">
                <svg width="22" height="22" viewBox="0 0 32 32" style={{ transform: `rotate(${Number(b.heading || 0)}deg)`, color }}>
                  <polygon points="16,3 24,26 16,21 8,26" fill="currentColor" />
                </svg>
                <div className="flex-1 min-w-0">
                  <div className="text-[10px] font-mono text-zinc-500 uppercase truncate">{b.boat_id}</div>
                  <div className="text-xs font-mono text-zinc-200">
                    {Number(b.speed || 0).toFixed(1)} m/s · {Number(b.heading || 0).toFixed(0)}°
                  </div>
                </div>
                <RiskPill level={level} value={Number(b.risk).toFixed(2)} />
              </div>
            </div>
          );
        })}
        {safe.length === 0 && (
          <div className="text-[11px] font-mono text-zinc-600 px-3 py-2 bg-panel/60 border border-white/5 rounded-lg">
            No vessels online — waiting for telemetry…
          </div>
        )}
      </div>
    </div>
  );
}

export function RiskPill({ level, value }: { level: RiskLevel; value: string | number }) {
  const cls =
    level === "danger"
      ? "bg-danger/15 text-danger shadow-[0_0_10px_rgba(239,68,68,0.25)]"
      : level === "warning"
      ? "bg-warning/15 text-warning"
      : "bg-safe/15 text-safe";
  return (
    <span className={`px-2 py-0.5 rounded-full text-[10px] font-mono font-bold ${cls}`}>{value}</span>
  );
}