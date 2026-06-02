import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { AlertTriangle, Clock, Map, Radio, Route, Table2 } from "lucide-react";
import { MapContainer, Marker, Polyline, Popup, TileLayer } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import "./styles.css";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

const boatIcon = new L.DivIcon({
  className: "boat-marker",
  html: "<span></span>",
  iconSize: [18, 18],
  iconAnchor: [9, 9],
});

const tabs = [
  { id: "map", label: "Live Map", icon: Map },
  { id: "collision", label: "Predictive Collision", icon: AlertTriangle },
  { id: "prediction", label: "Prediction", icon: Route },
  { id: "alerts", label: "Alerts", icon: AlertTriangle },
  { id: "telemetry", label: "Telemetry", icon: Table2 },
  { id: "history", label: "History", icon: Clock },
];

function useApiData() {
  const [state, setState] = useState({ boats: [], telemetry: [], latest: [], alerts: [], predictions: [], metrics: {} });
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        const [boats, telemetry, latest, alerts, predictions, metrics] = await Promise.all([
          fetch(`${API_BASE}/boats`).then((r) => r.json()),
          fetch(`${API_BASE}/telemetry?limit=120`).then((r) => r.json()),
          fetch(`${API_BASE}/telemetry/latest`).then((r) => r.json()),
          fetch(`${API_BASE}/alerts?limit=50`).then((r) => r.json()),
          fetch(`${API_BASE}/predictions?limit=50`).then((r) => r.json()),
          fetch(`${API_BASE}/metrics`).then((r) => r.json()),
        ]);
        if (alive) {
          setState({ boats, telemetry, latest, alerts, predictions, metrics });
          setError("");
        }
      } catch (exc) {
        if (alive) setError("Backend offline");
      }
    }
    load();
    const timer = setInterval(load, 1500);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);

  return { ...state, error };
}

function riskClass(risk = 0) {
  if (risk > 0.7) return "danger";
  if (risk >= 0.4) return "warning";
  return "safe";
}

function Shell() {
  const [active, setActive] = useState("map");
  const data = useApiData();
  const center = data.latest[0] ? [data.latest[0].lat, data.latest[0].lon] : [9.591, 76.522];
  const groupedPredictions = useMemo(() => {
    return data.predictions.reduce((acc, point) => {
      acc[point.boat_id] ||= [];
      acc[point.boat_id].push([point.pred_lat, point.pred_lon]);
      return acc;
    }, {});
  }, [data.predictions]);

  const ActiveIcon = tabs.find((tab) => tab.id === active)?.icon || Radio;

  return (
    <main className="app">
      <aside className="sidebar">
        <div className="brand">
          <Radio size={24} />
          <div>
            <h1>Backwater Boat</h1>
            <p>Collision Avoidance</p>
          </div>
        </div>
        <nav>
          {tabs.map((tab) => {
            const Icon = tab.icon;
            return (
              <button key={tab.id} className={active === tab.id ? "active" : ""} onClick={() => setActive(tab.id)}>
                <Icon size={18} />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </nav>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <ActiveIcon size={20} />
            <h2>{tabs.find((tab) => tab.id === active)?.label}</h2>
          </div>
          <span className={data.error ? "status offline" : "status"}>{data.error || "Live"}</span>
        </header>

        {active === "map" && <LiveMap center={center} latest={data.latest} predictions={groupedPredictions} />}
        {active === "collision" && (
          <PredictiveCollision
            center={center}
            latest={data.latest}
            telemetry={data.telemetry}
            predictions={data.predictions}
            metrics={data.metrics}
          />
        )}
        {active === "prediction" && <Prediction latest={data.latest} predictions={data.predictions} />}
        {active === "alerts" && <Alerts alerts={data.alerts} />}
        {active === "telemetry" && <Telemetry rows={data.telemetry} />}
        {active === "history" && <History telemetry={data.telemetry} alerts={data.alerts} />}
      </section>
    </main>
  );
}

function PredictiveCollision({ center, latest, telemetry, predictions, metrics }) {
  const [boatA, boatB] = latest;
  const actualPaths = groupPath(telemetry, "lat", "lon");
  const predictedPaths = groupPath(predictions, "pred_lat", "pred_lon");
  const distance = boatA && boatB ? haversine(boatA.lat, boatA.lon, boatB.lat, boatB.lon) : 0;
  const relativeSpeed = boatA && boatB ? Math.max(0.1, Math.abs(boatA.speed - boatB.speed)) : 0.1;
  const ttc = distance ? distance / relativeSpeed : 0;
  const futureDistance = futureSeparation(predictedPaths[boatA?.boat_id], predictedPaths[boatB?.boat_id]);
  const alertState = stateForFutureDistance(futureDistance);
  const risk = boatA && boatB ? Math.max(Number(boatA.risk || 0), Number(boatB.risk || 0)) : 0;

  return (
    <div className="collision-layout">
      <section className="collision-map">
        <MapContainer center={center} zoom={15} scrollWheelZoom className="map compact">
          <TileLayer attribution="&copy; OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
          {latest.map((boat) => (
            <Marker key={boat.boat_id} position={[boat.lat, boat.lon]} icon={boatIcon}>
              <Popup>{boat.boat_id}</Popup>
            </Marker>
          ))}
          {Object.entries(actualPaths).map(([boatId, points]) => (
            <Polyline key={`actual-${boatId}`} positions={points} pathOptions={{ color: "#0f766e", weight: 4 }} />
          ))}
          {Object.entries(predictedPaths).map(([boatId, points]) => (
            <Polyline key={`pred-${boatId}`} positions={points} pathOptions={{ color: "#e11d48", weight: 3, dashArray: "6 8" }} />
          ))}
        </MapContainer>
      </section>
      <aside className="collision-panel">
        <Metric label="Boat A" value={boatA?.boat_id || "-"} />
        <Metric label="Boat B" value={boatB?.boat_id || "-"} />
        <Metric label="Current Position" value={boatA ? `${boatA.lat}, ${boatA.lon}` : "-"} />
        <Metric label="Predicted Position" value={predictedPaths[boatA?.boat_id]?.[0]?.join(", ") || "-"} />
        <div className="risk-meter">
          <span style={{ width: `${Math.min(100, risk * 100)}%` }}></span>
        </div>
        <Metric label="Time To Collision" value={ttc ? `${ttc.toFixed(1)} s` : "-"} />
        <Metric label="Future Distance" value={futureDistance ? `${futureDistance.toFixed(1)} m` : "-"} />
        <Metric label="Alert State" value={alertState} />
        <Metric label="Predictions" value={`${metrics.prediction_executed || 0} run / ${metrics.prediction_skipped || 0} skipped`} />
        <Metric label="Alerts Total" value={metrics.alerts_total || 0} />
      </aside>
    </div>
  );
}

function Metric({ label, value }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function LiveMap({ center, latest, predictions }) {
  return (
    <div className="map-wrap">
      <MapContainer center={center} zoom={15} scrollWheelZoom className="map">
        <TileLayer attribution="&copy; OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
        {latest.map((boat) => (
          <Marker key={boat.boat_id} position={[boat.lat, boat.lon]} icon={boatIcon}>
            <Popup>
              <strong>{boat.boat_id}</strong>
              <br />
              Speed {boat.speed} m/s
              <br />
              Heading {boat.heading} deg
              <br />
              Risk {boat.risk}
            </Popup>
          </Marker>
        ))}
        {Object.entries(predictions).map(([boatId, points]) => (
          <Polyline key={boatId} positions={points} pathOptions={{ color: "#e11d48", weight: 3, dashArray: "6 8" }} />
        ))}
      </MapContainer>
      <div className="fleet-strip">
        {latest.map((boat) => (
          <div className="fleet-item" key={boat.boat_id}>
            <strong>{boat.boat_id}</strong>
            <span className={`pill ${riskClass(boat.risk)}`}>{Number(boat.risk).toFixed(2)}</span>
          </div>
        ))}
      </div>
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
    <div className="panel-grid">
      <section className="panel">
        <h3>Prediction Trigger</h3>
        <div className="boat-actions">
          {latest.map((boat) => (
            <button key={boat.boat_id} onClick={() => trigger(boat.boat_id)}>
              <Route size={16} />
              <span>{boat.boat_id}</span>
            </button>
          ))}
        </div>
      </section>
      <DataTable
        title="Future Positions"
        rows={predictions}
        columns={["boat_id", "timestamp", "pred_lat", "pred_lon", "confidence"]}
      />
    </div>
  );
}

function Alerts({ alerts }) {
  return (
    <section className="alerts">
      {alerts.length === 0 && <p className="empty">No alerts yet.</p>}
      {alerts.map((alert) => (
        <article key={alert.id} className={`alert ${alert.severity.toLowerCase()}`}>
          <AlertTriangle size={18} />
          <div>
            <strong>{alert.severity} · {alert.boat_id}</strong>
            <p>{alert.message}</p>
          </div>
        </article>
      ))}
    </section>
  );
}

function Telemetry({ rows }) {
  return <DataTable title="Telemetry" rows={rows} columns={["boat_id", "timestamp", "lat", "lon", "speed", "heading", "obstacle", "risk"]} />;
}

function History({ telemetry, alerts }) {
  return (
    <div className="panel-grid">
      <DataTable title="Recent Telemetry" rows={telemetry.slice(0, 40)} columns={["boat_id", "timestamp", "lat", "lon", "risk"]} />
      <DataTable title="Recent Alerts" rows={alerts} columns={["boat_id", "timestamp", "severity", "message"]} />
    </div>
  );
}

function DataTable({ title, rows, columns }) {
  return (
    <section className="panel table-panel">
      <h3>{title}</h3>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map((row, idx) => (
              <tr key={row.id || `${row.boat_id}-${idx}`}>
                {columns.map((column) => <td key={column}>{formatValue(row[column])}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function formatValue(value) {
  if (typeof value === "number") return Math.abs(value) > 1000 ? value.toFixed(0) : value.toFixed(5).replace(/0+$/, "").replace(/\.$/, "");
  return value ?? "";
}

function groupPath(rows, latKey, lonKey) {
  return rows.reduce((acc, row) => {
    if (row[latKey] == null || row[lonKey] == null) return acc;
    acc[row.boat_id] ||= [];
    acc[row.boat_id].push([row[latKey], row[lonKey]]);
    return acc;
  }, {});
}

function haversine(lat1, lon1, lat2, lon2) {
  const radius = 6371000;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.sin(dLon / 2) ** 2;
  return 2 * radius * Math.asin(Math.sqrt(a));
}

function futureSeparation(pathA = [], pathB = []) {
  let min = 0;
  pathA.slice(0, 5).forEach((point, index) => {
    const other = pathB[index];
    if (!other) return;
    const distance = haversine(point[0], point[1], other[0], other[1]);
    min = min === 0 ? distance : Math.min(min, distance);
  });
  return min;
}

function stateForFutureDistance(distance) {
  if (!distance || distance > 100) return "SAFE";
  if (distance >= 50) return "WARNING";
  return "DANGER";
}

createRoot(document.getElementById("root")).render(<Shell />);
