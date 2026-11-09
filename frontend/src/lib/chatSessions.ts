import { API_BASE, ApiError, parseError } from "./api";
import type { ChatSource } from "./chatStream";

export interface ChatSessionSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface StoredMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  sources: ChatSource[] | null;
  citations: number[] | null;
  suggestions: string[] | null;
  rewritten_question: string | null;
  status: "done" | "stopped" | "failed" | null;
  created_at: string;
}

export interface ChatSessionDetail extends ChatSessionSummary {
  messages: StoredMessage[];
}

export type Phase = "reading" | "streaming" | "done" | "stopped" | "failed";

/** One question and its answer, as the page shows it, whether streamed now or saved earlier. */
export interface Turn {
  id: number;
  question: string;
  answer: string;
  sources: ChatSource[];
  rewritten: string | null;
  suggestions: string[];
  /** The sources the finished answer cites; null until it finishes (or when it did not finish). */
  citations: number[] | null;
  phase: Phase;
  failure: { reason: string } | ApiError | null;
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/chat/sessions${path}`, { cache: "no-store", ...init });
  } catch {
    throw new ApiError(0, "Network error");
  }
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => null);
  if (!res.ok) throw parseError(res.status, body);
  return body as T;
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "content-type": "application/json" },
  body: JSON.stringify(body),
});

export const chatSessions = {
  list: () => call<{ items: ChatSessionSummary[]; total: number }>("?limit=100"),
  create: () => call<ChatSessionSummary>("", json("POST", {})),
  get: (id: string) => call<ChatSessionDetail>(`/${id}`),
  rename: (id: string, title: string) => call<ChatSessionSummary>(`/${id}`, json("PATCH", { title })),
  remove: (id: string) => call<void>(`/${id}`, { method: "DELETE" }),
};

/**
 * Saved messages as turns. A question with no answer after it (the server stopped mid-stream) is shown as
 * a failed turn, so the person can ask it again.
 */
export function turnsFromMessages(messages: StoredMessage[], firstId = 0): Turn[] {
  const turns: Turn[] = [];
  for (const message of messages) {
    if (message.role === "user") {
      turns.push({
        id: firstId + turns.length,
        question: message.content,
        answer: "",
        sources: [],
        rewritten: null,
        suggestions: [],
        citations: null,
        phase: "failed",
        failure: { reason: "model_failed" },
      });
      continue;
    }
    const turn = turns.at(-1);
    if (!turn || turn.phase !== "failed" || turn.answer !== "" || turn.sources.length > 0) continue;
    const status = message.status ?? "done";
    turn.answer = message.content;
    turn.sources = message.sources ?? [];
    turn.rewritten = message.rewritten_question;
    turn.suggestions = message.suggestions ?? [];
    turn.citations = status === "done" ? (message.citations ?? []) : null;
    turn.phase = status;
    turn.failure = status === "failed" ? { reason: "model_failed" } : null;
  }
  return turns;
}
