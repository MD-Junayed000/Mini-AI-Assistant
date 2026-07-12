import { useEffect, useState } from "react";
import { getHealth, type HealthResponse } from "../api/client";

const POLL_MS = 15_000;

type State = "up" | "degraded" | "down" | "checking";

const STATE_LABEL: Record<State, string> = {
  up: "up",
  degraded: "degraded",
  down: "down",
  checking: "Checking…",
};

function overallToState(h: HealthResponse | null): State {
  if (!h) return "checking";
  if (h.overall === "up") return "up";
  if (h.overall === "degraded") return "degraded";
  if (h.overall === "down") return "down";
  return "checking";
}

interface Props {
  /** When true, also render the per-component list (used inside the popup). */
  detailed?: boolean;
  /** When true, render only the inline state word (used inside the header button). */
  compact?: boolean;
}

export function StatusPill({ detailed = false, compact = false }: Props) {
  const [h, setH] = useState<HealthResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    const fetchOnce = async () => {
      try {
        const r = await getHealth();
        if (!cancelled) setH(r);
      } catch (err) {
        if (!cancelled) setH({ overall: "down", components: {}, error: String(err) });
      }
    };
    fetchOnce();
    const t = window.setInterval(fetchOnce, POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
  }, []);

  const refresh = () => {
    void (async () => {
      try {
        setH(await getHealth());
      } catch (err) {
        setH({ overall: "down", components: {}, error: String(err) });
      }
    })();
  };

  const state = overallToState(h);
  const comps = h?.components ?? {};
  const showDetails = detailed && Object.keys(comps).length > 0;

  if (compact) {
    return (
      <span className={`status-inline ${state}`}>
        <span className="dot" />
        {STATE_LABEL[state]}
      </span>
    );
  }

  return (
    <div className="status-block">
      <div className="status-row">
        <span className={`status-pill ${state}`}>
          <span className="dot" />
          API {STATE_LABEL[state]}
        </span>
        <button
          className="status-refresh"
          onClick={refresh}
          title="Re-check now"
          aria-label="Re-check status"
        >
          ↻
        </button>
      </div>
      {showDetails && (
        <div className="components">
          {Object.entries(comps).map(([name, st]) => (
            <div className="row" key={name}>
              <span>{name}</span>
              <span className={st === "up" ? "ok" : "bad"}>
                {st === "up" ? STATE_LABEL.up : STATE_LABEL.down}
              </span>
            </div>
          ))}
        </div>
      )}
      {h?.error && <div className="notice err">{h.error}</div>}
    </div>
  );
}