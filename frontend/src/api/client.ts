/**
 * Typed HTTP client for the Mini AI Assistant backend.
 *
 * Mirrors every endpoint declared in `backend/routes/chat.py`. The base URL
 * is read from `import.meta.env.VITE_API_BASE`:
 *
 *   - dev (vite dev server)   → "/api" (the Vite proxy forwards to :8000)
 *   - single-image production → "" (same origin as the FastAPI host)
 *
 * The previous Streamlit implementation used `httpx` on the server side; the
 * React app is a pure browser app, so we use `fetch`. Single retry on
 * transient network errors keeps Windows's occasional WinError 10054 socket
 * drops from looking like an app fault.
 */

const BASE: string =
  ((import.meta.env.VITE_API_BASE ?? "") as string).replace(/\/+$/, "");

export interface Source {
  id: string;
  preview?: string;
  source?: string;
  score?: number;
}

export interface Message {
  role: "user" | "assistant" | "system";
  content: string;
  ts?: number;
  elapsed_s?: number | null;
  sources?: Source[];
}

export interface SessionSummary {
  session_id: string;
  title: string;
  turns: number;
  last_ts?: number;
}

export interface SessionMessages {
  session_id: string;
  messages: Message[];
}

export interface SessionsResponse {
  sessions: SessionSummary[];
}

export interface ChatRequest {
  session_id: string;
  message: string;
}

export interface ChatResponse {
  answer: string;
  sources: Source[];
  tool_calls?: unknown[];
  evidence?: unknown[];
  injection_risk?: boolean | null;
  fallback_used?: boolean | null;
}

export interface IngestResponse {
  chunks: number;
  source: string;
  backend: string;
  fallback_reason?: string | null;
  error?: string;
}

export interface HealthComponentMap {
  [name: string]: string; // "up" | "down"
}

export interface HealthResponse {
  overall: "up" | "degraded" | "down" | "unknown";
  components?: HealthComponentMap;
  cached?: boolean;
  taken_at?: number;
  error?: string;
}

export interface KbSource {
  source: string;
  chunks: number;
}

export interface KbSourcesResponse {
  sources: KbSource[];
  total_chunks: number;
  total_sources: number;
}

export interface ClearSourceResponse {
  source: string;
  removed: number;
}

export interface RootResponse {
  service: string;
  version: string;
  ui: string;
  endpoints: Record<string, string>;
}

export interface ApiErrorBody {
  error?: string;
  code?: string;
  friendly?: string;
  detail?: unknown;
}

/** Thrown for non-2xx responses. `body` carries the parsed JSON when available. */
export class ApiError extends Error {
  readonly status: number;
  readonly body: ApiErrorBody | null;
  constructor(status: number, message: string, body: ApiErrorBody | null) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

async function parseOrEmpty<T>(p: Promise<Response>): Promise<T> {
  const r = await p;
  // No content (204) — return empty object cast.
  if (r.status === 204) return {} as T;
  const text = await r.text();
  const data = text ? (JSON.parse(text) as unknown) : {};
  if (!r.ok) {
    const body = (data ?? null) as ApiErrorBody | null;
    const msg = body?.friendly ?? body?.error ?? `HTTP ${r.status}`;
    throw new ApiError(r.status, msg, body);
  }
  return data as T;
}

async function fetchWithRetry(
  input: string,
  init: RequestInit,
  retries = 1,
): Promise<Response> {
  // First attempt + one retry; the user can always click again if it
  // still fails. Keeps the WinError 10054 case from showing as a hard error.
  let lastErr: unknown = null;
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      return await fetch(input, init);
    } catch (err) {
      lastErr = err;
    }
  }
  throw lastErr instanceof Error ? lastErr : new Error("Network error");
}

function url(path: string): string {
  // Allow callers to pass either "/sessions" or "sessions" — be permissive.
  const p = path.startsWith("/") ? path : `/${path}`;
  return `${BASE}${p}`;
}

// ---------- Endpoints ------------------------------------------------------

export async function getRoot(): Promise<RootResponse> {
  return parseOrEmpty<RootResponse>(fetchWithRetry(url("/"), { method: "GET" }));
}

export async function getHealth(): Promise<HealthResponse> {
  return parseOrEmpty<HealthResponse>(
    fetchWithRetry(url("/healthz"), { method: "GET" }),
  );
}

export async function listSessions(): Promise<SessionsResponse> {
  return parseOrEmpty<SessionsResponse>(
    fetchWithRetry(url("/sessions"), { method: "GET" }),
  );
}

export async function getSessionMessages(
  session_id: string,
  limit = 200,
): Promise<SessionMessages> {
  const qs = new URLSearchParams({ limit: String(limit) });
  return parseOrEmpty<SessionMessages>(
    fetchWithRetry(url(`/session/${encodeURIComponent(session_id)}/messages?${qs}`), {
      method: "GET",
    }),
  );
}

export async function deleteSession(session_id: string): Promise<{ deleted: number }> {
  return parseOrEmpty<{ deleted: number }>(
    fetchWithRetry(url(`/session/${encodeURIComponent(session_id)}/delete`), {
      method: "POST",
    }),
  );
}

export async function resetSession(
  session_id: string,
): Promise<{ reset: boolean }> {
  return parseOrEmpty<{ reset: boolean }>(
    fetchWithRetry(url(`/session/${encodeURIComponent(session_id)}/reset`), {
      method: "POST",
    }),
  );
}

export async function renameSession(
  session_id: string,
  title: string,
): Promise<{ session_id: string; title: string }> {
  return parseOrEmpty<{ session_id: string; title: string }>(
    fetchWithRetry(url(`/session/${encodeURIComponent(session_id)}/rename`), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    }),
  );
}

export async function sendChat(req: ChatRequest): Promise<ChatResponse> {
  return parseOrEmpty<ChatResponse>(
    fetchWithRetry(url("/chat"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    }),
  );
}

export async function ingestFile(file: File): Promise<IngestResponse> {
  // Build the multipart payload manually so we can keep `fetchWithRetry`
  // symmetric and don't need FormData-spreading helpers.
  const fd = new FormData();
  fd.append("file", file, file.name);
  return parseOrEmpty<IngestResponse>(
    fetchWithRetry(url("/ingest"), { method: "POST", body: fd }),
  );
}

export async function listKbSources(): Promise<KbSourcesResponse> {
  return parseOrEmpty<KbSourcesResponse>(
    fetchWithRetry(url("/admin/kb/sources"), { method: "GET" }),
  );
}

export async function clearKbSource(source: string): Promise<ClearSourceResponse> {
  return parseOrEmpty<ClearSourceResponse>(
    fetchWithRetry(url("/admin/kb/clear-source"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source }),
    }),
  );
}

export async function clearKbAll(): Promise<{ removed: number }> {
  return parseOrEmpty<{ removed: number }>(
    fetchWithRetry(url("/admin/kb/clear"), { method: "POST" }),
  );
}

export async function refreshCache(): Promise<{ refreshed: boolean }> {
  return parseOrEmpty<{ refreshed: boolean }>(
    fetchWithRetry(url("/admin/cache/refresh"), { method: "POST" }),
  );
}
