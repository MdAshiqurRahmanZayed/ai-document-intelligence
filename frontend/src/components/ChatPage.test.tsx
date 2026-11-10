import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChatPage } from "./ChatPage";
import { renderWithClient } from "@/test/helpers";

let search = "";
const push = vi.fn();
const replace = vi.fn();
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(search),
  useRouter: () => ({ push, replace }),
  usePathname: () => "/chat",
}));

const row = (id: string, title: string) => ({ id, title, created_at: "2026-11-09T10:00:00Z", updated_at: "2026-11-09T10:00:00Z", message_count: 2 });

interface Sessions {
  list: unknown[];
  failList?: boolean;
  failRename?: boolean;
}

/** The sessions API: list, create, read, rename, delete. Returns what was called. */
function stubSessions(state: Sessions) {
  const calls: { method: string; url: string; body?: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit = {}) => {
      const method = init.method ?? "GET";
      calls.push({ method, url, body: init.body ? JSON.parse(String(init.body)) : undefined });
      const id = url.split("?")[0].split("/").pop();
      if (method === "GET" && url.includes("sessions?")) {
        return state.failList ? Response.json({ detail: "bad gateway" }, { status: 502 }) : Response.json({ items: state.list, total: state.list.length });
      }
      if (method === "GET") return Response.json({ ...row(id ?? "", "Hosting invoices"), messages: [] });
      if (method === "PATCH") {
        if (state.failRename) return Response.json({ detail: "no" }, { status: 500 });
        return Response.json({ ...row(id ?? "", String(JSON.parse(String(init.body)).title)) });
      }
      if (method === "DELETE") return new Response(null, { status: 204 });
      state.list.unshift(row("new", "New chat")); // as the server does: the new chat is listed
      return Response.json(row("new", "New chat"), { status: 201 });
    }),
  );
  return calls;
}

beforeEach(() => {
  search = "";
  push.mockReset();
  replace.mockReset();
});
afterEach(() => vi.unstubAllGlobals());

describe("ChatPage", () => {
  it("lists the saved chats, and opening one puts it in the address", async () => {
    stubSessions({ list: [row("a", "Hosting invoices"), row("b", "Payment terms")] });
    renderWithClient(<ChatPage />);

    const nav = await screen.findByRole("navigation", { name: "Saved chats" });
    expect(await within(nav).findByRole("button", { name: "Payment terms" })).toBeInTheDocument();
    await userEvent.click(within(nav).getByRole("button", { name: "Payment terms" }));

    expect(push).toHaveBeenCalledWith("/chat?session=b");
  });

  it("starts a new chat by clearing the address", async () => {
    search = "session=a";
    stubSessions({ list: [row("a", "Hosting invoices")] });
    renderWithClient(<ChatPage />);

    await userEvent.click(await screen.findByRole("button", { name: "New chat" }));

    expect(push).toHaveBeenCalledWith("/chat");
  });

  it("still lets a question be asked when the list cannot be loaded, and offers a retry", async () => {
    stubSessions({ list: [], failList: true });
    renderWithClient(<ChatPage />);

    expect(await screen.findByText(/could not be loaded/)).toBeInTheDocument();
    expect(screen.getByLabelText("Ask about your documents")).toBeEnabled();
  });

  it("renames a chat through the API and shows the new title", async () => {
    const calls = stubSessions({ list: [row("a", "Hosting invoices")] });
    renderWithClient(<ChatPage />);

    await userEvent.click(await screen.findByRole("button", { name: "Rename Hosting invoices" }));
    const input = screen.getByRole("textbox", { name: "Chat name" });
    await userEvent.clear(input);
    await userEvent.type(input, "Supplier Q4{Enter}");

    expect(await screen.findByRole("button", { name: "Supplier Q4" })).toBeInTheDocument();
    const patch = calls.find((c) => c.method === "PATCH");
    expect(patch).toMatchObject({ url: "/api/backend/chat/sessions/a", body: { title: "Supplier Q4" } });
  });

  it("keeps the old title and shows an error when the rename fails", async () => {
    stubSessions({ list: [row("a", "Hosting invoices")], failRename: true });
    renderWithClient(<ChatPage />);

    await userEvent.click(await screen.findByRole("button", { name: "Rename Hosting invoices" }));
    await userEvent.type(screen.getByRole("textbox", { name: "Chat name" }), " X{Enter}");

    expect(await screen.findByText(/name could not be saved/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Hosting invoices" })).toBeInTheDocument();
  });

  it("deletes a chat after confirming, and leaves it when it was open", async () => {
    search = "session=a";
    const calls = stubSessions({ list: [row("a", "Hosting invoices"), row("b", "Payment terms")] });
    renderWithClient(<ChatPage />);

    await userEvent.click(await screen.findByRole("button", { name: "Delete Hosting invoices" }));
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));

    await waitFor(() => expect(screen.queryByRole("button", { name: "Hosting invoices" })).not.toBeInTheDocument());
    expect(calls.some((c) => c.method === "DELETE" && c.url === "/api/backend/chat/sessions/a")).toBe(true);
    expect(push).toHaveBeenCalledWith("/chat");
    expect(screen.getByRole("button", { name: "Payment terms" })).toBeInTheDocument();
  });

  it("puts a new chat at the top of the list, and in the address, with the first question", async () => {
    const state: Sessions = { list: [row("a", "Hosting invoices")] };
    stubSessions(state);
    const enc = new TextEncoder();
    const done = () =>
      new Response(
      new ReadableStream({
        start(c) {
          c.enqueue(enc.encode('event: sources\ndata: {"sources": []}\n\n'));
          c.enqueue(enc.encode('event: token\ndata: {"text": "Nothing."}\n\n'));
          c.enqueue(enc.encode('event: done\ndata: {"citations": [], "suggestions": []}\n\n'));
          c.close();
        },
      }),
      { headers: { "content-type": "text/event-stream" } },
    );
    const base = vi.mocked(fetch);
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        if (url.includes("/chat/sessions")) return base(url, init);
        // the server titles a new chat from its first question
        (state.list[0] as { title: string }).title = JSON.parse(String(init?.body)).question;
        return done();
      }),
    );
    renderWithClient(<ChatPage />);
    await screen.findByRole("button", { name: "Hosting invoices" });

    await userEvent.type(screen.getByLabelText("Ask about your documents"), "Where is the freight invoice?");
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/chat?session=new"));
    const titles = within(screen.getByRole("navigation", { name: "Saved chats" })).getAllByRole("button", { name: /^(Hosting|Where)/ });
    expect(titles[0]).toHaveTextContent("Where is the freight invoice?");
  });
});
