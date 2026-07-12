import type { Message } from "../api/client";

interface Props {
  message: Message;
}

/**
 * Render one chat message. User messages are right-aligned in a muted bubble;
 * assistant messages are left-aligned in white with a collapsible sources
 * drawer underneath. The `elapsed_s` and `sources` fields are only populated
 * for assistant turns in practice.
 */
export function MessageBubble({ message }: Props) {
  const role = message.role === "user" ? "user" : "assistant";
  return (
    <div className={`message ${role}`}>
      <div className="bubble">
        <div>{message.content || <em style={{ color: "var(--text-muted)" }}>(empty)</em>}</div>
        {message.elapsed_s != null && (
          <div className="meta">answered in {message.elapsed_s.toFixed(1)} s</div>
        )}
        {message.sources && message.sources.length > 0 && (
          <details className="sources">
            <summary>Sources ({message.sources.length})</summary>
            <ul>
              {message.sources.map((s, i) => (
                <li key={`${s.id ?? i}-${i}`}>
                  <strong>{s.id ?? `source ${i + 1}`}</strong>
                  {s.preview ? ` — ${String(s.preview).slice(0, 200)}` : ""}
                </li>
              ))}
            </ul>
          </details>
        )}
      </div>
    </div>
  );
}