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
  sendPrompt: (text: string) => void;
}

interface Props {
  sessionId: string | null;
  onSessionsTouched: () => void;
  onMenuClick?: () => void;        // ← NEW
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
  { sessionId, onSessionsTouched, onMenuClick },
  ref,
) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statusOpen, setStatusOpen] = useState(false);
  const [loadingSession, setLoadingSession] = useState(false);
  const bodyRef = useRef<HTMLDivElement>(null);
  const statusRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!sessionId) {
      setMessages([]);
      setLoadingSession(false);
      return;
    }
    setMessages([]);
    setError(null);
    setLoadingSession(true);
    let cancelled = false;
    (async () => {
      try {
        const r = await getSessionMessages(sessionId);
        if (!cancelled) setMessages(r.messages ?? []);
      } catch (e: any) {
        if (!cancelled) {
          setMessages([]);
          setError(
            (e?.body?.friendly ??
              e?.body?.error ??
              e?.message ??
              "Couldn't load this chat.") +
            " — Try Refresh list in the sidebar.",
          );
        }
      } finally {
        if (!cancelled) setLoadingSession(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  useEffect(() => {
    if (sessionId && !busy && !loadingSession) {
      window.setTimeout(() => textareaRef.current?.focus(), 50);
    }
  }, [sessionId, busy, loadingSession]);

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
    const t0 = performance.now();
    const nowTs = Date.now() / 1000;
    const userMsg: Message = { role: "user", content: text, ts: nowTs };
    const placeholder: Message = {
      role: "assistant",
      content: "",
      ts: nowTs,
      pending: true,
    };
    setMessages((m) => [...m, userMsg, placeholder]);
    setBusy(true);

    const tickInterval = window.setInterval(() => {
      const elapsed = (performance.now() - t0) / 1000;
      setMessages((m) =>
        m.map((mm, i) =>
          i === m.length - 1 && mm.pending
            ? { ...mm, elapsed_s: elapsed }
            : mm,
        ),
      );
    }, 200);

    try {
      const r: ChatResponse = await sendChat({ session_id: sessionId, message: text });
      const elapsed = (performance.now() - t0) / 1000;
      window.clearInterval(tickInterval);
      setMessages((m) =>
        m.map((mm, i) =>
          i === m.length - 1 && mm.pending
            ? {
                role: "assistant",
                content: r.answer ?? "(no answer)",
                sources: r.sources ?? [],
                elapsed_s: elapsed,
                ts: Date.now() / 1000,
              }
            : mm,
        ),
      );
      onSessionsTouched();
    } catch (e: any) {
      const elapsed = (performance.now() - t0) / 1000;
      window.clearInterval(tickInterval);
      const friendly =
        e?.body?.friendly ??
        e?.body?.error ??
        e?.message ??
        "Something went wrong.";
      setError(friendly);
      setMessages((m) =>
        m.map((mm, i) =>
          i === m.length - 1 && mm.pending
            ? {
                role: "assistant",
                content: `Error: ${friendly}`,
                elapsed_s: elapsed,
                ts: Date.now() / 1000,
              }
            : mm,
        ),
      );
    } finally {
      window.clearInterval(tickInterval);
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
                  {/* ==================== MOBILE MENU BUTTON ==================== */}
            <button 
              className="mobile-menu-btn"
              onClick={onMenuClick}           // ← This will come from props
              aria-label="Open sidebar"
            >
              ☰
            </button>
            {/* ======================================================== */}
          <div className="brand-block">
            <h1 className="brand-title">
              Mini AI Assistant
              <span className="brand-tagline-inline">
                Retrieval-augmented chat over your documents and tools.
              </span>
            </h1>
          </div>
          <div className="status-slot" ref={statusRef}>
            <button
              className="api-dot-btn"
              onClick={() => setStatusOpen((v) => !v)}
              title="API & component health"
              aria-haspopup="dialog"
              aria-expanded={statusOpen}
            >
              <span className="api-dot-label">API: <StatusPill compact /></span>
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
            className="composer-send"
            disabled={!sessionId || busy || !draft.trim()}
            onClick={() => void send()}
            title="Send message"
            aria-label="Send message"
          >
            <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
              <path d="M3 11.5L21 3l-8.5 18-2.2-7.3L3 11.5z" fill="currentColor"/>
            </svg>
          </button>
        </div>
        <div className="composer-hint">
          <span className="composer-hint-text">Enter to send · Shift+Enter for newline</span>
        </div>
      </div>
    </section>
  );
});
