import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { SessionList } from "./SessionList";
import type { ChatSessionSummary } from "@/lib/chatSessions";

const session = (id: string, title: string): ChatSessionSummary => ({
  id,
  title,
  created_at: "2026-11-09T10:00:00Z",
  updated_at: "2026-11-09T10:00:00Z",
  message_count: 2,
});

function setup(props: Partial<React.ComponentProps<typeof SessionList>> = {}) {
  const handlers = {
    onRetry: vi.fn(),
    onOpen: vi.fn(),
    onNew: vi.fn(),
    onRename: vi.fn().mockResolvedValue(undefined),
    onDelete: vi.fn().mockResolvedValue(undefined),
  };
  render(
    <SessionList
      sessions={[session("a", "Hosting invoices"), session("b", "Payment terms")]}
      loading={false}
      failed={false}
      activeId={null}
      {...handlers}
      {...props}
    />,
  );
  return handlers;
}

describe("SessionList", () => {
  it("lists the titles in the given order and marks the open chat", () => {
    setup({ activeId: "b" });

    const items = within(screen.getByRole("list")).getAllByRole("listitem");
    expect(items.map((i) => i.textContent)).toEqual([expect.stringContaining("Hosting invoices"), expect.stringContaining("Payment terms")]);
    expect(screen.getByRole("button", { name: "Payment terms" })).toHaveAttribute("aria-current", "true");
    expect(screen.getByRole("button", { name: "Hosting invoices" })).not.toHaveAttribute("aria-current");
  });

  it("opens a chat and starts a new one", async () => {
    const h = setup();

    await userEvent.click(screen.getByRole("button", { name: "Payment terms" }));
    await userEvent.click(screen.getByRole("button", { name: "New chat" }));

    expect(h.onOpen).toHaveBeenCalledWith("b");
    expect(h.onNew).toHaveBeenCalledTimes(1);
  });

  it("says there are no saved chats yet", () => {
    setup({ sessions: [] });

    expect(screen.getByText("No saved chats yet.")).toBeInTheDocument();
  });

  it("shows an error with a retry when the list cannot be loaded", async () => {
    const h = setup({ sessions: undefined, failed: true });

    expect(screen.getByRole("alert")).toHaveTextContent("could not be loaded");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(h.onRetry).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "New chat" })).toBeEnabled();
  });

  it("renames in place with Enter", async () => {
    const h = setup();

    await userEvent.click(screen.getByRole("button", { name: "Rename Hosting invoices" }));
    const input = screen.getByRole("textbox", { name: "Chat name" });
    expect(input).toHaveValue("Hosting invoices");
    await userEvent.clear(input);
    await userEvent.type(input, "  Supplier Q4  {Enter}");

    expect(h.onRename).toHaveBeenCalledWith("a", "Supplier Q4");
    expect(screen.queryByRole("textbox", { name: "Chat name" })).not.toBeInTheDocument();
  });

  it("cancels a rename with Escape and sends nothing", async () => {
    const h = setup();

    await userEvent.click(screen.getByRole("button", { name: "Rename Hosting invoices" }));
    await userEvent.type(screen.getByRole("textbox", { name: "Chat name" }), " changed{Escape}");

    expect(h.onRename).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Hosting invoices" })).toBeInTheDocument();
  });

  it.each([["blank", "{Control>}a{/Control}{Backspace}"], ["unchanged", ""]])("sends nothing for a %s title", async (_, typing) => {
    const h = setup();

    await userEvent.click(screen.getByRole("button", { name: "Rename Hosting invoices" }));
    if (typing) await userEvent.type(screen.getByRole("textbox", { name: "Chat name" }), typing);
    await userEvent.keyboard("{Enter}");

    expect(h.onRename).not.toHaveBeenCalled();
  });

  it("limits a title to 100 characters", async () => {
    setup();

    await userEvent.click(screen.getByRole("button", { name: "Rename Hosting invoices" }));

    expect(screen.getByRole("textbox", { name: "Chat name" })).toHaveAttribute("maxlength", "100");
  });

  it("keeps the old title and shows an error when the rename fails", async () => {
    const onRename = vi.fn().mockRejectedValue(new Error("no"));
    setup({ onRename });

    await userEvent.click(screen.getByRole("button", { name: "Rename Hosting invoices" }));
    await userEvent.type(screen.getByRole("textbox", { name: "Chat name" }), " X{Enter}");

    expect(onRename).toHaveBeenCalled();
    expect(await screen.findByRole("alert")).toHaveTextContent("could not be saved");
    expect(screen.getByRole("button", { name: "Hosting invoices" })).toBeInTheDocument();
  });

  it("deletes only after a confirmation", async () => {
    const h = setup();

    await userEvent.click(screen.getByRole("button", { name: "Delete Hosting invoices" }));
    expect(h.onDelete).not.toHaveBeenCalled();
    expect(screen.getByText("Delete “Hosting invoices”?")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));

    expect(h.onDelete).toHaveBeenCalledWith("a");
  });

  it("keeps the chat when the confirmation is cancelled", async () => {
    const h = setup();

    await userEvent.click(screen.getByRole("button", { name: "Delete Hosting invoices" }));
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(h.onDelete).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Hosting invoices" })).toBeInTheDocument();
  });

  it("shows an error when a delete fails", async () => {
    setup({ onDelete: vi.fn().mockRejectedValue(new Error("no")) });

    await userEvent.click(screen.getByRole("button", { name: "Delete Hosting invoices" }));
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("could not be deleted");
  });
});
