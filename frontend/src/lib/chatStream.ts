import { API_BASE, ApiError, parseError } from "./api";
import { filtersToParams } from "./filters";
import type { DocumentFilters } from "./types";

export interface ChatSource {
  n: number;
  document_id: string;
  filename: string;
  page_no: number;
  quote: string;
}

/** What the API streams, in order: sources, tokens, then done (or an error instead of done). */
export type ChatEvent =
  | { type: "sources"; sources: ChatSource[]; rewritten_question?: string }
  | { type: "token"; text: string }
  | { type: "done"; citations: number[]; suggestions: string[] }
  | { type: "error"; reason: string };

export interface ChatRequest {
  question: string;
  /** The saved conversation the question belongs to; the server keeps the question and the answer in it. */
  sessionId: string;
  filters: DocumentFilters;
}

/** Events of a server-sent event stream; an event ends at a blank line. Returns what is left over. */
export function parseEvents(buffer: string): { events: ChatEvent[]; rest: string } {
  const blocks = buffer.replaceAll("\r\n", "\n").split("\n\n");
  const rest = blocks.pop() ?? "";
  const events: ChatEvent[] = [];
  for (const block of blocks) {
    let name = "";
    const data: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) name = line.slice(6).trim();
      else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
    }
    if (!name || data.length === 0) continue;
    try {
      events.push({ type: name, ...JSON.parse(data.join("\n")) } as ChatEvent);
    } catch {
      // A damaged event is skipped; the stream goes on.
    }
  }
  return { events, rest };
}

/**
 * Asks a question and yields the events as they arrive. An unusable request (no model key, an invalid
 * question) throws an ApiError before anything is yielded; aborting the signal ends the stream quietly.
 */
export async function* chatStream(
  request: ChatRequest,
  signal?: AbortSignal,
  fetchFn: typeof fetch = fetch,
): AsyncGenerator<ChatEvent> {
  const query = filtersToParams(request.filters).toString();
  let res: Response;
  try {
    res = await fetchFn(`${API_BASE}/chat${query ? `?${query}` : ""}`, {
      method: "POST",
      headers: { "content-type": "application/json", accept: "text/event-stream" },
      body: JSON.stringify({ question: request.question, session_id: request.sessionId }),
      cache: "no-store",
      signal,
    });
  } catch {
    if (signal?.aborted) return;
    throw new ApiError(0, "Network error");
  }
  if (!res.ok) throw parseError(res.status, await res.json().catch(() => null));
  if (!res.body) return;

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parsed = parseEvents(buffer);
      buffer = parsed.rest;
      yield* parsed.events;
    }
  } catch (error) {
    if (signal?.aborted) return;
    throw error instanceof ApiError ? error : new ApiError(0, "The connection was lost");
  } finally {
    reader.cancel().catch(() => undefined);
  }
}
