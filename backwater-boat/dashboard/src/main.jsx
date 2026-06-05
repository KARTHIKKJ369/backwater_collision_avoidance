import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity, AlertTriangle, Clock, Map, Radio,
  Route, Table2, Anchor, Navigation, Gauge, ChevronRight
} from "lucide-react";
import { MapContainer, Marker, Polyline, Circle, Popup, TileLayer } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import "./styles.css";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

function makeBoatIcon(heading = 0, riskLevel = "safe") {
  const colors = { safe: "#00d4b8", warning: "#f0a500", danger: "#ff3b5c" };
  const color = colors[riskLevel] || colors.safe;
  const glow = riskLevel === "danger" ? `filter:drop-shadow(0 0 6px ${color});` : "";
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32" style="transform:rotate(${heading}deg);${glow}"><polygon points="16,3 24,26 16,21 8,26" fill="${color}" stroke="#000d1a" stroke-width="1.5" stroke-linejoin="round"/><polygon points="16,3 19,11 16,9 13,11" fill="white" opacity="0.55"/></svg>`;
  return new L.DivIcon({ className: "", html: svg, iconSize: [32, 32], iconAnchor: [16, 16] });
}

const tabs = [
  { id: "map",        label: "Live Map",          icon: Map },
  { id: "collision",  label: "Collision",          icon: AlertTriangle },
  { id: "prediction", label: "Prediction",         icon: Route },
  { id: "evaluation", label: "Evaluation",         icon: Activity },
  { id: "alerts",     label: "Alerts",             icon: Gauge },
  { id: "telemetry",  label: "Telemetry",          icon: Table2 },
  { id: "history",    label: "History",            icon: Clock },
];

function useApiData() {
  const [state, setState] = useState({
    boats: [], telemetry: [], latest: [], alerts: [],
    predictions: [], metrics: {}, evaluation: {}, timeline: [], recommendations: [],
  });
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        const [boats, telemetry, latest, alerts, predictions, metrics, evaluation, timeline, recommendations] =
          await Promise.all([
            fetch(`${API_BASE}/boats`).then(r => r.json()),
            fetch(`${API_BASE}/telemetry?limit=120`).then(r => r.json()),
            fetch(`${API_BASE}/telemetry/latest`).then(r => r.json()),
            fetch(`${API_BASE}/alerts?limit=50`).then(r => r.json()),
            fetch(`${API_BASE}/predictions?limit=50`).then(r => r.json()),
            fetch(`${API_BASE}/metrics`).then(r => r.json()),
            fetch(`${API_BASE}/evaluation`).then(r => r.json()),
            fetch(`${API_BASE}/timeline`).then(r => r.json()),
            fetch(`${API_BASE}/recommendations?limit=20`).then(r => r.json()),
          ]);
        if (alive) { setState({ boats, telemetry, latest, alerts, predictions, metrics, evaluation, timeline, recommendations }); setError(""); }
      } catch { if (alive) setError("Offline"); }
    }
    load();
    const t = setInterval(load, 1500);
    return () => { alive = false; clearInterval(t); };
  }, []);

  return { ...state, error };
}

function riskClass(risk = 0) {
  if (risk > 0.7) return "danger";
  if (risk >= 0.4) return "warning";
  return "safe";
}

function Clock12() {
  const [t, setT] = useState(new Date());
  useEffect(() => { const i = setInterval(() => setT(new Date()), 1000); return () => clearInterval(i); }, []);
  return <span className="time-badge">{t.toLocaleTimeString()}</span>;
}

function Shell() {
  const [active, setActive] = useState("map");
  const data = useApiData();
  const center = data.latest[0] ? [data.latest[0].lat, data.latest[0].lon] : [9.591, 76.522];
  const groupedPredictions = useMemo(() => {
    return data.predictions.reduce((acc, p) => {
      acc[p.boat_id] ||= [];
      acc[p.boat_id].push([p.pred_lat, p.pred_lon]);
      return acc;
    }, {});
  }, [data.predictions]);

  const activeTab = tabs.find(t => t.id === active);
  const ActiveIcon = activeTab?.icon || Radio;
  const dangerAlerts = data.alerts.filter(a => a.severity?.toLowerCase() === "danger").length;

  return (
    <main className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-icon"><Anchor size={18} color="#fff" /></div>
          <div>
            <h1>Backwater Guard</h1>
            <p>Collision Avoidance</p>
          </div>
        </div>
        <nav>
          {tabs.map(tab => {
            const Icon = tab.icon;
            return (
              <button key={tab.id} className={active === tab.id ? "active" : ""} onClick={() => setActive(tab.id)}>
                <Icon size={16} />
                <span>{tab.label}</span>
                {tab.id === "alerts" && dangerAlerts > 0 && (
                  <span style={{ marginLeft: "auto", background: "var(--danger)", color: "#fff", borderRadius: "99px", fontSize: "9px", fontWeight: 700, padding: "1px 6px" }}>{dangerAlerts}</span>
                )}
              </button>
            );
          })}
        </nav>
        <div className="sidebar-footer">
          <div className="sys-stats">
            <div className="sys-stat"><span>Boats</span><strong>{data.latest.length}</strong></div>
            <div className="sys-stat"><span>Alerts</span><strong>{data.alerts.length}</strong></div>
            <div className="sys-stat"><span>Preds</span><strong>{data.predictions.length}</strong></div>
            <div className="sys-stat"><span>Telem</span><strong>{data.telemetry.length}</strong></div>
          </div>
        </div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div className="topbar-left">
            <ActiveIcon size={16} />
            <h2>{activeTab?.label}</h2>
          </div>
          <div className="topbar-right">
            <Clock12 />
            <div className={`status-dot${data.error ? " offline" : ""}`} />
            <span className={`status${data.error ? " offline" : ""}`}>{data.error || "Live"}</span>
          </div>
        </header>

        {active === "map"        && <LiveMap center={center} latest={data.latest} predictions={groupedPredictions} telemetry={data.telemetry} />}
        {active === "collision"  && <PredictiveCollision center={center} latest={data.latest} telemetry={data.telemetry} predictions={data.predictions} metrics={data.metrics} recommendations={data.recommendations} />}
        {active === "prediction" && <Prediction latest={data.latest} predictions={data.predictions} />}
        {active === "evaluation" && <ScenarioEvaluation evaluation={data.evaluation} timeline={data.timeline} />}
        {active === "alerts"     && <Alerts alerts={data.alerts} />}
        {active === "telemetry"  && <Telemetry rows={data.telemetry} />}
        {active === "history"    && <History telemetry={data.telemetry} alerts={data.alerts} />}
      </section>
    </main>
  );
}

// Boat colors per index so two boats are visually distinct
const BOAT_COLORS = ["#00d4b8", "#1e90ff", "#f0a500", "#c084fc"];

function LiveMap({ center, latest, predictions, telemetry }) {
  // Build actual trail per boat from recent telemetry
  const trails = useMemo(() => groupPath(telemetry || [], "lat", "lon"), [telemetry]);

  // Build fading predicted segments: each step gets progressively lower opacity
  function predSegments(points) {
    if (!points || points.length < 2) return [];
    const segs = [];
    for (let i = 0; i < points.length - 1; i++) {
      segs.push({ pts: [points[i], points[i + 1]], opacity: 1 - i / points.length });
    }
    return segs;
  }

  // Check if any two boats are dangerously close
  const collisionPairs = useMemo(() => {
    const pairs = [];
    for (let i = 0; i < latest.length; i++) {
      for (let j = i + 1; j < latest.length; j++) {
        const d = haversine(latest[i].lat, latest[i].lon, latest[j].lat, latest[j].lon);
        if (d < 80) pairs.push({ a: latest[i], b: latest[j], dist: d });
      }
    }
    return pairs;
  }, [latest]);

  return (
    <div className="map-wrap">
      <MapContainer center={center} zoom={15} scrollWheelZoom className="map">
        <TileLayer attribution="&copy; OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />

        {/* Actual trail (last N positions, faint) */}
        {latest.map((boat, idx) => {
          const trail = trails[boat.boat_id] || [];
          const color = BOAT_COLORS[idx % BOAT_COLORS.length];
          return trail.length > 1 ? (
            <Polyline key={`trail-${boat.boat_id}`} positions={trail.slice(-30)}
              pathOptions={{ color, weight: 2, opacity: 0.35 }} />
          ) : null;
        })}

        {/* Predicted path — fading dashed segments per step */}
        {latest.map((boat, idx) => {
          const pts = predictions[boat.boat_id] || [];
          const color = BOAT_COLORS[idx % BOAT_COLORS.length];
          return predSegments(pts).map((seg, si) => (
            <Polyline key={`pred-${boat.boat_id}-${si}`} positions={seg.pts}
              pathOptions={{ color, weight: 2.5, opacity: seg.opacity * 0.85, dashArray: "6 6" }} />
          ));
        })}

        {/* Predicted endpoint dot */}
        {latest.map((boat, idx) => {
          const pts = predictions[boat.boat_id] || [];
          const last = pts[pts.length - 1];
          const color = BOAT_COLORS[idx % BOAT_COLORS.length];
          return last ? (
            <Circle key={`pred-end-${boat.boat_id}`} center={last}
              radius={4} pathOptions={{ color, fillColor: color, fillOpacity: 0.5, weight: 1.5, opacity: 0.4 }} />
          ) : null;
        })}

        {/* Collision warning zone */}
        {collisionPairs.map(({ a, b }, i) => (
          <Circle key={`col-${i}`}
            center={[(a.lat + b.lat) / 2, (a.lon + b.lon) / 2]}
            radius={50}
            pathOptions={{ color: "#ff3b5c", fillColor: "#ff3b5c", fillOpacity: 0.08, weight: 1.5, dashArray: "4 6" }} />
        ))}

        {/* Boat markers with heading arrow */}
        {latest.map((boat, idx) => {
          const rc = riskClass(boat.risk);
          const icon = makeBoatIcon(Number(boat.heading || 0), rc);
          return (
            <Marker key={boat.boat_id} position={[boat.lat, boat.lon]} icon={icon}>
              <Popup>
                <strong style={{ fontFamily: "monospace", fontSize: 13 }}>{boat.boat_id}</strong><br />
                Speed: {Number(boat.speed).toFixed(2)} m/s<br />
                Heading: {Number(boat.heading).toFixed(1)}°<br />
                Risk: <span style={{ color: rc === "danger" ? "#ff3b5c" : rc === "warning" ? "#f0a500" : "#00c97a", fontWeight: 700 }}>{Number(boat.risk).toFixed(3)}</span>
              </Popup>
            </Marker>
          );
        })}
      </MapContainer>

      {/* Map legend */}
      <div className="map-legend">
        <div className="legend-row"><span className="legend-line solid" style={{ background: "#00d4b8" }} />Boat A trail</div>
        <div className="legend-row"><span className="legend-line solid" style={{ background: "#1e90ff" }} />Boat B trail</div>
        <div className="legend-row"><span className="legend-line dashed" style={{ borderColor: "#00d4b8" }} />Predicted path</div>
        <div className="legend-row"><span className="legend-dot" style={{ background: "#ff3b5c" }} />Collision zone</div>
      </div>

      <div className="fleet-strip">
        {latest.map((boat, idx) => (
          <div className="fleet-item" key={boat.boat_id}>
            <div className="fleet-boat-arrow" style={{ color: BOAT_COLORS[idx % BOAT_COLORS.length] }}>
              <svg width="18" height="18" viewBox="0 0 32 32" style={{ transform: `rotate(${Number(boat.heading||0)}deg)` }}>
                <polygon points="16,3 24,26 16,21 8,26" fill="currentColor" />
              </svg>
            </div>
            <div>
              <div className="fleet-item-id">{boat.boat_id}</div>
              <div className="fleet-item-meta">{Number(boat.speed||0).toFixed(1)} m/s · {Number(boat.heading||0).toFixed(0)}°</div>
            </div>
            <span className={`pill ${riskClass(boat.risk)}`}>{Number(boat.risk).toFixed(2)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function PredictiveCollision({ center, latest, telemetry, predictions, metrics, recommendations }) {
  const [boatA, boatB] = latest;
  const actualPaths   = groupPath(telemetry, "lat", "lon");
  const predictedPaths = groupPath(predictions, "pred_lat", "pred_lon");
  const distance      = boatA && boatB ? haversine(boatA.lat, boatA.lon, boatB.lat, boatB.lon) : 0;
  const relativeSpeed = boatA && boatB ? Math.max(0.1, Math.abs(boatA.speed - boatB.speed)) : 0.1;
  const ttc           = distance ? distance / relativeSpeed : null;
  const futureDistance = futureSeparation(predictedPaths[boatA?.boat_id], predictedPaths[boatB?.boat_id]);
  const alertState    = stateForFutureDistance(futureDistance);
  const risk          = boatA && boatB ? Math.max(Number(boatA.risk || 0), Number(boatB.risk || 0)) : 0;
  const avgConfidence = averageConfidence(predictions);
  const ttcState      = ttcColorState(ttc);
  const riskState     = riskClass(risk);
  const latestRec     = recommendations[0];

  return (
    <div className="collision-layout">
      <section style={{ minWidth: 0, overflow: "hidden", borderRadius: 10 }}>
        <MapContainer center={center} zoom={15} scrollWheelZoom className="map compact">
          <TileLayer attribution="&copy; OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
          {Object.entries(actualPaths).map(([id, pts], idx) => (
            <Polyline key={`a-${id}`} positions={pts.slice(-30)}
              pathOptions={{ color: BOAT_COLORS[idx % BOAT_COLORS.length], weight: 2.5, opacity: 0.45 }} />
          ))}
          {Object.entries(predictedPaths).map(([id, pts], idx) => {
            const color = BOAT_COLORS[idx % BOAT_COLORS.length];
            const segs = [];
            for (let i = 0; i < pts.length - 1; i++) {
              segs.push({ pts: [pts[i], pts[i+1]], op: 1 - i / pts.length });
            }
            return segs.map((seg, si) => (
              <Polyline key={`p-${id}-${si}`} positions={seg.pts}
                pathOptions={{ color, weight: 2, opacity: seg.op * 0.85, dashArray: "6 6" }} />
            ));
          })}
          {latest.map((boat, idx) => (
            <Marker key={boat.boat_id} position={[boat.lat, boat.lon]}
              icon={makeBoatIcon(Number(boat.heading || 0), riskClass(boat.risk))}>
              <Popup>{boat.boat_id}</Popup>
            </Marker>
          ))}
          {risk > 0.7 && boatA && boatB && (
            <Circle center={[(boatA.lat + boatB.lat)/2, (boatA.lon + boatB.lon)/2]}
              radius={60}
              pathOptions={{ color: "#ff3b5c", fillColor: "#ff3b5c", fillOpacity: 0.08, weight: 1.5, dashArray: "4 6" }} />
          )}
        </MapContainer>
      </section>

      <div className="collision-panel">
        <div className="panel-section-label">Vessels</div>
        <Metric label="Boat A" value={boatA?.boat_id || "—"} />
        <Metric label="Boat B" value={boatB?.boat_id || "—"} />

        <div className="panel-section-label">Risk</div>
        <Metric label="Risk Score" value={`${(risk * 100).toFixed(0)}%`} tone={riskState} />
        <div className="risk-meter-wrap">
          <div className="risk-meter-label">
            <span>0%</span><span>100%</span>
          </div>
          <div className={`risk-meter ${riskState}`}>
            <span style={{ width: `${Math.min(100, risk * 100)}%` }} />
          </div>
        </div>
        <Metric label="Alert State"  value={alertState}                              tone={alertState.toLowerCase()} />
        <Metric label="TTC"          value={ttc === null ? "N/A" : `${ttc.toFixed(1)} s`} tone={ttcState} />
        <Metric label="Future Dist"  value={futureDistance ? `${futureDistance.toFixed(1)} m` : "—"} />

        <div className="panel-section-label">Prediction</div>
        <Metric label="Confidence"   value={avgConfidence ? `${(avgConfidence * 100).toFixed(0)}%` : "—"} tone={confidenceState(avgConfidence)} />
        <Metric label="Executed"     value={`${metrics.prediction_executed || 0} / ${metrics.prediction_skipped || 0} skip`} />
        <Metric label="Collisions"   value={metrics.collisions_predicted || 0}        tone={metrics.collisions_predicted ? "danger" : "safe"} />

        <div className="panel-section-label">Actions</div>
        <Metric label="Recommendation" value={latestRec?.action || "MAINTAIN"}        tone={recommendationTone(latestRec?.action)} />
        <Metric label="Accepted"       value={metrics.accepted_actions || 0}           tone={metrics.accepted_actions ? "safe" : ""} />
        <Metric label="Avoided"        value={metrics.avoided_collisions || 0}         tone={metrics.avoided_collisions ? "safe" : ""} />
        <Metric label="Alerts Total"   value={metrics.alerts_total || 0} />

        <div className="panel-section-label">Position</div>
        <Metric label="Boat A Pos"    value={boatA ? `${Number(boatA.lat).toFixed(5)}, ${Number(boatA.lon).toFixed(5)}` : "—"} />
        <Metric label="Predicted"     value={predictedPaths[boatA?.boat_id]?.[0]?.map(v => Number(v).toFixed(4)).join(", ") || "—"} />
      </div>
    </div>
  );
}

function Metric({ label, value, tone = "" }) {
  return (
    <div className={`metric ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Prediction({ latest, predictions }) {
  async function trigger(boatId) {
    await fetch(`${API_BASE}/predict`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ boat_id: boatId }),
    });
  }
  return (
    <div className="prediction-wrap">
      <div className="panel" style={{ height: "fit-content" }}>
        <h3>Trigger Prediction</h3>
        <div className="boat-actions">
          {latest.map(boat => (
            <button key={boat.boat_id} onClick={() => trigger(boat.boat_id)}>
              <Navigation size={15} />
              <span>{boat.boat_id}</span>
              <ChevronRight size={14} style={{ marginLeft: "auto", opacity: 0.4 }} />
            </button>
          ))}
          {latest.length === 0 && <p className="empty" style={{ padding: "12px 0" }}>No boats online</p>}
        </div>
      </div>
      <DataTable title="Future Positions" rows={predictions} columns={["boat_id", "timestamp", "pred_lat", "pred_lon", "confidence"]} />
    </div>
  );
}

function ScenarioEvaluation({ evaluation, timeline }) {
  const cards = [
    ["Scenario",    evaluation.scenario   || "LIVE"],
    ["Alerts",      evaluation.alerts     || 0],
    ["Predictions", evaluation.predictions || 0],
    ["Collisions",  evaluation.collisions  || 0],
    ["Precision",   formatPercent(evaluation.precision)],
    ["Latency",     `${evaluation.latency || 0} ms`],
  ];
  return (
    <div className="evaluation-page">
      <div className="eval-cards">
        {cards.map(([label, value]) => (
          <div className="eval-card" key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>
      <div className="panel" style={{ flex: 1 }}>
        <h3>Collision Timeline</h3>
        <div className="timeline-chart">
          {timeline.slice(-80).map((point, i) => (
            <div className="timeline-row" key={`${point.t}-${i}`}>
              <span>{formatValue(point.t)}</span>
              <div className="timeline-track">
                <i className={riskClass(point.risk)} style={{ width: `${Math.max(4, Math.min(100, Number(point.risk || 0) * 100))}%` }} />
              </div>
              <strong style={{ fontSize: 10, color: riskColor(point.risk) }}>{point.alert || "SAFE"}</strong>
            </div>
          ))}
          {timeline.length === 0 && <p className="empty">No timeline data yet.</p>}
        </div>
      </div>
    </div>
  );
}

function Alerts({ alerts }) {
  return (
    <div className="alerts-wrap">
      {alerts.length === 0 && <p className="empty">No alerts — all clear.</p>}
      {alerts.map(alert => (
        <article key={alert.id} className={`alert ${alert.severity?.toLowerCase()}`}>
          <AlertTriangle size={16} className="alert-icon" />
          <div>
            <strong>{alert.severity} · {alert.boat_id}</strong>
            <p>{alert.message}</p>
          </div>
          <span style={{ marginLeft: "auto", fontSize: 10, fontFamily: "monospace", color: "var(--text-dim)", flexShrink: 0 }}>
            {formatValue(alert.timestamp)}
          </span>
        </article>
      ))}
    </div>
  );
}

function Telemetry({ rows }) {
  return (
    <div className="table-wrap">
      <DataTable title="Live Telemetry" rows={rows} columns={["boat_id", "timestamp", "lat", "lon", "speed", "heading", "obstacle", "risk"]} />
    </div>
  );
}

function History({ telemetry, alerts }) {
  return (
    <div className="history-wrap">
      <DataTable title="Recent Telemetry" rows={telemetry.slice(0, 40)} columns={["boat_id", "timestamp", "lat", "lon", "risk"]} />
      <DataTable title="Recent Alerts"    rows={alerts}                  columns={["boat_id", "timestamp", "severity", "message"]} />
    </div>
  );
}

function DataTable({ title, rows, columns }) {
  return (
    <div className="table-panel">
      <h3>{title}</h3>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>{columns.map(col => <th key={col}>{col}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map((row, idx) => (
              <tr key={row.id || `${row.boat_id}-${idx}`}>
                {columns.map(col => <td key={col}>{formatValue(row[col])}</td>)}
              </tr>
            ))}
            {rows.length === 0 && (
              <tr><td colSpan={columns.length} style={{ textAlign: "center", color: "var(--text-dim)", padding: "24px" }}>No data</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Helpers ──
function formatValue(v) {
  if (typeof v === "number") return Math.abs(v) > 1000 ? v.toFixed(0) : v.toFixed(5).replace(/0+$/, "").replace(/\.$/, "");
  return v ?? "";
}
function formatPercent(v) { return v == null ? "0%" : `${(Number(v) * 100).toFixed(1)}%`; }
function groupPath(rows, latKey, lonKey) {
  return rows.reduce((acc, row) => {
    if (row[latKey] == null || row[lonKey] == null) return acc;
    acc[row.boat_id] ||= [];
    acc[row.boat_id].push([row[latKey], row[lonKey]]);
    return acc;
  }, {});
}
function haversine(lat1, lon1, lat2, lon2) {
  const R = 6371000, dLat = (lat2 - lat1) * Math.PI / 180, dLon = (lon2 - lon1) * Math.PI / 180;
  const a = Math.sin(dLat/2)**2 + Math.cos(lat1*Math.PI/180)*Math.cos(lat2*Math.PI/180)*Math.sin(dLon/2)**2;
  return 2 * R * Math.asin(Math.sqrt(a));
}
function futureSeparation(pathA = [], pathB = []) {
  let min = 0;
  pathA.slice(0, 5).forEach((p, i) => {
    const o = pathB[i]; if (!o) return;
    const d = haversine(p[0], p[1], o[0], o[1]);
    min = min === 0 ? d : Math.min(min, d);
  });
  return min;
}
function stateForFutureDistance(d)    { if (!d || d > 100) return "SAFE"; if (d >= 50) return "WARNING"; return "DANGER"; }
function averageConfidence(preds)     { if (!preds.length) return 0; return preds.reduce((s, p) => s + Number(p.confidence || 0), 0) / preds.length; }
function confidenceState(c)           { if (c >= 0.75) return "safe"; if (c >= 0.45) return "warning"; return "danger"; }
function ttcColorState(ttc)           { if (!ttc || ttc > 20) return "safe"; if (ttc > 10) return "warning"; return "danger"; }
function recommendationTone(a = "")   { if (a.startsWith("HARD") || a === "STOP") return "danger"; if (a === "SLOW_DOWN" || a.startsWith("TURN")) return "warning"; return "safe"; }
function riskColor(risk)              { if (risk > 0.7) return "var(--danger)"; if (risk >= 0.4) return "var(--warn)"; return "var(--safe)"; }

createRoot(document.getElementById("root")).render(<Shell />);