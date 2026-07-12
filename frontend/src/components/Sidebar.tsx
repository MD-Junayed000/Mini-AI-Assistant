import { useEffect, useRef, useState } from "react";
import {
  clearKbAll,
  clearKbSource,
  deleteSession,
  ingestFile,
  listKbSources,
  listSessions,
  renameSession,
  type KbSourcesResponse,
  type SessionSummary,
} from "../api/client";
import { StatusPill } from "./StatusPill";

interface Props {
  activeSid: string | null;
  titles: Record<string, string>;
  onTitlesChange: (next: Record<string, string>) => void;
  onNewChat: () => void;
  onSwitchChat: (sid: string) => void;
  onKbChanged: () => void;
}

/**
 * Sidebar with: new-chat button, knowledge-base ingest + per-source clearing,
 * persistent session list (server-side, merged with local titles), rename,
 * and a live /healthz pill.
 */
export function Sidebar(props: Props) {
  const { activeSid, titles, onTitlesChange, onNewChat, onSwitchChat, onKbChanged } = props;
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [kb, setKb] = useState<KbSourcesResponse | null>(null);
  const [ingestNotice, setIngestNotice] = useState<
    { kind: "ok" | "warn" | "err"; text: string } | null
  >(null);
  const [clearAllArmed, setClearAllArmed] = useState(false);
  const [renameTarget, setRenameTarget] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");

  const refreshAll = async () => {
    try {
      const [s, k] = await Promise.all([listSessions(), listKbSources()]);
      setSessions(s.sessions ?? []);
      setKb(k);
    } catch {
      // Keep previous state; the StatusPill surfaces the failure.
    }
  };

  useEffect(() => {
    refreshAll();
    const t = window.setInterval(refreshAll, 15_000);
    return () => window.clearInterval(t);
  }, []);

  const handleUpload = async (file: File) => {
    setIngestNotice(null);
    try {
      const r = await ingestFile(file);
      if (r.chunks === 0) {
        const why = r.error ?? r.fallback_reason ?? "no text could be extracted";
        if (r.fallback_reason === "chroma_restart_required") {
          setIngestNotice({
            kind: "warn",
            text:
              "Vector index is unrecoverable in this process. Restart the API or run `make recover-chroma`, then upload again.",
          });
        } else {
          setIngestNotice({
            kind: "err",
            text: `Couldn't index ${file.name}: ${why}`,
          });
        }
      } else {
        let msg = `Indexed ${r.chunks} chunks from ${r.source}`;
        if (r.backend && r.backend !== "docling" && r.fallback_reason) {
          msg += ` — using ${r.backend} (docling unavailable; OCR figures skipped)`;
        } else if (r.backend && r.backend !== "docling") {
          msg += ` — using ${r.backend}`;
        }
        setIngestNotice({ kind: "ok", text: msg });
      }
      onKbChanged();
      await refreshAll();
    } catch (e) {
      setIngestNotice({ kind: "err", text: String(e) });
    }
  };

  const handleClearSource = async (source: string) => {
    try {
      const r = await clearKbSource(source);
      setIngestNotice({
        kind: "ok",
        text: `Cleared ${r.removed} chunk(s) from ${source.split(/[\\/]/).pop()}.`,
      });
      onKbChanged();
      await refreshAll();
    } catch (e) {
      setIngestNotice({ kind: "err", text: `Clear failed: ${String(e)}` });
    }
  };

  const handleClearAll = async () => {
    try {
      const r = await clearKbAll();
      setIngestNotice({ kind: "ok", text: `Cleared ${r.removed} chunk(s) from the KB.` });
      onKbChanged();
      await refreshAll();
    } catch (e) {
      setIngestNotice({ kind: "err", text: `Clear failed: ${String(e)}` });
    }
  };

  const handleDeleteSession = async (sid: string) => {
    try {
      await deleteSession(sid);
    } catch {
      /* ignore — UI will still remove it locally */
    }
    const next = { ...titles };
    delete next[sid];
    onTitlesChange(next);
    if (activeSid === sid) onNewChat();
    await refreshAll();
  };

  const handleRename = async (sid: string) => {
    const v = renameValue.trim();
    if (!v) return;
    try {
      await renameSession(sid, v);
    } catch {
      /* server is a no-op for rename; local title still updates */
    }
    onTitlesChange({ ...titles, [sid]: v });
    setRenameTarget(null);
    setRenameValue("");
  };

  const labelFor = (s: SessionSummary) =>
    titles[s.session_id] ?? s.title ?? `session ${s.session_id.slice(0, 8)}`;

  return (
    <aside className="sidebar">
      <button className="new-chat-btn primary" onClick={onNewChat}>
        + New chat
      </button>

      <div>
        <h3>Knowledge Base</h3>
        <p className="caption">Upload a PDF, TXT, or MD file to index it for retrieval.</p>
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.txt,.md"
          style={{ marginTop: 6 }}
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) handleUpload(f);
            // Reset so the same file can be re-picked.
            e.target.value = "";
          }}
        />
        {ingestNotice && <div className={`notice ${ingestNotice.kind}`}>{ingestNotice.text}</div>}
      </div>

      <hr />

      <div>
        <h3>Indexed documents</h3>
        {kb && kb.sources && kb.sources.length > 0 ? (
          <>
            <p className="caption">
              {kb.total_sources} document(s) · {kb.total_chunks} chunk(s) total
            </p>
            {kb.sources.map((s) => {
              const short = s.source.replace(/\\/g, "/").split("/").pop() ?? s.source;
              return (
                <div className="kb-row" key={s.source}>
                  <div>
                    <div className="src" title={s.source}>{short}</div>
                    <div className="count">{s.chunks} chunk(s)</div>
                  </div>
                  <button
                    className="del"
                    title={`Clear ${s.chunks} chunk(s) from ${short}`}
                    onClick={() => handleClearSource(s.source)}
                  >
                    ✕
                  </button>
                </div>
              );
            })}
            <details style={{ marginTop: 10 }}>
              <summary style={{ cursor: "pointer", color: "var(--text-muted)" }}>
                Danger zone
              </summary>
              <div style={{ marginTop: 8 }}>
                <label style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 12 }}>
                  <input
                    type="checkbox"
                    checked={clearAllArmed}
                    onChange={(e) => setClearAllArmed(e.target.checked)}
                  />
                  I understand this clears the entire knowledge base.
                </label>
                <button
                  className="danger"
                  disabled={!clearAllArmed}
                  style={{ width: "100%", marginTop: 8 }}
                  onClick={handleClearAll}
                >
                  Clear all indexed chunks
                </button>
              </div>
            </details>
          </>
        ) : (
          <p className="caption">No documents indexed yet.</p>
        )}
      </div>

      <hr />

      <div>
        <h3>Chats</h3>
        <button onClick={refreshAll} style={{ width: "100%", marginBottom: 8 }}>
          ↻ Refresh list
        </button>
        {sessions.length === 0 && (
          <p className="caption">No chats yet — click + New chat to start one.</p>
        )}
        {sessions.map((s) => {
          const isActive = s.session_id === activeSid;
          const isRenaming = renameTarget === s.session_id;
          return (
            <div className="session-row" key={s.session_id}>
              <button
                className={`open${isActive ? " active" : ""}`}
                disabled={isActive || isRenaming}
                onClick={() => onSwitchChat(s.session_id)}
                title={labelFor(s)}
              >
                <span className={`dot${isActive ? " on" : ""}`} aria-hidden="true" />
                {isRenaming ? (
                  <input
                    className="rename-input"
                    autoFocus
                    value={renameValue}
                    onChange={(e) => setRenameValue(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") handleRename(s.session_id);
                      if (e.key === "Escape") {
                        setRenameTarget(null);
                        setRenameValue("");
                      }
                    }}
                    onClick={(e) => e.stopPropagation()}
                  />
                ) : (
                  <span className="label">{labelFor(s)}</span>
                )}
              </button>
              <button
                className="rename"
                title="Rename this chat"
                onClick={() => {
                  setRenameTarget(s.session_id);
                  setRenameValue(titles[s.session_id] ?? "");
                }}
              >
                ✎
              </button>
              <button
                className="del"
                title="Delete this chat permanently"
                onClick={() => handleDeleteSession(s.session_id)}
              >
                ✕
              </button>
            </div>
          );
        })}
      </div>

      <hr />

      <div>
        <h3>Status</h3>
        <StatusPill />
      </div>
    </aside>
  );
}