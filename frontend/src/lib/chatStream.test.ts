import { describe, expect, it, vi } from "vitest";

import { ApiError } from "./api";
import { chatStream, parseEvents, type ChatEvent } from "./chatStream";

const enc = new TextEncoder();
const event = (name: string, body: unknown) => `event: ${name}\ndata: ${JSON.stringify(body)}\n\n`;

function responseOf(chunks: string[]): Response {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(enc.encode(chunk));
      controller.close();
    },
  });
  return new Response(stream, { headers: { "content-type": "text/event-stream" } });
}

async function collect(fetchFn: typeof fetch, signal?: AbortSignal): Promise<ChatEvent[]> {
  const events: ChatEvent[] = [];
  for await (const e of chatStream({ question: "q", sessionId: "s1", filters: {} }, signal, fetchFn)) events.push(e);
  return events;
}

describe("parseEvents", () => {
  it("reads whole events and returns the unfinished rest", () => {
    const { events, rest } = parseEvents(event("token", { text: "a" }) + 'event: token\ndata: {"te');

    expect(events).toEqual([{ type: "token", text: "a" }]);
    expect(rest).toBe('event: token\ndata: {"te');
  });

  it("reads several events from one chunk", () => {
    const { events } = parseEvents(event("token", { text: "a" }) + event("token", { text: "b" }));

    expect(events.map((e) => (e as { text: string }).text)).toEqual(["a", "b"]);
  });

  it("accepts CRLF line ends and skips a damaged event", () => {
    const { events } = parseEvents('event: token\r\ndata: {broken\r\n\r\n' + event("token", { text: "ok" }).replaceAll("\n", "\r\n"));

    expect(events).toEqual([{ type: "token", text: "ok" }]);
  });
});

describe("chatStream", () => {
  it("yields events split in the middle of a line and of the JSON", async () => {
    const whole = event("sources", { sources: [] }) + event("token", { text: "héllo ✓" }) + event("done", { citations: [], suggestions: [] });
    const cut = [whole.slice(0, 20), whole.slice(20, 60), whole.slice(60)];

    const events = await collect(vi.fn().mockResolvedValue(responseOf(cut)));

    expect(events.map((e) => e.type)).toEqual(["sources", "token", "done"]);
    expect(events[1]).toEqual({ type: "token", text: "héllo ✓" });
  });

  it("does not break a multi-byte character split between chunks", async () => {
    const bytes = enc.encode(event("token", { text: "✓✓" }));
    const at = bytes.indexOf(0xe2) + 1; // inside the first ✓
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(bytes.slice(0, at));
        controller.enqueue(bytes.slice(at));
        controller.close();
      },
    });

    const events = await collect(vi.fn().mockResolvedValue(new Response(stream)));

    expect(events).toEqual([{ type: "token", text: "✓✓" }]);
  });

  it("passes an error event on as an event", async () => {
    const events = await collect(vi.fn().mockResolvedValue(responseOf([event("error", { reason: "provider_limited" })])));

    expect(events).toEqual([{ type: "error", reason: "provider_limited" }]);
  });

  it("posts the question with its session, and the filters in the query", async () => {
    const fetchFn = vi.fn<typeof fetch>(async () => responseOf([]));

    await collect(fetchFn);
    for await (const _ of chatStream(
      { question: "and its tax?", sessionId: "s1", filters: { currency: "SEK" } },
      undefined,
      fetchFn,
    )) void _;

    const [url, init] = fetchFn.mock.calls[1];
    expect(url).toBe("/api/backend/chat?currency=SEK");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({ question: "and its tax?", session_id: "s1" });
  });

  it("turns a 409 chat_unavailable into a typed error before anything is yielded", async () => {
    const fetchFn = vi.fn().mockResolvedValue(Response.json({ detail: { reason: "chat_unavailable" } }, { status: 409 }));

    await expect(collect(fetchFn)).rejects.toMatchObject({ status: 409, reason: "chat_unavailable" });
  });

  it("turns a network failure into an ApiError", async () => {
    const fetchFn = vi.fn().mockRejectedValue(new TypeError("fetch failed"));

    await expect(collect(fetchFn)).rejects.toBeInstanceOf(ApiError);
  });

  it("stops reading quietly when aborted", async () => {
    const abort = new AbortController();
    let controller!: ReadableStreamDefaultController<Uint8Array>;
    const stream = new ReadableStream<Uint8Array>({
      start(c) {
        controller = c;
        c.enqueue(enc.encode(event("token", { text: "a" })));
      },
    });
    const fetchFn = vi.fn().mockResolvedValue(new Response(stream));
    const seen: ChatEvent[] = [];

    const reading = (async () => {
      for await (const e of chatStream({ question: "q", sessionId: "s1", filters: {} }, abort.signal, fetchFn)) {
        seen.push(e);
        abort.abort();
        controller.error(new DOMException("Aborted", "AbortError"));
      }
    })();

    await expect(reading).resolves.toBeUndefined();
    expect(seen).toEqual([{ type: "token", text: "a" }]);
  });
});
