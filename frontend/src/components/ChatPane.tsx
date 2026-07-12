import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import {
  getSessionMessages,
  sendChat,
  type ChatResponse,
  type Message,
} from "../api/client";
import { MessageBubble } from "./MessageBubble";

interface Props {
  sessionId: string | null;
  onSessionsTouched: () => void;
}

/**
 * Main pane: scrolls the active session's messages and posts new chat
 * requests. We hydrate the per-session bucket from the server the first time
 * we see a session id (mirrors the Streamlit behaviour) so the user keeps
 * their history across page reloads.
 */
export function ChatPane({ sessionId, onSessionsTouched }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bodyRef = useRef<HTMLDivElement>(null);

  // Hydrate when the active session changes.
  useEffect(() => {
    if (!sessionId) {
      setMessages([]);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const r = await getSessionMessages(sessionId);
        if (!cancelled) setMessages(r.messages ?? []);
      } catch {
        if (!cancelled) setMessages([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  // Auto-scroll to the bottom whenever messages change.
  useEffect(() => {
    const el = bodyRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  const send = async () => {
    if (!sessionId) return;
    const text = draft.trim();
    if (!text || busy) return;
    setError(null);
    setDraft("");
    const userMsg: Message = { role: "user", content: text, ts: Date.now() / 1000 };
    setMessages((m) => [...m, userMsg]);
    setBusy(true);
    const t0 = performance.now();
    try {
      const r: ChatResponse = await sendChat({ session_id: sessionId, message: text });
      const elapsed = (performance.now() - t0) / 1000;
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: r.answer ?? "(no answer)",
          sources: r.sources ?? [],
          elapsed_s: elapsed,
          ts: Date.now() / 1000,
        },
      ]);
      onSessionsTouched();
    } catch (e: any) {
      const elapsed = (performance.now() - t0) / 1000;
      const friendly =
        e?.body?.friendly ??
        e?.body?.error ??
        e?.message ??
        "Something went wrong.";
      setError(friendly);
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: `Error: ${friendly}`,
          elapsed_s: elapsed,
          ts: Date.now() / 1000,
        },
      ]);
    } finally {
      setBusy(false);
    }
  };

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // Enter sends; Shift+Enter inserts a newline.
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void send();
    }
  };

  return (
    <section className="main">
      <header className="main-header">
        <h1>Mini AI Assistant</h1>
        <p>
          Ask questions about orders, products, or the knowledge base. The
          assistant uses retrieval-augmented generation with structured tool calls.
        </p>
      </header>

      <div className="main-body" ref={bodyRef}>
        {!sessionId && (
          <div className="empty">
            <h2>Start a conversation</h2>
            <p>Click <strong>+ New chat</strong> in the sidebar.</p>
          </div>
        )}
        {sessionId && messages.length === 0 && !busy && (
          <div className="empty">
            <h2>New chat</h2>
            <p>Ask anything about orders, products, or your uploaded documents.</p>
          </div>
        )}
        {messages.map((m, i) => (
          <MessageBubble key={i} message={m} />
        ))}
        {error && <div className="notice err">{error}</div>}
      </div>

      <div className="composer">
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKey}
          placeholder={
            sessionId
              ? "Ask anything about orders, products, or the knowledge base (Enter to send, Shift+Enter for newline)"
              : "Start a chat from the sidebar first…"
          }
          disabled={!sessionId || busy}
          rows={1}
        />
        <button className="primary" disabled={!sessionId || busy || !draft.trim()} onClick={send}>
          {busy ? "…" : "Send"}
        </button>
      </div>
    </section>
  );
}