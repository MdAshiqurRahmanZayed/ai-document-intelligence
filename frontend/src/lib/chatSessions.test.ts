import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "./api";
import { chatSessions, turnsFromMessages, type StoredMessage } from "./chatSessions";

afterEach(() => vi.unstubAllGlobals());

const SOURCE = { n: 1, document_id: "d1", filename: "cirrus.pdf", page_no: 2, quote: "Hosting 4500 SEK" };

const user = (id: number, content: string): StoredMessage => ({
  id,
  role: "user",
  content,
  sources: null,
  citations: null,
  suggestions: null,
  rewritten_question: null,
  status: null,
  created_at: "2026-11-09T10:00:00Z",
});

const assistant = (id: number, content: string, extra: Partial<StoredMessage> = {}): StoredMessage => ({
  ...user(id, content),
  role: "assistant",
  sources: [SOURCE],
  citations: [1],
  suggestions: ["What was the total?"],
  status: "done",
  ...extra,
});

describe("turnsFromMessages", () => {
  it("turns a question and its answer into one turn with everything the page shows", () => {
    const turns = turnsFromMessages([user(1, "Who billed hosting?"), assistant(2, "Cirrus [1].", { rewritten_question: "hosting supplier" })]);

    expect(turns).toEqual([
      {
        id: 0,
        question: "Who billed hosting?",
        answer: "Cirrus [1].",
        sources: [SOURCE],
        rewritten: "hosting supplier",
        suggestions: ["What was the total?"],
        citations: [1],
        phase: "done",
        failure: null,
      },
    ]);
  });

  it("keeps order and numbers the turns from the given id", () => {
    const turns = turnsFromMessages([user(1, "a"), assistant(2, "A"), user(3, "b"), assistant(4, "B")], 10);

    expect(turns.map((t) => [t.id, t.question, t.answer])).toEqual([
      [10, "a", "A"],
      [11, "b", "B"],
    ]);
  });

  it("marks a stopped answer as stopped and a failed one as failed", () => {
    const turns = turnsFromMessages([
      user(1, "a"),
      assistant(2, "part", { status: "stopped" }),
      user(3, "b"),
      assistant(4, "half", { status: "failed" }),
    ]);

    expect(turns[0]).toMatchObject({ phase: "stopped", answer: "part", failure: null, citations: null });
    expect(turns[1]).toMatchObject({ phase: "failed", answer: "half", failure: { reason: "model_failed" } });
  });

  it("shows a question with no saved answer as failed, so it can be asked again", () => {
    const turns = turnsFromMessages([user(1, "a"), user(2, "b"), assistant(3, "B")]);

    expect(turns[0]).toMatchObject({ question: "a", answer: "", phase: "failed" });
    expect(turns[1]).toMatchObject({ question: "b", answer: "B", phase: "done" });
  });

  it("shows an answer with no sources (nothing found) without a list", () => {
    const [turn] = turnsFromMessages([user(1, "zebra"), assistant(2, "nothing", { sources: [], suggestions: [] })]);

    expect(turn.sources).toEqual([]);
    expect(turn.phase).toBe("done");
  });
});

describe("chatSessions", () => {
  it("renames with a PATCH and deletes with a DELETE through the proxy", async () => {
    const fn = vi.fn(async (_url: string, init?: RequestInit) =>
      init?.method === "DELETE" ? new Response(null, { status: 204 }) : Response.json({ id: "s1", title: "Hosting" }),
    );
    vi.stubGlobal("fetch", fn);

    await chatSessions.rename("s1", "Hosting");
    await expect(chatSessions.remove("s1")).resolves.toBeUndefined();

    expect(fn.mock.calls[0][0]).toBe("/api/backend/chat/sessions/s1");
    expect(fn.mock.calls[0][1]?.method).toBe("PATCH");
    expect(JSON.parse(String(fn.mock.calls[0][1]?.body))).toEqual({ title: "Hosting" });
    expect(fn.mock.calls[1][1]?.method).toBe("DELETE");
  });

  it("turns an error answer into an ApiError with its reason", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Response.json({ detail: { reason: "session_not_found" } }, { status: 404 })));

    await expect(chatSessions.get("nope")).rejects.toMatchObject({ status: 404, reason: "session_not_found" });
    await expect(chatSessions.get("nope")).rejects.toBeInstanceOf(ApiError);
  });
});
