import { useCallback, useEffect, useState } from "react";
import { Sidebar } from "./components/Sidebar";
import { ChatPane } from "./components/ChatPane";

/** Generate a 12-char hex session id, matching the Streamlit helper. */
function newSid(): string {
  const bytes = new Uint8Array(6);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

const ACTIVE_SID_KEY = "mini_ai.activeSid";
const TITLES_KEY = "mini_ai.titles";

/**
 * Root component. Owns:
 *   - active session id (persisted to localStorage so refresh keeps you put)
 *   - user-renamed titles (persisted to localStorage; server titles win
 *     when present)
 *   - the sidebar's "touched" callback so the chat pane can nudge the
 *     sidebar session list when a new message lands
 */
export default function App() {
  const [activeSid, setActiveSid] = useState<string | null>(() => {
    return localStorage.getItem(ACTIVE_SID_KEY) ?? newSid();
  });
  const [titles, setTitles] = useState<Record<string, string>>(() => {
    try {
      return JSON.parse(localStorage.getItem(TITLES_KEY) ?? "{}");
    } catch {
      return {};
    }
  });

  // Persist on change.
  useEffect(() => {
    if (activeSid) localStorage.setItem(ACTIVE_SID_KEY, activeSid);
  }, [activeSid]);
  useEffect(() => {
    localStorage.setItem(TITLES_KEY, JSON.stringify(titles));
  }, [titles]);

  const handleNewChat = useCallback(() => {
    const sid = newSid();
    setActiveSid(sid);
  }, []);

  const handleSwitchChat = useCallback((sid: string) => {
    if (sid) setActiveSid(sid);
  }, []);

  const handleKbChanged = useCallback(() => {
    /* Sidebar polls on its own; this is a hook for future invalidation. */
  }, []);

  const handleSessionsTouched = useCallback(() => {
    /* Sidebar polls on its own; this is a hook for future invalidation. */
  }, []);

  return (
    <div className="app">
      <Sidebar
        activeSid={activeSid}
        titles={titles}
        onTitlesChange={setTitles}
        onNewChat={handleNewChat}
        onSwitchChat={handleSwitchChat}
        onKbChanged={handleKbChanged}
      />
      <ChatPane
        sessionId={activeSid}
        onSessionsTouched={handleSessionsTouched}
      />
    </div>
  );
}