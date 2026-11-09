import { QueryClientProvider } from "@tanstack/react-query";
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ChatView } from "./ChatView";
import type { ChatSessionDetail, StoredMessage } from "@/lib/chatSessions";
import { ToastProvider } from "@/components/ui/Toast";
import { renderWithClient } from "@/test/helpers";

afterEach(() => vi.unstubAllGlobals());

const enc = new TextEncoder();
const sse = (name: string, body: unknown) => enc.encode(`event: ${name}\ndata: ${JSON.stringify(body)}\n\n`);
const SOURCE = { n: 1, document_id: "d1", filename: "cirrus.pdf", page_no: 2, quote: "Hosting 4500 SEK" };

type Part = [string, unknown];
const events = (...parts: Part[]) => parts.map(([name, body]) => sse(name, body));
const whole = (...parts: Part[]) =>
  new Response(new ReadableStream({ start: (c) => (events(...parts).forEach((e) => c.enqueue(e)), c.close()) }), {
    headers: { "content-type": "text/event-stream" },
  });

const ANSWER = (text = "Cirrus [1].", suggestions: string[] = []): Part[] => [
  ["sources", { sources: [SOURCE] }],
  ["token", { text }],
  ["done", { citations: [1], suggestions }],
];

interface Call {
  url: string;
  body: { question: string; session_id: string };
}

const CREATED = { id: "s1", title: "New chat", created_at: "2026-11-09T10:00:00Z", updated_at: "2026-11-09T10:00:00Z", message_count: 0 };

/** The session calls made, apart from the questions. */
interface SessionCall {
  method: string;
  url: string;
}

/**
 * Answers each question with the next response; an open stream is fed by the test. Creating a session
 * answers with `s1`, and reading one answers from `saved`, by id; those calls are listed in `sessions`.
 */
function stubChat(...responses: (Response | ((signal: AbortSignal) => Response))[]) {
  return stub({}, responses);
}

function stub(saved: Record<string, ChatSessionDetail>, responses: (Response | ((signal: AbortSignal) => Response))[]) {
  const calls: Call[] = [];
  const sessions: SessionCall[] = [];
  const fn = vi.fn(async (url: string, init: RequestInit = {}) => {
    if (url.includes("/chat/sessions")) {
      const method = init.method ?? "GET";
      sessions.push({ method, url });
      if (method === "POST") return Response.json(CREATED, { status: 201 });
      const hit = saved[url.split("/").pop() ?? ""];
      return hit ? Response.json(hit) : Response.json({ detail: { reason: "session_not_found" } }, { status: 404 });
    }
    calls.push({ url, body: JSON.parse(String(init.body)) });
    const next = responses[Math.min(calls.length, responses.length) - 1];
    return typeof next === "function" ? next(init.signal as AbortSignal) : next;
  });
  vi.stubGlobal("fetch", fn);
  return Object.assign(calls, { sessions });
}

const stored = (role: "user" | "assistant", id: number, content: string, extra: Partial<StoredMessage> = {}): StoredMessage => ({
  id,
  role,
  content,
  sources: null,
  citations: null,
  suggestions: null,
  rewritten_question: null,
  status: null,
  created_at: "2026-11-09T10:00:00Z",
  ...extra,
});

const savedSession = (messages: StoredMessage[], id = "s1"): ChatSessionDetail => ({ ...CREATED, id, title: "Hosting", message_count: messages.length, messages });

/** A stream that stays open until the test closes it; aborting errors it, as a real fetch does. */
function openStream() {
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  const make = (signal: AbortSignal) => {
    signal.addEventListener("abort", () => controller.error(new DOMException("Aborted", "AbortError")));
    return new Response(new ReadableStream({ start: (c) => void (controller = c) }), {
      headers: { "content-type": "text/event-stream" },
    });
  };
  return {
    make,
    push: (name: string, body: unknown) => controller.enqueue(sse(name, body)),
    close: () => controller.close(),
  };
}

async function ask(question: string) {
  await userEvent.type(screen.getByLabelText("Ask about your documents"), question);
  await userEvent.click(screen.getByRole("button", { name: "Ask" }));
}

describe("ChatView", () => {
  it("shows the question, the sources, and the answer with its citation chip", async () => {
    stubChat(whole(...ANSWER()));
    renderWithClient(<ChatView />);

    await ask("Who billed hosting?");

    expect(await screen.findByRole("button", { name: "Source 1" })).toBeInTheDocument();
    const sources = screen.getByRole("list", { name: "Sources" });
    expect(within(sources).getByRole("link", { name: "cirrus.pdf" })).toHaveAttribute("href", "/documents/d1");
    expect(within(sources).getByText("page 2")).toBeInTheDocument();
    expect(within(sources).getByText("Hosting 4500 SEK")).toBeInTheDocument();
    expect(screen.getByText("Who billed hosting?")).toBeInTheDocument();
  });

  it("lists the sources as numbered rows beside the answer, which comes first", async () => {
    const two = { ...SOURCE, n: 2, document_id: "d2", filename: "scan.png", page_no: 1, quote: "Fabrikam" };
    stubChat(whole(["sources", { sources: [SOURCE, two] }], ["token", { text: "Both [1][2]." }], ["done", { citations: [1, 2], suggestions: [] }]));
    const { container } = renderWithClient(<ChatView />);

    await ask("Who billed hosting?");

    const list = await screen.findByRole("list", { name: "Sources" });
    const rows = within(list).getAllByRole("listitem");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("1cirrus.pdfpage 2Hosting 4500 SEK");
    expect(rows[1]).toHaveTextContent("2scan.pngpage 1Fabrikam");
    expect(screen.getByRole("heading", { name: "Sources · 2" })).toBeInTheDocument();
    // two columns on a wide screen: the answer first, the list after it (below it on a narrow one)
    const grid = container.querySelector("[class*='lg:grid-cols']") as HTMLElement;
    expect(grid.firstElementChild).toHaveTextContent("Both");
    expect(grid.lastElementChild).toContainElement(list);
  });

  it("lists only the sources the finished answer cites, with their own numbers", async () => {
    const rows = [1, 2, 3].map((n) => ({ ...SOURCE, n, document_id: `d${n}`, filename: `file${n}.pdf`, quote: `quote ${n}` }));
    stubChat(whole(["sources", { sources: rows }], ["token", { text: "Only the second [2]." }], ["done", { citations: [2], suggestions: [] }]));
    renderWithClient(<ChatView />);

    await ask("Which file?");

    const list = await screen.findByRole("list", { name: "Sources" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(1);
    expect(within(list).getByText("file2.pdf")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Sources · 1" })).toBeInTheDocument();
    expect(screen.queryByText("file1.pdf")).not.toBeInTheDocument();
  });

  it("shows everything being read while the answer is written, then only what it cites", async () => {
    const stream = openStream();
    stubChat(stream.make);
    renderWithClient(<ChatView />);
    const rows = [1, 2].map((n) => ({ ...SOURCE, n, filename: `file${n}.pdf` }));

    await ask("Which file?");
    stream.push("sources", { sources: rows });
    expect(await screen.findByText("file1.pdf")).toBeInTheDocument();
    expect(screen.getByText("file2.pdf")).toBeInTheDocument();
    stream.push("token", { text: "It is [1]." });
    stream.push("done", { citations: [1], suggestions: [] });
    stream.close();

    await waitFor(() => expect(screen.queryByText("file2.pdf")).not.toBeInTheDocument());
    expect(screen.getByText("file1.pdf")).toBeInTheDocument();
  });

  it("shows no source list when the answer cites nothing", async () => {
    stubChat(whole(["sources", { sources: [SOURCE] }], ["token", { text: "I can't tell from these documents." }], ["done", { citations: [], suggestions: [] }]));
    renderWithClient(<ChatView />);

    await ask("Something else?");

    await screen.findByText(/can't tell/);
    expect(screen.queryByRole("list", { name: "Sources" })).not.toBeInTheDocument();
  });

  it("highlights the source of a chip while it is hovered or focused", async () => {
    stubChat(whole(...ANSWER()));
    renderWithClient(<ChatView />);
    await ask("Who billed hosting?");
    const chip = await screen.findByRole("button", { name: "Source 1" });
    const row = within(screen.getByRole("list", { name: "Sources" })).getByRole("listitem");
    expect(row).toHaveAttribute("data-active", "false");

    await userEvent.hover(chip);
    expect(row).toHaveAttribute("data-active", "true");
    await userEvent.unhover(chip);
    expect(row).toHaveAttribute("data-active", "false");

    await act(async () => chip.focus());
    expect(row).toHaveAttribute("data-active", "true");
    await act(async () => chip.blur());
    expect(row).toHaveAttribute("data-active", "false");
  });

  it("uses the full width and shows no source list when nothing was found", async () => {
    stubChat(whole(["sources", { sources: [] }], ["token", { text: "I couldn't find anything." }], ["done", { citations: [], suggestions: [] }]));
    const { container } = renderWithClient(<ChatView />);

    await ask("zebra");

    await screen.findByText("I couldn't find anything.");
    expect(screen.queryByRole("list", { name: "Sources" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /Sources/ })).not.toBeInTheDocument();
    expect(container.querySelector("[class*='lg:grid-cols']")).toBeNull();
  });

  it("shows the sources before the first word and grows the answer as it arrives", async () => {
    const stream = openStream();
    stubChat(stream.make);
    renderWithClient(<ChatView />);

    await ask("Who billed hosting?");
    stream.push("sources", { sources: [SOURCE] });

    const sources = await screen.findByRole("list", { name: "Sources" });
    expect(within(sources).getByText("cirrus.pdf")).toBeInTheDocument();
    expect(screen.getByText("Writing the answer…")).toBeInTheDocument();

    stream.push("token", { text: "Cirrus " });
    expect(await screen.findByText(/Cirrus/)).toBeInTheDocument();
    stream.push("token", { text: "billed it." });
    expect(await screen.findByText(/billed it\./)).toBeInTheDocument();
    stream.push("done", { citations: [], suggestions: [] });
    stream.close();
  });

  it("makes sending impossible while an answer streams, and Stop keeps the text so far", async () => {
    const stream = openStream();
    const calls = stubChat(stream.make);
    renderWithClient(<ChatView />);

    await ask("Who billed hosting?");
    stream.push("sources", { sources: [SOURCE] });
    stream.push("token", { text: "Cirrus billed" });
    await screen.findByText(/Cirrus billed/);

    expect(screen.queryByRole("button", { name: "Ask" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Stop" }));

    await screen.findByText("Stopped.");
    expect(screen.getByText(/Cirrus billed/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ask" })).toBeInTheDocument();
    expect(calls).toHaveLength(1);
  });

  it("sends nothing for a blank question", async () => {
    const calls = stubChat(whole(...ANSWER()));
    renderWithClient(<ChatView />);

    await userEvent.type(screen.getByLabelText("Ask about your documents"), "   ");

    expect(screen.getByRole("button", { name: "Ask" })).toBeDisabled();
    await userEvent.keyboard("{Enter}");
    expect(calls).toHaveLength(0);
  });

  it("sends a suggested follow-up into the same session, without history", async () => {
    const calls = stubChat(whole(...ANSWER("Cirrus [1].", ["What was the total?"])), whole(...ANSWER("Total is 9999 [1].")));
    renderWithClient(<ChatView />);

    await ask("Who billed hosting?");
    await userEvent.click(await screen.findByRole("button", { name: "What was the total?" }));

    await waitFor(() => expect(calls).toHaveLength(2));
    expect(calls[1].body).toEqual({ question: "What was the total?", session_id: "s1" });
    expect(calls[0].body.session_id).toBe("s1");
    expect(calls.sessions.filter((c) => c.method === "POST")).toHaveLength(1);
    expect(await screen.findByText(/Total is 9999/)).toBeInTheDocument();
  });

  it("sends the filters with the question", async () => {
    const calls = stubChat(whole(...ANSWER()));
    renderWithClient(<ChatView />);

    await userEvent.type(screen.getByLabelText("Currency"), "SEK");
    await userEvent.click(screen.getByRole("button", { name: "Apply filters" }));
    await ask("Who billed hosting?");

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].url).toBe("/api/backend/chat?currency=SEK");
  });

  it("shows a suggestion button to try an example question", async () => {
    const calls = stubChat(whole(...ANSWER()));
    renderWithClient(<ChatView />);

    await userEvent.click(screen.getByRole("button", { name: "Which supplier invoiced hosting?" }));

    await waitFor(() => expect(calls[0]?.body.question).toBe("Which supplier invoiced hosting?"));
  });

  it("shows the rewritten question", async () => {
    stubChat(whole(["sources", { sources: [SOURCE], rewritten_question: "tax on EV-1011" }], ["token", { text: "25" }], ["done", { citations: [], suggestions: [] }]));
    renderWithClient(<ChatView />);

    await ask("and its tax?");

    expect(await screen.findByText("Searched for: tax on EV-1011")).toBeInTheDocument();
  });

  it("shows nothing found as an answer without source cards", async () => {
    stubChat(whole(["sources", { sources: [] }], ["token", { text: "I couldn't find anything." }], ["done", { citations: [], suggestions: [] }]));
    renderWithClient(<ChatView />);

    await ask("zebra");

    expect(await screen.findByText("I couldn't find anything.")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Sources" })).not.toBeInTheDocument();
    expect(screen.getByText("Try another question, or remove a filter.")).toBeInTheDocument();
  });

  it("explains that chat needs a key", async () => {
    stubChat(Response.json({ detail: { reason: "chat_unavailable" } }, { status: 409 }));
    renderWithClient(<ChatView />);

    await ask("hello");

    expect(await screen.findByText("Chat is not available")).toBeInTheDocument();
    expect(screen.getByText("It needs a configured Google API key.")).toBeInTheDocument();
  });

  it.each([
    ["provider_limited", /provider's limit has been reached/],
    ["model_failed", /could not be written/],
  ])("shows %s with a retry that asks again", async (reason, message) => {
    const calls = stubChat(whole(["sources", { sources: [SOURCE] }], ["error", { reason }]), whole(...ANSWER("Retried [1].")));
    renderWithClient(<ChatView />);

    await ask("Who billed hosting?");
    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByText(/Retried/)).toBeInTheDocument();
    expect(calls).toHaveLength(2);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getAllByText("Who billed hosting?")).toHaveLength(1);
  });

  it("shows a failed request with a retry", async () => {
    stubChat(Response.json({ detail: "bad gateway" }, { status: 502 }));
    renderWithClient(<ChatView />);

    await ask("hello");

    expect(await screen.findByText("Something went wrong")).toBeInTheDocument();
    expect(screen.getByText(/API could not be reached/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("marks a stream that ends without done as failed", async () => {
    stubChat(whole(["sources", { sources: [SOURCE] }], ["token", { text: "Half an ans" }]));
    renderWithClient(<ChatView />);

    await ask("hello");

    expect(await screen.findByRole("alert")).toHaveTextContent(/could not be written/);
    expect(screen.getByText(/Half an ans/)).toBeInTheDocument();
  });
});

/** Shows the same view for another chat, keeping its providers so that it is not remounted. */
function showChat(view: ReturnType<typeof renderWithClient>, sessionId: string | null) {
  view.rerender(
    <QueryClientProvider client={view.client}>
      <ToastProvider>
        <ChatView sessionId={sessionId} />
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe("ChatView sessions", () => {
  it("creates a session on the first question and tells the page, once", async () => {
    stubChat(whole(...ANSWER()), whole(...ANSWER("Again [1].")));
    const onSessionChange = vi.fn();
    const onTurnEnd = vi.fn();
    renderWithClient(<ChatView onSessionChange={onSessionChange} onTurnEnd={onTurnEnd} />);

    await ask("Who   billed hosting?");
    await screen.findByText(/Cirrus/);
    await ask("And again?");
    await screen.findByText(/Again/);

    expect(onSessionChange).toHaveBeenCalledTimes(1);
    expect(onSessionChange).toHaveBeenCalledWith("s1", expect.objectContaining({ id: "s1", title: "Who billed hosting?" }));
    expect(onTurnEnd).toHaveBeenCalledTimes(2);
  });

  it("shows a failed session creation as an error with a retry", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Response.json({ detail: "bad gateway" }, { status: 502 })));
    renderWithClient(<ChatView />);

    await ask("hello");

    expect(await screen.findByText("Something went wrong")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("restores saved answers with chips, sources and follow-ups, and continues the same session", async () => {
    const two = { ...SOURCE, n: 2, document_id: "d2", filename: "scan.png", page_no: 1, quote: "Fabrikam" };
    const calls = stub(
      { s1: savedSession([
        stored("user", 1, "Who billed hosting?"),
        stored("assistant", 2, "Cirrus [1].", { sources: [SOURCE], citations: [1], status: "done", suggestions: [] }),
        stored("user", 3, "And freight?"),
        stored("assistant", 4, "Fabrikam [2].", { sources: [SOURCE, two], citations: [2], status: "done", suggestions: ["What was the total?"], rewritten_question: "freight supplier" }),
      ]) },
      [whole(...ANSWER("Total is 9999 [1]."))],
    );
    renderWithClient(<ChatView sessionId="s1" />);

    expect(await screen.findByText("Who billed hosting?")).toBeInTheDocument();
    expect(screen.getByText("And freight?")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /^Source / })).toHaveLength(2);
    expect(screen.getAllByRole("list", { name: "Sources" })).toHaveLength(2);
    expect(screen.getByText("Searched for: freight supplier")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "What was the total?" }));

    expect(await screen.findByText(/Total is 9999/)).toBeInTheDocument();
    expect(calls[0].body.session_id).toBe("s1");
    expect(calls.sessions.filter((c) => c.method === "POST")).toHaveLength(0);
  });

  it("marks a saved stopped answer as stopped and a saved failed answer with a retry", async () => {
    const calls = stub(
      { s1: savedSession([
        stored("user", 1, "first"),
        stored("assistant", 2, "Part of an answer", { sources: [SOURCE], status: "stopped", suggestions: [] }),
        stored("user", 3, "second"),
        stored("assistant", 4, "Half", { sources: [SOURCE], status: "failed", suggestions: [] }),
      ]) },
      [whole(...ANSWER("Retried [1]."))],
    );
    renderWithClient(<ChatView sessionId="s1" />);

    expect(await screen.findByText("Stopped.")).toBeInTheDocument();
    expect(screen.getByText(/Part of an answer/)).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(/could not be written/);
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByText(/Retried/)).toBeInTheDocument();
    expect(calls[0].body).toEqual({ question: "second", session_id: "s1" });
  });

  it("shows a not-found state, with a link to a new chat, for an unknown session", async () => {
    stubChat();
    renderWithClient(<ChatView sessionId="gone" />);

    expect(await screen.findByText("This chat was not found")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Start a new chat" })).toHaveAttribute("href", "/chat");
    expect(screen.getByRole("button", { name: "Ask" })).toBeDisabled();
  });

  it("shows not found, not a connection error, for an id the API rejects as invalid", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Response.json({ detail: [{ loc: ["path", "session_id"], msg: "Input should be a valid UUID" }] }, { status: 422 })));
    renderWithClient(<ChatView sessionId="not-a-uuid" />);

    expect(await screen.findByText("This chat was not found")).toBeInTheDocument();
    expect(screen.queryByText("Something went wrong")).not.toBeInTheDocument();
  });

  it("shows a retryable error when the saved chat cannot be loaded", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Response.json({ detail: "bad gateway" }, { status: 502 })));
    renderWithClient(<ChatView sessionId="s1" />);

    expect(await screen.findByText("Something went wrong")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("stops a streaming answer before showing another chat", async () => {
    const stream = openStream();
    let streamSignal: AbortSignal | undefined;
    stub({ s2: savedSession([stored("user", 1, "older question"), stored("assistant", 2, "Older answer", { sources: [], status: "done", suggestions: [] })], "s2") }, [(signal) => ((streamSignal = signal), stream.make(signal))]);
    const view = renderWithClient(<ChatView />);

    await ask("Who billed hosting?");
    stream.push("sources", { sources: [SOURCE] });
    stream.push("token", { text: "Cirrus billed" });
    await screen.findByText(/Cirrus billed/);
    showChat(view, "s2");

    expect(await screen.findByText("Older answer")).toBeInTheDocument();
    expect(streamSignal?.aborted).toBe(true);
    expect(screen.queryByText(/Cirrus billed/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ask" })).toBeInTheDocument();
  });

  it("clears the conversation when the chat is left for a new one", async () => {
    stub({ s1: savedSession([stored("user", 1, "first"), stored("assistant", 2, "An answer", { sources: [], status: "done", suggestions: [] })]) }, []);
    const view = renderWithClient(<ChatView sessionId="s1" />);
    await screen.findByText("An answer");

    showChat(view, null);

    expect(await screen.findByText("Try one of these:")).toBeInTheDocument();
    expect(screen.queryByText("An answer")).not.toBeInTheDocument();
  });
});
