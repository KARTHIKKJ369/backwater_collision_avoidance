import { createFileRoute } from "@tanstack/react-router";
import { Suspense, lazy, useEffect, useState } from "react";

// Leaflet touches `window` at module scope. Defer the entire dashboard until after mount.
const Shell = lazy(() => import("@/components/dashboard/Shell"));

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "BackwaterGuard — Collision Avoidance Console" },
      {
        name: "description",
        content:
          "Real-time AI maritime safety dashboard: live vessel telemetry, LSTM trajectory forecasting, CPA/TTC risk scoring, and collision alerts for backwater navigation.",
      },
      { property: "og:title", content: "BackwaterGuard — Collision Avoidance Console" },
      {
        property: "og:description",
        content:
          "Live fleet map, AI risk scoring, and recommended evasive actions for backwater boats.",
      },
    ],
  }),
  component: Index,
});

function Index() {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  if (!mounted) return <Splash />;

  return (
    <Suspense fallback={<Splash />}>
      <Shell />
    </Suspense>
  );
}

function Splash() {
  return (
    <div className="flex h-screen w-full items-center justify-center bg-canvas text-zinc-400">
      <div className="flex flex-col items-center gap-3">
        <div className="size-10 rounded-md bg-cyan/15 ring-1 ring-cyan/30 flex items-center justify-center shadow-[0_0_20px_rgba(6,182,212,0.25)]">
          <span className="text-cyan font-bold text-sm">BG</span>
        </div>
        <div className="text-[11px] font-mono uppercase tracking-widest text-zinc-500">
          Initializing BackwaterGuard…
        </div>
      </div>
    </div>
  );
}
