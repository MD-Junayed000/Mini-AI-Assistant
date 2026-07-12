import { useCallback, useEffect, useState } from "react";
import { Sidebar } from "./components/Sidebar";
import { ChatPane } from "./components/ChatPane";

function newSid(): string {
  const bytes = new Uint8Array(6);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

const ACTIVE_SID_KEY = "mini_ai.activeSid";
const TITLES_KEY = "mini_ai.titles";

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

  useEffect(() => {
    if (activeSid) localStorage.setItem(ACTIVE_SID_KEY, activeSid);
  }, [activeSid]);
  useEffect(() => {
    localStorage.setItem(TITLES_KEY, JSON.stringify(titles));
  }, [titles]);

  const handleNewChat = useCallback(() => setActiveSid(newSid()), []);
  const handleSwitchChat = useCallback((sid: string) => {
    if (sid) setActiveSid(sid);
  }, []);
  const noop = useCallback(() => {}, []);

  return (
    <div className="app">
      <Sidebar
        activeSid={activeSid}
        titles={titles}
        onTitlesChange={setTitles}
        onNewChat={handleNewChat}
        onSwitchChat={handleSwitchChat}
        onKbChanged={noop}
      />
      <ChatPane sessionId={activeSid} onSessionsTouched={noop} />
    </div>
  );
}