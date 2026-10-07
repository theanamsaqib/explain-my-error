import type {
  DebugRequest,
  DebugResponse,
  Health,
  HistoryItem,
  StreamEvent,
} from "@/types/debug";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  code: string;
  constructor(code: string, message: string) {
    super(message);
    this.code = code;
  }
}

async function toApiError(res: Response): Promise<ApiError> {
  try {
    const body = await res.json();
    if (body?.error?.message) return new ApiError(body.error.code ?? "error", body.error.message);
  } catch {
    /* not JSON */
  }
  return new ApiError("http_error", `The server answered with HTTP ${res.status}.`);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError(
      "network",
      `Cannot reach the backend at ${API_URL}. Is it running? (uvicorn app.main:app --port 8000)`,
    );
  }
  if (!res.ok) throw await toApiError(res);
  return (await res.json()) as T;
}

export const getHealth = () => request<Health>("/api/health");
export const getHistory = () => request<HistoryItem[]>("/api/debug/history");
export const getSession = (id: number) => request<DebugResponse>(`/api/debug/history/${id}`);

export const runDebug = (body: DebugRequest) =>
  request<DebugResponse>("/api/debug", { method: "POST", body: JSON.stringify(body) });

/**
 * POST /api/debug/stream and call `onEvent` for every Server-Sent Event as it arrives.
 * Resolves when the stream ends. A server-side `error` event is thrown as an ApiError.
 */
export async function streamDebug(
  body: DebugRequest,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/debug/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new ApiError("network", `Cannot reach the backend at ${API_URL}. Is it running?`);
  }
  if (!res.ok || !res.body) throw await toApiError(res);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const flush = (block: string) => {
    const dataLine = block.split("\n").find((l) => l.startsWith("data: "));
    if (!dataLine) return;
    const event = JSON.parse(dataLine.slice(6)) as StreamEvent;
    if (event.type === "error") throw new ApiError(event.error.code, event.error.message);
    onEvent(event);
  };

  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      flush(buffer.slice(0, idx));
      buffer = buffer.slice(idx + 2);
    }
  }
  if (buffer.trim()) flush(buffer);
}
