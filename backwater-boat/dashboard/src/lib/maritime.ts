export type Boat = {
  boat_id: string;
  lat: number;
  lon: number;
  speed: number;
  heading: number;
  risk: number;
  timestamp?: string;
};

export type Prediction = {
  boat_id: string;
  pred_lat: number;
  pred_lon: number;
  confidence: number;
};

export type Alert = {
  id: string | number;
  severity?: string;
  type?: string;
  message?: string;
  timestamp?: string;
  boat_id?: string;
};

export type Weather = {
  description: string;
  condition_id?: number;
  wind_speed: number;
  visibility_m: number;
  temperature?: number;
};

export type Recommendation = { action?: string; reason?: string; timestamp?: string };

export type RiskLevel = "safe" | "warning" | "danger";

export function riskClass(risk = 0): RiskLevel {
  if (risk > 0.7) return "danger";
  if (risk >= 0.4) return "warning";
  return "safe";
}

export function recommendationTone(action?: string): RiskLevel {
  if (!action) return "safe";
  const a = action.toUpperCase();
  if (a.includes("STOP") || a.includes("EMERGENCY")) return "danger";
  if (a.includes("SLOW") || a.includes("TURN")) return "warning";
  return "safe";
}

export function haversine(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371000;
  const toRad = (x: number) => (x * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

export function groupPath<T extends Record<string, unknown>>(
  rows: T[] | undefined,
  latKey: string,
  lonKey: string,
): Record<string, [number, number][]> {
  if (!Array.isArray(rows)) return {};
  const out: Record<string, [number, number][]> = {};
  for (const r of rows) {
    const id = String((r as Record<string, unknown>).boat_id ?? "");
    if (!id) continue;
    const lat = Number((r as Record<string, unknown>)[latKey]);
    const lon = Number((r as Record<string, unknown>)[lonKey]);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) continue;
    (out[id] ||= []).push([lat, lon]);
  }
  return out;
}

export function averageConfidence(preds: Prediction[] | undefined): number {
  if (!Array.isArray(preds) || preds.length === 0) return 0;
  const sum = preds.reduce((acc, p) => acc + Number(p.confidence || 0), 0);
  return sum / preds.length;
}

export function futureSeparation(
  a?: [number, number, number][],
  b?: [number, number, number][],
): number | null {
  if (!a || !b || a.length === 0 || b.length === 0) return null;
  const n = Math.min(a.length, b.length);
  let min = Infinity;
  for (let i = 0; i < n; i++) {
    const d = haversine(a[i][0], a[i][1], b[i][0], b[i][1]);
    if (d < min) min = d;
  }
  return Number.isFinite(min) ? min : null;
}

export function ttcColorState(ttc: number | null): string {
  if (ttc === null) return "text-zinc-100";
  if (ttc < 15) return "text-danger";
  if (ttc < 45) return "text-warning";
  return "text-safe";
}

export function formatPercent(v: unknown): string {
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  return `${(n * 100).toFixed(1)}%`;
}

export function formatValue(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return v.toFixed(2);
  if (typeof v === "string") return v;
  try { return JSON.stringify(v); } catch { return String(v); }
}
