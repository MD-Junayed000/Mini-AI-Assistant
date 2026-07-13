import Markdown from "react-markdown";
import type { Message } from "../api/client";

interface Props {
  message: Message;
  /** True while the assistant reply for this turn is still streaming. */
  pending?: boolean;
}

export function MessageBubble({ message, pending = false }: Props) {
  const role = message.role === "user" ? "user" : "assistant";
  const isPending = pending || message.pending === true;
  const elapsedLabel =
    message.elapsed_s != null ? `${message.elapsed_s.toFixed(1)} s` : null;
  return (
    <div className={`message ${role}${isPending ? " pending" : ""}`}>
      <div className="bubble">
        <div className="bubble-content">
          {message.content && message.content.length > 0 ? (
            <Markdown>{message.content}</Markdown>
          ) : isPending ? (
            <div className="gen-skeleton" aria-label="Generating response">
              <span className="dot1" />
              <span className="dot2" />
              <span className="dot3" />
              <span className="gen-text">Generating response…</span>
            </div>
          ) : (
            <em style={{ color: "var(--text-muted)" }}>(empty)</em>
          )}
          {isPending && message.content && (
            <span className="cursor" aria-hidden="true" />
          )}
        </div>
        <div className="meta-row">
          {elapsedLabel && <span className="meta">{elapsedLabel}</span>}
          {isPending && (
            <span className="meta pending-label">thinking…</span>
          )}
        </div>
        {message.sources && message.sources.length > 0 && (
          <details className="sources">
            <summary>{message.sources.length} source(s)</summary>
            <ul>
              {message.sources.map((s, i) => (
                <li key={`${s.id ?? i}-${i}`}>
                  <strong>{s.id ?? `source ${i + 1}`}</strong>
                  {s.preview ? ` — ${String(s.preview).slice(0, 180)}` : ""}
                </li>
              ))}
            </ul>
          </details>
        )}
      </div>
    </div>
  );
}