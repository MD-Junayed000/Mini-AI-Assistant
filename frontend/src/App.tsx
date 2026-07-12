import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Sidebar } from "./components/Sidebar";
import { ChatPane } from "./components/ChatPane";
import { bootstrapSession, listSessions, type SessionSummary } from "./api/client";

/** Generate a 12-char hex session id without an external dependency. */
function newSid(): string {
  const bytes = new Uint8Array(6);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

const ACTIVE_SID_KEY = "mini_ai.activeSid";
const TITLES_KEY = "mini_ai.titles";
const KNOWN_SIDS_KEY = "mini_ai.knownSids";

function readJSON<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

interface LocalChat {
  sid: string;
  /** epoch ms — used to sort the sidebar list newest-first. */
  lastActive: number;
  /** Title the user last saw (renamed locally, or fetched from server). */
  title: string;
  /** True iff the server's /sessions endpoint returned this id. */
  serverKnown: boolean;
  /** True once the user has sent at least one message on this chat. */
  everUsed: boolean;
}

export default function App() {
  const [activeSid, setActiveSid] = useState<string | null>(() => {
    return localStorage.getItem(ACTIVE_SID_KEY) ?? newSid();
  });
  const [titles, setTitles] = useState<Record<string, string>>(() =>
    readJSON<Record<string, string>>(TITLES_KEY, {}),
  );
  /** Every session id the user has ever opened from this browser, newest first. */
  const [knownSids, setKnownSids] = useState<string[]>(() =>
    readJSON<string[]>(KNOWN_SIDS_KEY, []),
  );
  /** Server-known session list (refreshed every 15s + on demand). */
  const [serverSessions, setServerSessions] = useState<SessionSummary[]>([]);
  /** Bumps when a chat is sent/created/deleted so the sidebar re-renders. */
  const [touchTick, setTouchTick] = useState(0);
  const refreshTimer = useRef<number | null>(null);

  // Persist active session id so a reload keeps the same chat open.
  useEffect(() => {
    if (activeSid) localStorage.setItem(ACTIVE_SID_KEY, activeSid);
  }, [activeSid]);

  // Persist user-renamed titles.
  useEffect(() => {
    localStorage.setItem(TITLES_KEY, JSON.stringify(titles));
  }, [titles]);

  // Persist the locally-tracked session list so a uvicorn restart (which
  // wipes the in-process fallback) doesn't make previous chats "vanish".
  useEffect(() => {
    localStorage.setItem(KNOWN_SIDS_KEY, JSON.stringify(knownSids));
  }, [knownSids]);

  // Whenever the active session id changes, register it in `knownSids`
  // so the sidebar will list it even before the server has acknowledged it.
  useEffect(() => {
    if (!activeSid) return;
    setKnownSids((prev) => (prev.includes(activeSid) ? prev : [activeSid, ...prev]));
  }, [activeSid]);

  /** Merge server-known sessions with locally-tracked ones. The server is
   *  authoritative for `lastActive`, `turns`, and the auto-derived title;
   *  the local map is authoritative for renames the user just made. */
  const mergedSessions = useMemo<LocalChat[]>(() => {
    const byId = new Map<string, LocalChat>();
    for (const s of serverSessions) {
      byId.set(s.session_id, {
        sid: s.session_id,
        lastActive: (s.last_ts ?? 0) * 1000,
        title: titles[s.session_id] ?? s.title ?? `session ${s.session_id.slice(0, 8)}`,
        serverKnown: true,
        everUsed: true,
      });
    }
    for (const sid of knownSids) {
      const existing = byId.get(sid);
      if (existing) {
        // Promote a local rename over the server-derived title.
        if (titles[sid]) existing.title = titles[sid];
      } else {
        byId.set(sid, {
          sid,
          // Local-only stub: best-effort sort order via the position in
          // `knownSids` (which is newest-first).
          lastActive: 0,
          title: titles[sid] ?? `session ${sid.slice(0, 8)}`,
          serverKnown: false,
          everUsed: false,
        });
      }
    }
    // Newest first; ties broken by knownSids order.
    const order = new Map<string, number>();
    knownSids.forEach((sid, i) => order.set(sid, i));
    return Array.from(byId.values()).sort((a, b) => {
      if (b.lastActive !== a.lastActive) return b.lastActive - a.lastActive;
      return (order.get(a.sid) ?? 999) - (order.get(b.sid) ?? 999);
    });
  }, [serverSessions, knownSids, titles, touchTick]);

  /** Refresh the server-side session list. Failures are silent — the
   *  locally-tracked chats remain visible in the sidebar. */
  const refreshSessions = useCallback(async () => {
    try {
      const r = await listSessions();
      setServerSessions(r.sessions ?? []);
    } catch {
      /* keep local list */
    }
  }, []);

  useEffect(() => {
    void refreshSessions();
    refreshTimer.current = window.setInterval(refreshSessions, 15_000);
    return () => {
      if (refreshTimer.current) window.clearInterval(refreshTimer.current);
    };
  }, [refreshSessions]);

  /** + New chat — keep the previous chat in knownSids so it stays visible. */
  const handleNewChat = useCallback(() => {
    const prev = activeSid;
    const sid = newSid();
    if (prev) {
      setKnownSids((sids) => (sids.includes(prev) ? sids : [prev, ...sids]));
    }
    setActiveSid(sid);
    setTouchTick((n) => n + 1);
    void bootstrapSession(sid)
      .then(() => {
        void refreshSessions();
      })
      .catch(() => {
        /* local sidebar state still keeps the new chat visible */
      });
  }, [activeSid, refreshSessions]);

  /** Switch to a different chat. */
  const handleSwitchChat = useCallback((sid: string) => {
    if (!sid) return;
    setActiveSid((current) => {
      if (current && current !== sid) {
        setKnownSids((sids) => (sids.includes(current) ? sids : [current, ...sids]));
      }
      return sid;
    });
  }, []);

  const handleTitlesChange = useCallback((next: Record<string, string>) => {
    setTitles(next);
  }, []);

  /** Drop a session from the local list after the sidebar deletes it. */
  const handleDeleteChat = useCallback((sid: string) => {
    setKnownSids((sids) => sids.filter((s) => s !== sid));
    setTouchTick((n) => n + 1);
  }, []);

  /** Triggered when a chat turn completes so the sidebar can refresh. */
  const handleSessionsTouched = useCallback(() => {
    setTouchTick((n) => n + 1);
    void refreshSessions();
  }, [refreshSessions]);

  /** Broadcast so other components (sidebar) can react to KB changes. */
  const handleKbChanged = useCallback(() => {
    window.dispatchEvent(new CustomEvent("mini_ai:kb-changed"));
  }, []);

  /** Flat record the sidebar uses for title lookups. */
  const sidebarTitles = useMemo<Record<string, string>>(() => {
    const out: Record<string, string> = {};
    for (const c of mergedSessions) out[c.sid] = c.title;
    return out;
  }, [mergedSessions]);

  return (
    <div className="app">
      <Sidebar
        activeSid={activeSid}
        titles={sidebarTitles}
        sessions={mergedSessions}
        onTitlesChange={handleTitlesChange}
        onNewChat={handleNewChat}
        onSwitchChat={handleSwitchChat}
        onDeleteChat={handleDeleteChat}
        onSessionsTouched={handleSessionsTouched}
        onKbChanged={handleKbChanged}
        refreshTrigger={touchTick}
      />
      <ChatPane sessionId={activeSid} onSessionsTouched={handleSessionsTouched} />
    </div>
  );
}