import type { Message } from "../api/client";

interface Props {
  message: Message;
  /** True while the assistant reply for this turn is still streaming. */
  pending?: boolean;
}

export function MessageBubble({ message, pending = false }: Props) {
  const role = message.role === "user" ? "user" : "assistant";
  return (
    <div className={`message ${role}${pending ? " pending" : ""}`}>
      <div className="bubble">
        <div className="bubble-content">
          {message.content || (
            <em style={{ color: "var(--text-muted)" }}>(empty)</em>
          )}
          {pending && <span className="cursor" aria-hidden="true" />}
        </div>
        {message.elapsed_s != null && (
          <div className="meta">{message.elapsed_s.toFixed(1)} s</div>
        )}
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