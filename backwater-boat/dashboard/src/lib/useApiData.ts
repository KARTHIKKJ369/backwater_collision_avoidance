import { useEffect, useState } from "react";
import type { Alert, Boat, Prediction, Recommendation, Weather } from "./maritime";

export const API_BASE =
  (import.meta.env.VITE_API_BASE as string | undefined) || "http://localhost:8000";

const FAST_MS = 1500;
const SLOW_MS = 8000;

type TelemetryRow = Boat;

export type ApiData = {
  boats: unknown[];
  telemetry: TelemetryRow[];
  latest: Boat[];
  alerts: Alert[];
  predictions: Prediction[];
  metrics: Record<string, unknown>;
  evaluation: Record<string, unknown>;
  timeline: { t?: string; risk?: number; alert?: string }[];
  recommendations: Recommendation[];
  weather: Weather | null;
  error: string;
};

const empty: ApiData = {
  boats: [],
  telemetry: [],
  latest: [],
  alerts: [],
  predictions: [],
  metrics: {},
  evaluation: {},
  timeline: [],
  recommendations: [],
  weather: null,
  error: "",
};

async function safeJson<T>(url: string, fallback: T): Promise<T> {
  try {
    const r = await fetch(url);
    if (!r.ok) return fallback;
    return (await r.json()) as T;
  } catch {
    return fallback;
  }
}

export function useApiData(): ApiData {
  const [fast, setFast] = useState({
    boats: [] as unknown[],
    telemetry: [] as TelemetryRow[],
    latest: [] as Boat[],
    alerts: [] as Alert[],
    predictions: [] as Prediction[],
    metrics: {} as Record<string, unknown>,
  });
  const [slow, setSlow] = useState({
    evaluation: {} as Record<string, unknown>,
    timeline: [] as { t?: string; risk?: number; alert?: string }[],
    recommendations: [] as Recommendation[],
  });
  const [weather, setWeather] = useState<Weather | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;

    async function loadFast() {
      try {
        const [boats, telemetry, latest, alerts, predictions, metrics] = await Promise.all([
          fetch(`${API_BASE}/boats`).then((r) => r.json()),
          fetch(`${API_BASE}/telemetry?limit=120`).then((r) => r.json()),
          fetch(`${API_BASE}/telemetry/latest`).then((r) => r.json()),
          fetch(`${API_BASE}/alerts?limit=50`).then((r) => r.json()),
          fetch(`${API_BASE}/predictions?limit=50`).then((r) => r.json()),
          fetch(`${API_BASE}/metrics`).then((r) => r.json()),
        ]);
        if (!alive) return;
        setFast({ boats, telemetry, latest, alerts, predictions, metrics });
        setError("");
      } catch {
        if (alive) setError("Offline");
      }
    }

    async function loadSlow() {
      const [evaluation, timeline, recommendations, weatherData] = await Promise.all([
        safeJson<Record<string, unknown>>(`${API_BASE}/evaluation`, {}),
        safeJson<{ t?: string; risk?: number; alert?: string }[]>(`${API_BASE}/timeline`, []),
        safeJson<Recommendation[]>(`${API_BASE}/recommendations?limit=20`, []),
        safeJson<Weather | null>(`${API_BASE}/weather?lat=9.591&lon=76.522`, null),
      ]);
      if (!alive) return;
      setSlow({ evaluation, timeline, recommendations });
      if (weatherData) setWeather(weatherData);
    }

    loadFast();
    loadSlow();
    const tFast = setInterval(loadFast, FAST_MS);
    const tSlow = setInterval(loadSlow, SLOW_MS);
    return () => {
      alive = false;
      clearInterval(tFast);
      clearInterval(tSlow);
    };
  }, []);

  return { ...fast, ...slow, weather, error };
}
