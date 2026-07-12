import { useEffect, useState } from "react";
import { getHealth, type HealthResponse } from "../api/client";

/**
 * Connection-status pill rendered in the sidebar. Polls `/healthz` every
 * 15 seconds (well below the backend's 10s TTL cache) so the operator gets
 * live feedback without hammering the API.
 */
export function StatusPill() {
  const [h, setH] = useState<HealthResponse | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const fetchOnce = async () => {
      try {
        const r = await getHealth();
        if (!cancelled) setH(r);
      } catch (err) {
        if (!cancelled)
          setH({ overall: "down", components: {}, error: String(err) });
      }
    };
    fetchOnce();
    const t = window.setInterval(fetchOnce, 15_000);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
  }, [tick]);

  // Re-fetch on manual click.
  const refresh = () => setTick((n) => n + 1);

  const state = (h?.overall ?? "unknown") as
    | "up"
    | "degraded"
    | "down"
    | "unknown";
  const label =
    state === "up"
      ? "connected"
      : state === "degraded"
        ? "degraded"
        : state === "down"
          ? "unreachable"
          : "checking…";
  const comps = h?.components ?? {};

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span className={`status-pill ${state}`}>
          <span className="dot" />
          API: {label}
        </span>
        <button onClick={refresh} style={{ padding: "2px 8px", fontSize: 12 }}>
          ↻
        </button>
      </div>
      {Object.keys(comps).length > 0 && (
        <div className="components">
          {Object.entries(comps).map(([name, state]) => (
            <div className="row" key={name}>
              <span>{name}</span>
              <span>{state === "up" ? "✓" : "✗"}</span>
            </div>
          ))}
        </div>
      )}
      {h?.error && <div className="notice err">{h.error}</div>}
    </div>
  );
}