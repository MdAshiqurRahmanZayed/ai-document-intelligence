import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DocumentsView } from "./DocumentsView";
import { POLL_MS } from "@/hooks/useDocuments";
import type { DocumentListItem, DocumentStatus } from "@/lib/types";

const doc = (id: string, status: DocumentStatus, extra: Partial<DocumentListItem> = {}): DocumentListItem => ({
  id,
  filename: `${id}.pdf`,
  status,
  source_type: "pdf",
  page_count: 2,
  error_code: null,
  created_at: "2026-11-03T10:00:00Z",
  updated_at: "2026-11-03T10:00:00Z",
  invoices: [],
  ...extra,
});

function stubFetch(handler: (url: string) => unknown) {
  const fn = vi.fn(async (url: string) => Response.json(handler(url)));
  vi.stubGlobal("fetch", fn);
  return fn;
}

function renderView(filters = {}, onFiltersChange = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <DocumentsView filters={filters} onFiltersChange={onFiltersChange} />
    </QueryClientProvider>,
  );
  return onFiltersChange;
}

beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("DocumentsView", () => {
  it("shows documents with status, progress and invoice summary", async () => {
    stubFetch(() => ({
      items: [
        doc("a", "PROCESSING"),
        doc("b", "COMPLETED", { invoices: [{ invoice_index: 0, invoice_number: "INV-1", supplier_name: "Acme", invoice_date: null, total: "130.00", currency: "EUR" }] }),
      ],
      next_cursor: null,
    }));
    renderView();

    expect(await screen.findByText("a.pdf")).toBeInTheDocument();
    expect(screen.getByText("Processing", { selector: "span[data-status]" })).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: /Processing/ })).toBeInTheDocument();
    expect(screen.getByText("Acme")).toBeInTheDocument();
    expect(screen.getByText(/INV-1 · 130\.00 EUR/)).toBeInTheDocument();
  });

  it("shows the empty state with a link to upload", async () => {
    stubFetch(() => ({ items: [], next_cursor: null }));
    renderView();

    expect(await screen.findByText("No documents yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Upload your first documents/ })).toHaveAttribute("href", "/upload");
  });

  it("says when filters match nothing", async () => {
    stubFetch(() => ({ items: [], next_cursor: null }));
    renderView({ status: "FAILED" });

    expect(await screen.findByText("No documents match these filters")).toBeInTheDocument();
  });

  it("shows an error with a retry that asks again", async () => {
    let fail = true;
    const fn = vi.fn(async () => (fail ? Response.json({ detail: "x" }, { status: 502 }) : Response.json({ items: [doc("a", "COMPLETED")], next_cursor: null })));
    vi.stubGlobal("fetch", fn);
    renderView();

    expect(await screen.findByRole("alert")).toHaveTextContent(/API could not be reached/);
    fail = false;
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByText("a.pdf")).toBeInTheDocument();
  });

  it("sends the chosen filters to the API", async () => {
    const fn = stubFetch(() => ({ items: [], next_cursor: null }));
    const onChange = renderView({ status: "NEEDS_REVIEW" });

    expect(fn.mock.calls[0][0]).toContain("status=NEEDS_REVIEW");

    await userEvent.type(screen.getByLabelText("Supplier"), "acme");
    await userEvent.click(screen.getByRole("button", { name: "Apply filters" }));

    expect(onChange).toHaveBeenCalledWith({ status: "NEEDS_REVIEW", supplier: "acme" });
  });

  it("loads more with the cursor and never repeats a document", async () => {
    const fn = stubFetch((url) =>
      url.includes("cursor=c1") ? { items: [doc("c", "COMPLETED")], next_cursor: null } : { items: [doc("a", "COMPLETED"), doc("b", "COMPLETED")], next_cursor: "c1" },
    );
    renderView();

    await screen.findByText("a.pdf");
    await userEvent.click(screen.getByRole("button", { name: "Load more" }));

    expect(await screen.findByText("c.pdf")).toBeInTheDocument();
    expect(fn.mock.calls[1][0]).toContain("cursor=c1");
    expect(screen.getAllByRole("link", { name: /\.pdf$/ })).toHaveLength(3);
    expect(screen.queryByRole("button", { name: "Load more" })).toBeNull();
  });
});

describe("polling", () => {
  it("refreshes while a document is in progress and shows the new status", async () => {
    let status: DocumentStatus = "PROCESSING";
    const fn = stubFetch(() => ({ items: [doc("a", status)], next_cursor: null }));
    renderView();
    await screen.findByText("a.pdf");
    expect(screen.getByText("Processing", { selector: "span[data-status]" })).toBeInTheDocument();

    status = "COMPLETED";
    await act(() => vi.advanceTimersByTimeAsync(POLL_MS + 100));

    await waitFor(() => expect(screen.getByText("Completed", { selector: "span[data-status]" })).toBeInTheDocument());
    expect(fn.mock.calls.length).toBeGreaterThan(1);
  });

  it("stops refreshing once every document is final", async () => {
    const fn = stubFetch(() => ({ items: [doc("a", "COMPLETED"), doc("b", "FAILED"), doc("c", "NEEDS_REVIEW")], next_cursor: null }));
    renderView();
    await screen.findByText("a.pdf");
    const calls = fn.mock.calls.length;

    await act(() => vi.advanceTimersByTimeAsync(POLL_MS * 5));

    expect(fn.mock.calls.length).toBe(calls);
  });
});

describe("filter form", () => {
  it("clearing filters applies an empty set", async () => {
    stubFetch(() => ({ items: [], next_cursor: null }));
    const onChange = renderView({ supplier: "acme" });
    await screen.findByText("No documents match these filters");

    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));

    expect(onChange).toHaveBeenCalledWith({});
  });
});
