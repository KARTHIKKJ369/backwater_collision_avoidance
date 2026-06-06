import React, { useEffect, useMemo, useState, memo } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity, AlertTriangle, Clock, Map as MapIcon, Radio,
  Anchor, Navigation, Layers, CloudRain, Wind, Eye, Sun, CloudFog, CloudLightning, Cloud
} from "lucide-react";
import { MapContainer, Marker, Polyline, Circle, Popup, TileLayer } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import "./styles.css";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

const _iconCache = new Map();
function makeBoatIcon(heading = 0, riskLevel = "safe") {
  const key = `${heading}|${riskLevel}`;
  if (_iconCache.has(key)) return _iconCache.get(key);
  const colors = { safe: "#10B981", warning: "#F59E0B", danger: "#EF4444" };
  const color  = colors[riskLevel] || colors.safe;
  
  const svg    = `<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 32 32" style="transform:rotate(${heading}deg);"><polygon points="16,2 26,28 16,22 6,28" fill="${color}" stroke="#0F172A" stroke-width="2" stroke-linejoin="miter"/></svg>`;
  const icon   = new L.DivIcon({ className: "", html: svg, iconSize: [28, 28], iconAnchor: [14, 14] });
  _iconCache.set(key, icon);
  return icon;
}

const tabs = [
  { id: "map",       label: "Live Map",   icon: MapIcon },
  { id: "collision", label: "Collision",  icon: AlertTriangle },
  { id: "analytics", label: "Analytics",  icon: Activity },
  { id: "logs",      label: "Logs",       icon: Clock },
];

const FAST_MS = 1500;
const SLOW_MS = 8000;

function useApiData() {
  const [fast, setFast] = useState({ boats: [], telemetry: [], latest: [], alerts: [], predictions: [], metrics: {} });
  const [slow, setSlow] = useState({ evaluation: {}, timeline: [], recommendations: [] });
  const [weather, setWeather] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    async function loadFast() {
      try {
        const [boats, telemetry, latest, alerts, predictions, metrics] = await Promise.all([
          fetch(`${API_BASE}/boats`).then(r => r.json()),
          fetch(`${API_BASE}/telemetry?limit=120`).then(r => r.json()),
          fetch(`${API_BASE}/telemetry/latest`).then(r => r.json()),
          fetch(`${API_BASE}/alerts?limit=50`).then(r => r.json()),
          fetch(`${API_BASE}/predictions?limit=50`).then(r => r.json()),
          fetch(`${API_BASE}/metrics`).then(r => r.json()),
        ]);
        if (alive) { setFast({ boats, telemetry, latest, alerts, predictions, metrics }); setError(""); }
      } catch { if (alive) setError("Offline"); }
    }
    
    async function loadSlow() {
      try {
        const [evaluation, timeline, recommendations, weatherData] = await Promise.all([
          fetch(`${API_BASE}/evaluation`).then(r => r.json()),
          fetch(`${API_BASE}/timeline`).then(r => r.json()),
          fetch(`${API_BASE}/recommendations?limit=20`).then(r => r.json()),
          fetch(`${API_BASE}/weather?lat=9.591&lon=76.522`).then(r => r.json()).catch(() => null),
        ]);
        if (alive) {
          setSlow({ evaluation, timeline, recommendations });
          if (weatherData) setWeather(weatherData);
        }
      } catch {}
    }
    loadFast(); loadSlow();
    const tFast = setInterval(loadFast, FAST_MS);
    const tSlow = setInterval(loadSlow, SLOW_MS);
    return () => { alive = false; clearInterval(tFast); clearInterval(tSlow); };
  }, []);

  return { ...fast, ...slow, weather, error };
}

function riskClass(risk = 0) {
  if (risk > 0.7)  return "danger";
  if (risk >= 0.4) return "warning";
  return "safe";
}

const Clock12 = memo(function Clock12() {
  const [t, setT] = useState(new Date());
  useEffect(() => { const i = setInterval(() => setT(new Date()), 1000); return () => clearInterval(i); }, []);
  return <span className="time-badge">{t.toLocaleTimeString()}</span>;
});

const StatusIndicator = memo(function StatusIndicator({ error }) {
  return (
    <div className="status-wrap">
      <div className={`status-dot${error ? " offline" : ""}`} />
      <span className={`status${error ? " offline" : ""}`}>{error || "System Live"}</span>
    </div>
  );
});

const WeatherWidget = memo(function WeatherWidget({ weather }) {
  if (!weather) return null;
  let Icon = Sun;
  const id = weather.condition_id || 800;
  if (id >= 200 && id < 300) Icon = CloudLightning;
  else if (id >= 300 && id < 600) Icon = CloudRain;
  else if (id >= 700 && id < 800) Icon = CloudFog;
  else if (id > 800) Icon = Cloud;

  return (
    <div className="weather-widget">
      <div className="weather-icon"><Icon size={20} /></div>
      <div className="weather-details">
        <span className="weather-desc">{weather.description}</span>
        <div className="weather-stats">
          <span><Wind size={10}/> {weather.wind_speed.toFixed(1)} m/s</span>
          <span><Eye size={10}/> {(weather.visibility_m / 1000).toFixed(1)} km</span>
        </div>
      </div>
    </div>
  );
});

function Shell() {
  const [active, setActive] = useState("map");
  const data   = useApiData();
  const center = Array.isArray(data.latest) && data.latest[0] ? [data.latest[0].lat, data.latest[0].lon] : [9.591, 76.522];

  const groupedPredictions = useMemo(() => {
    if (!Array.isArray(data.predictions)) return {};
    return data.predictions.reduce((acc, p) => {
      acc[p.boat_id] ||= [];
      acc[p.boat_id].push([p.pred_lat, p.pred_lon, p.confidence]);
      return acc;
    }, {});
  }, [data.predictions]);

  const dangerAlerts = useMemo(() => {
    if (!Array.isArray(data.alerts)) return 0;
    return data.alerts.filter(a => a.severity?.toLowerCase() === "danger").length;
  }, [data.alerts]);

  const activeTab  = tabs.find(t => t.id === active);
  const ActiveIcon = activeTab?.icon || Radio;

  return (
    <main className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-icon"><Anchor size={20} color="#fff" /></div>
          <div>
            <h1>BackwaterGuard</h1>
            <p>Collision Avoidance</p>
          </div>
        </div>
        <nav>
          {tabs.map(tab => {
            const Icon = tab.icon;
            return (
              <button key={tab.id} className={active === tab.id ? "active" : ""} onClick={() => setActive(tab.id)}>
                <Icon size={18} />
                <span>{tab.label}</span>
                {tab.id === "collision" && dangerAlerts > 0 && (
                  <span className="nav-badge">{dangerAlerts}</span>
                )}
              </button>
            );
          })}
        </nav>
        <div className="sidebar-footer">
          <div className="sys-stats">
            <div className="sys-stat"><span>Fleet</span><strong>{Array.isArray(data.latest) ? data.latest.length : 0}</strong></div>
            <div className="sys-stat"><span>Alerts</span><strong>{Array.isArray(data.alerts) ? data.alerts.length : 0}</strong></div>
            <div className="sys-stat"><span>Preds</span><strong>{Array.isArray(data.predictions) ? data.predictions.length : 0}</strong></div>
          </div>
        </div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div className="topbar-left">
            <ActiveIcon size={18} className="tab-icon" />
            <h2>{activeTab?.label}</h2>
          </div>
          <div className="topbar-right">
            <WeatherWidget weather={data.weather} />
            <div className="divider" />
            <Clock12 />
            <StatusIndicator error={data.error} />
          </div>
        </header>

        <div className="view-content">
          {active === "map"       && <LiveMap center={center} latest={data.latest} predictions={groupedPredictions} telemetry={data.telemetry} />}
          {active === "collision" && <PredictiveCollision center={center} latest={data.latest} telemetry={data.telemetry} groupedPredictions={groupedPredictions} predictions={data.predictions} metrics={data.metrics} recommendations={data.recommendations} />}
          {active === "analytics" && <Analytics evaluation={data.evaluation} timeline={data.timeline} telemetry={data.telemetry} />}
          {active === "logs"      && <Logs alerts={data.alerts} telemetry={data.telemetry} />}
        </div>
      </section>
    </main>
  );
}

const BOAT_COLORS = ["#38BDF8", "#A78BFA", "#FBBF24", "#34D399"];

function LiveMap({ center, latest = [], predictions = {}, telemetry = [] }) {
  const [showPreds, setShowPreds] = useState(true);

  async function triggerPrediction(boatId) {
    await fetch(`${API_BASE}/predict`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ boat_id: boatId }),
    });
  }

  const trails = useMemo(() => groupPath(telemetry, "lat", "lon"), [telemetry]);
  const safeLatest = Array.isArray(latest) ? latest : [];

  const collisionPairs = useMemo(() => {
    const pairs = [];
    for (let i = 0; i < safeLatest.length; i++)
      for (let j = i + 1; j < safeLatest.length; j++) {
        const d = haversine(safeLatest[i].lat, safeLatest[i].lon, safeLatest[j].lat, safeLatest[j].lon);
        if (d < 80) pairs.push({ a: safeLatest[i], b: safeLatest[j], dist: d });
      }
    return pairs;
  }, [safeLatest]);

  return (
    <div className="map-wrap">
      <div className="map-controls">
        <button className={showPreds ? "active" : ""} onClick={() => setShowPreds(!showPreds)}>
          <Layers size={14} /> AI Predictions
        </button>
        {safeLatest.map(boat => (
          <button key={`pred-btn-${boat.boat_id}`} onClick={() => triggerPrediction(boat.boat_id)}>
            <Navigation size={14} /> Scan {boat.boat_id}
          </button>
        ))}
      </div>

      <MapContainer center={center} zoom={16} scrollWheelZoom className="leaflet-map">
        <TileLayer attribution="&copy; CartoDB" url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png" />

        {safeLatest.map((boat, idx) => {
          const trail = trails[boat.boat_id] || [];
          const color = BOAT_COLORS[idx % BOAT_COLORS.length];
          return trail.length > 1 ? <Polyline key={`trail-${boat.boat_id}`} positions={trail.slice(-30)} pathOptions={{ color, weight: 2, opacity: 0.3 }} /> : null;
        })}

        {showPreds && safeLatest.map((boat, idx) => {
          const pts = predictions[boat.boat_id] || [];
          if (pts.length < 2) return null;

          const color = BOAT_COLORS[idx % BOAT_COLORS.length];
          const solidPath = pts.slice(0, 5);
          const uncertainPath = pts.slice(4);

          return (
            <React.Fragment key={`pred-${boat.boat_id}`}>
              <Polyline positions={solidPath.map(p => [p[0], p[1]])} pathOptions={{ color, weight: 3, opacity: 0.9 }} />
              <Polyline positions={uncertainPath.map(p => [p[0], p[1]])} pathOptions={{ color, weight: 2, opacity: 0.4, dashArray: "5 5" }} />
              {uncertainPath.map((p, i) => (
                <Circle key={`cone-${boat.boat_id}-${i}`} center={[p[0], p[1]]} radius={(i + 1) * 3.5} pathOptions={{ color: 'transparent', fillColor: color, fillOpacity: Math.max(0.02, 0.15 * (p[2] || 0.5)) }} />
              ))}
            </React.Fragment>
          );
        })}

        {collisionPairs.map(({ a, b }, i) => (
          <Circle key={`col-${i}`} center={[(a.lat + b.lat) / 2, (a.lon + b.lon) / 2]} radius={50} pathOptions={{ color: "#EF4444", fillColor: "#EF4444", fillOpacity: 0.15, weight: 2, dashArray: "4 6" }} />
        ))}

        {safeLatest.map(boat => {
          const rc = riskClass(boat.risk);
          return (
            <Marker key={boat.boat_id} position={[boat.lat, boat.lon]} icon={makeBoatIcon(Number(boat.heading || 0), rc)}>
              <Popup className="dark-popup">
                <strong>{boat.boat_id}</strong><br />
                Speed: {Number(boat.speed).toFixed(2)} m/s<br />
                Risk: <span className={`text-${rc}`}>{Number(boat.risk).toFixed(3)}</span>
              </Popup>
            </Marker>
          );
        })}
      </MapContainer>

      <div className="fleet-strip">
        {safeLatest.map((boat, idx) => (
          <div className="fleet-item" key={boat.boat_id}>
            <div className="fleet-boat-arrow" style={{ color: BOAT_COLORS[idx % BOAT_COLORS.length] }}>
              <svg width="20" height="20" viewBox="0 0 32 32" style={{ transform: `rotate(${Number(boat.heading || 0)}deg)` }}>
                <polygon points="16,3 24,26 16,21 8,26" fill="currentColor" />
              </svg>
            </div>
            <div className="fleet-meta">
              <div className="fleet-id">{boat.boat_id}</div>
              <div className="fleet-stats">{Number(boat.speed || 0).toFixed(1)} m/s · {Number(boat.heading || 0).toFixed(0)}°</div>
            </div>
            <span className={`pill ${riskClass(boat.risk)}`}>{Number(boat.risk).toFixed(2)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function PredictiveCollision({ center, latest = [], telemetry = [], groupedPredictions = {}, predictions = [], metrics = {}, recommendations = [] }) {
  const safeLatest = Array.isArray(latest) ? latest : [];
  const [boatA, boatB] = safeLatest;
  const actualPaths = useMemo(() => groupPath(telemetry, "lat", "lon"), [telemetry]);
  const predictedPaths = groupedPredictions;

  const distance = useMemo(() => boatA && boatB ? haversine(boatA.lat, boatA.lon, boatB.lat, boatB.lon) : 0, [boatA, boatB]);
  const relativeSpeed = useMemo(() => boatA && boatB ? Math.max(0.1, Math.abs(boatA.speed - boatB.speed)) : 0.1, [boatA, boatB]);
  const ttc = distance ? distance / relativeSpeed : null;
  const futureDistance = useMemo(() => futureSeparation(predictedPaths[boatA?.boat_id], predictedPaths[boatB?.boat_id]), [predictedPaths, boatA, boatB]);
  
  const risk = useMemo(() => boatA && boatB ? Math.max(Number(boatA.risk || 0), Number(boatB.risk || 0)) : 0, [boatA, boatB]);
  const riskState = riskClass(risk);
  const latestRec = Array.isArray(recommendations) ? recommendations[0] : null;

  return (
    <div className="collision-layout">
      <div className="map-wrap compact">
        <MapContainer center={center} zoom={16} scrollWheelZoom className="leaflet-map">
          <TileLayer attribution="&copy; CartoDB" url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png" />
          {Object.entries(actualPaths).map(([id, pts], idx) => (
            <Polyline key={`a-${id}`} positions={pts.slice(-30)} pathOptions={{ color: BOAT_COLORS[idx % BOAT_COLORS.length], weight: 2.5, opacity: 0.4 }} />
          ))}
          {Object.entries(predictedPaths).map(([id, pts], idx) => {
            if (pts.length < 2) return null;
            const color = BOAT_COLORS[idx % BOAT_COLORS.length];
            const solidPath = pts.slice(0, 5);
            const uncertainPath = pts.slice(4);

            return (
              <React.Fragment key={`p-${id}`}>
                <Polyline positions={solidPath.map(p => [p[0], p[1]])} pathOptions={{ color, weight: 3, opacity: 0.9 }} />
                <Polyline positions={uncertainPath.map(p => [p[0], p[1]])} pathOptions={{ color, weight: 2, opacity: 0.4, dashArray: "5 5" }} />
                {uncertainPath.map((p, i) => (
                  <Circle key={`cone-${id}-${i}`} center={[p[0], p[1]]} radius={(i + 1) * 3.5} pathOptions={{ color: 'transparent', fillColor: color, fillOpacity: Math.max(0.02, 0.15 * (p[2] || 0.5)) }} />
                ))}
              </React.Fragment>
            );
          })}
          {safeLatest.map(boat => (
            <Marker key={boat.boat_id} position={[boat.lat, boat.lon]} icon={makeBoatIcon(Number(boat.heading || 0), riskClass(boat.risk))} />
          ))}
          {risk > 0.7 && boatA && boatB && (
            <Circle center={[(boatA.lat + boatB.lat) / 2, (boatA.lon + boatB.lon) / 2]} radius={60} pathOptions={{ color: "#EF4444", fillColor: "#EF4444", fillOpacity: 0.15, weight: 2, dashArray: "4 6" }} />
          )}
        </MapContainer>
      </div>

      <div className="collision-panel">
        <div className={`action-banner ${recommendationTone(latestRec?.action)}`}>
          <span className="banner-label">Recommended Action</span>
          <h2 className="banner-action">{latestRec?.action || "MAINTAIN COURSE"}</h2>
        </div>

        <div className="threat-summary">
          <div className="vessel-vs">
            <div className="vessel-id">{boatA?.boat_id || "Vessel A"}</div>
            <span className="vs">vs</span>
            <div className="vessel-id">{boatB?.boat_id || "Vessel B"}</div>
          </div>
          
          <div className="critical-metrics">
            <div className="crit-box">
              <span>Time to Impact</span>
              <strong className={ttcColorState(ttc)}>{ttc === null ? "N/A" : `${ttc.toFixed(1)}s`}</strong>
            </div>
            <div className="crit-box">
              <span>Current Distance</span>
              <strong>{distance ? `${distance.toFixed(0)}m` : "—"}</strong>
            </div>
          </div>
        </div>

        <div className="panel-section-label">AI Threat Analysis</div>
        <Metric label="Risk Score" value={`${(risk * 100).toFixed(0)}%`} tone={riskState} />
        <div className="risk-meter-wrap">
          <div className="risk-meter-label"><span>Safe</span><span>Critical</span></div>
          <div className={`risk-meter ${riskState}`}><span style={{ width: `${Math.min(100, risk * 100)}%` }} /></div>
        </div>
        <Metric label="AI Confidence" value={averageConfidence(predictions) ? `${(averageConfidence(predictions) * 100).toFixed(0)}%` : "—"} />

        <div className="tech-details">
          <div className="panel-section-label" style={{ marginTop: 16 }}>Telemetry</div>
          <Metric label="Est. CPA (Distance)" value={futureDistance ? `${futureDistance.toFixed(1)} m` : "—"} />
          <Metric label="Boat A Speed" value={boatA ? `${Number(boatA.speed).toFixed(2)} m/s` : "—"} />
          <Metric label="Boat B Speed" value={boatB ? `${Number(boatB.speed).toFixed(2)} m/s` : "—"} />
        </div>
      </div>
    </div>
  );
}

function Analytics({ evaluation = {}, timeline = [], telemetry = [] }) {
  const cards = [
    ["Alerts Sent", evaluation.alerts || 0],
    ["Predictions", evaluation.predictions || 0],
    ["Collisions",  evaluation.collisions || 0],
    ["Precision",   formatPercent(evaluation.precision)],
    ["Latency",     `${evaluation.latency || 0} ms`],
  ];
  const safeTimeline = Array.isArray(timeline) ? timeline : [];
  const safeTelemetry = Array.isArray(telemetry) ? telemetry : [];

  return (
    <div className="analytics-layout scroll-content">
      <div className="eval-cards">
        {cards.map(([label, value]) => (
          <div className="eval-card" key={label}><span>{label}</span><strong>{value}</strong></div>
        ))}
      </div>
      
      <div className="panel">
        <h3>Collision Timeline Log</h3>
        <div className="timeline-chart">
          {safeTimeline.slice(-80).map((point, i) => (
            <div className="timeline-row" key={`${point.t}-${i}`}>
              <span className="time-col">{formatValue(point.t)}</span>
              <div className="timeline-track">
                <i className={`bg-${riskClass(point.risk)}`} style={{ width: `${Math.max(4, Math.min(100, Number(point.risk || 0) * 100))}%` }} />
              </div>
              <strong className={`text-${riskClass(point.risk)}`}>{point.alert || "SAFE"}</strong>
            </div>
          ))}
          {safeTimeline.length === 0 && <p className="empty">No timeline data yet.</p>}
        </div>
      </div>

      <DataTable title="Live Telemetry Log" rows={safeTelemetry} columns={["boat_id", "timestamp", "lat", "lon", "speed", "heading", "risk"]} />
    </div>
  );
}

function Logs({ alerts = [], telemetry = [] }) {
  const safeAlerts = Array.isArray(alerts) ? alerts : [];
  const recentTelemetry = useMemo(() => (Array.isArray(telemetry) ? telemetry.slice(0, 40) : []), [telemetry]);
  return (
    <div className="logs-layout scroll-content">
      <div className="alerts-wrap panel">
        <h3>System Alerts</h3>
        <div className="alerts-scroll">
          {safeAlerts.length === 0 && <p className="empty">No alerts — all clear.</p>}
          {safeAlerts.map(alert => (
            <article key={alert.id} className={`alert ${alert.severity?.toLowerCase()}`}>
              <AlertTriangle size={18} className="alert-icon" />
              <div className="alert-body">
                <strong>{alert.severity} · {alert.boat_id}</strong>
                <p>{alert.message}</p>
              </div>
              <span className="alert-time">{formatValue(alert.timestamp)}</span>
            </article>
          ))}
        </div>
      </div>
      <DataTable title="Historical Telemetry" rows={recentTelemetry} columns={["boat_id", "timestamp", "lat", "lon", "risk"]} />
    </div>
  );
}

function Metric({ label, value, tone = "" }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong className={`text-${tone}`}>{value}</strong>
    </div>
  );
}

const DataTable = memo(function DataTable({ title, rows, columns }) {
  return (
    <div className="table-panel">
      <h3>{title}</h3>
      <div className="table-scroll">
        <table>
          <thead><tr>{columns.map(col => <th key={col}>{col.toUpperCase()}</th>)}</tr></thead>
          <tbody>
            {rows.map((row, idx) => (
              <tr key={row.id || `${row.boat_id}-${idx}`}>
                {columns.map(col => <td key={col}>{formatValue(row[col])}</td>)}
              </tr>
            ))}
            {rows.length === 0 && (
              <tr><td colSpan={columns.length} style={{ textAlign: "center", color: "var(--text-dim)", padding: "24px" }}>No data available</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
});

function formatValue(v) {
  if (typeof v === "number") return Math.abs(v) > 1000 ? v.toFixed(0) : v.toFixed(5).replace(/0+$/, "").replace(/\.$/, "");
  return v ?? "";
}
function formatPercent(v)             { return v == null ? "0%" : `${(Number(v) * 100).toFixed(1)}%`; }
function groupPath(rows, latKey, lonKey) {
  if (!Array.isArray(rows)) return {};
  return rows.reduce((acc, row) => {
    if (row[latKey] == null || row[lonKey] == null) return acc;
    acc[row.boat_id] ||= [];
    acc[row.boat_id].push([row[latKey], row[lonKey]]);
    return acc;
  }, {});
}
function haversine(lat1, lon1, lat2, lon2) {
  const R = 6371000, dLat = (lat2 - lat1) * Math.PI / 180, dLon = (lon2 - lon1) * Math.PI / 180;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}
function futureSeparation(pathA = [], pathB = []) {
  if (!Array.isArray(pathA) || !Array.isArray(pathB)) return 0;
  let min = 0;
  pathA.slice(0, 5).forEach((p, i) => {
    const o = pathB[i]; if (!o) return;
    const d = haversine(p[0], p[1], o[0], o[1]);
    min = min === 0 ? d : Math.min(min, d);
  });
  return min;
}
function averageConfidence(preds)   { if (!Array.isArray(preds) || !preds.length) return 0; return preds.reduce((s, p) => s + Number(p.confidence || 0), 0) / preds.length; }
function ttcColorState(ttc)         { if (!ttc || ttc > 20) return "safe"; if (ttc > 10) return "warning"; return "danger"; }
function recommendationTone(a = "") { if (a?.startsWith("HARD") || a === "STOP") return "danger"; if (a === "SLOW_DOWN" || a?.startsWith("TURN")) return "warning"; return "safe"; }

createRoot(document.getElementById("root")).render(<Shell />);