import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import {
  getSessionMessages,
  sendChat,
  type ChatResponse,
  type Message,
} from "../api/client";
import { MessageBubble } from "./MessageBubble";
import { StatusPill } from "./StatusPill";

export interface ChatPaneHandle {
  /** Send a prompt as if the user typed it into the composer. */
  sendPrompt: (text: string) => void;
}

interface Props {
  sessionId: string | null;
  onSessionsTouched: () => void;
}

const STARTER_PROMPTS: { title: string; body: string }[] = [
  {
    title: "Browse the catalog",
    body: "What products do we sell?",
  },
  {
    title: "Track an order",
    body: "Where is order #ORD001?",
  },
  {
    title: "Recent activity",
    body: "Show me yesterday's orders.",
  },
  {
    title: "Ask your knowledge base",
    body: "Summarize the document I just uploaded.",
  },
];

export const ChatPane = forwardRef<ChatPaneHandle, Props>(function ChatPane(
  { sessionId, onSessionsTouched },
  ref,
) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statusOpen, setStatusOpen] = useState(false);
  const bodyRef = useRef<HTMLDivElement>(null);
  const statusRef = useRef<HTMLDivElement>(null);

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

  useEffect(() => {
    const el = bodyRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  useEffect(() => {
    if (!statusOpen) return;
    const onDoc = (e: MouseEvent) => {
      if (statusRef.current && !statusRef.current.contains(e.target as Node)) {
        setStatusOpen(false);
      }
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [statusOpen]);

  const send = async (textOverride?: string) => {
    if (!sessionId) return;
    const text = (textOverride ?? draft).trim();
    if (!text || busy) return;
    setError(null);
    if (textOverride === undefined) setDraft("");
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

  useImperativeHandle(ref, () => ({ sendPrompt: (text: string) => void send(text) }), [sessionId, busy]);

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void send();
    }
  };

  const isEmptyChat = sessionId && messages.length === 0 && !busy;
  const showHero = !sessionId || isEmptyChat;

  return (
    <section className="main">
      <header className="main-header">
        <div className="header-row">
          <div className="brand-block">
            <h1 className="brand-title">Mini AI Assistant</h1>
            <p className="brand-tagline">
              Retrieval-augmented chat over your documents and tools.
              <span className="tagline-divider" aria-hidden="true">·</span>
              <span className="tagline-hint">Enter to send · Shift+Enter for newline</span>
            </p>
          </div>
          <div className="status-slot" ref={statusRef}>
            <button
              className="api-dot-btn"
              onClick={() => setStatusOpen((v) => !v)}
              title="API & component health"
              aria-haspopup="dialog"
              aria-expanded={statusOpen}
            >
              <span className="api-dot" />
              <span className="api-dot-label">API</span>
            </button>
            {statusOpen && (
              <div className="api-popup" role="dialog" aria-label="API status">
                <div className="api-popup-head">API & component health</div>
                <StatusPill detailed />
              </div>
            )}
          </div>
        </div>
      </header>

      <div className="main-body" ref={bodyRef}>
        {showHero && (
          <div className="hero">
            <h2 className="hero-title">{sessionId ? "New chat" : "Welcome"}</h2>
            <p className="hero-sub">
              {sessionId
                ? "Ask anything about orders, products, or your uploaded documents."
                : "Click + New chat in the sidebar to start a conversation."}
            </p>
            <div className="starter-grid">
              {STARTER_PROMPTS.map((p) => (
                <button
                  key={p.title}
                  className="starter-card"
                  disabled={!sessionId || busy}
                  onClick={() => void send(p.body)}
                >
                  <div className="starter-kicker">{p.title}</div>
                  <div className="starter-body">“{p.body}”</div>
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) => {
          const isLastAssistantPending =
            busy && m.role === "assistant" && i === messages.length - 1;
          return (
            <MessageBubble
              key={`${m.ts ?? i}-${i}`}
              message={m}
              pending={isLastAssistantPending}
            />
          );
        })}
        {error && <div className="notice err">{error}</div>}
      </div>

      <div className="composer-wrap">
        <div className="composer">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={onKey}
            placeholder={
              sessionId
                ? "Ask anything about orders, products, or the knowledge base…"
                : "Start a chat from the sidebar first…"
            }
            disabled={!sessionId || busy}
            rows={1}
          />
          <button
            className="primary"
            disabled={!sessionId || busy || !draft.trim()}
            onClick={() => void send()}
          >
            {busy ? "…" : "Send"}
          </button>
        </div>
      </div>
    </section>
  );
});