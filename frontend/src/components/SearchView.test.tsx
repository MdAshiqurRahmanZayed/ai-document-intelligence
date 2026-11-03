import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SearchView, type SearchState } from "./SearchView";
import { renderWithClient, stubApi } from "@/test/helpers";
import type { SearchHit } from "@/lib/types";

afterEach(() => vi.unstubAllGlobals());

const hit = (extra: Partial<SearchHit> = {}): SearchHit => ({
  document_id: "d1",
  filename: "terms.pdf",
  status: "COMPLETED",
  page_no: 2,
  score: 0.03,
  snippet: "… <mark>Payment</mark> is due within thirty days …",
  invoices: [{ invoice_index: 0, invoice_number: "INV-1", supplier_name: "Acme", invoice_date: null, total: "120.00", currency: "EUR" }],
  ...extra,
});

const state = (extra: Partial<SearchState> = {}): SearchState => ({ q: "payment terms", mode: "hybrid", filters: {}, ...extra });

function renderSearch(s = state(), onChange = vi.fn()) {
  renderWithClient(<SearchView state={s} onChange={onChange} />);
  return onChange;
}

describe("SearchView", () => {
  it("shows results with filename, status, page, highlighted snippet and invoice", async () => {
    stubApi({ "/search": { mode_used: "hybrid", results: [hit()] } });
    renderSearch();

    const list = await screen.findByRole("list", { name: "Search results" });
    expect(within(list).getByRole("link", { name: "terms.pdf" })).toHaveAttribute("href", "/documents/d1");
    expect(within(list).getByText("Completed")).toBeInTheDocument();
    expect(within(list).getByText("page 2")).toBeInTheDocument();
    expect(within(list).getByText("Payment").tagName).toBe("MARK");
    expect(within(list).getByText("Acme")).toBeInTheDocument();
  });

  it("makes no request for a blank query and invites a search", () => {
    const { fn } = stubApi({});
    renderSearch(state({ q: "   " }));

    expect(screen.getByText("Search your documents")).toBeInTheDocument();
    expect(fn).not.toHaveBeenCalled();
  });

  it("sends the query, mode and filters together", async () => {
    const { calls } = stubApi({ "/search": { mode_used: "keyword", results: [] } });
    renderSearch(state({ q: "freight", mode: "keyword", filters: { status: "COMPLETED" } }));

    await screen.findByText("Nothing matched");
    expect(calls[0].url).toContain("q=freight");
    expect(calls[0].url).toContain("mode=keyword");
    expect(calls[0].url).toContain("status=COMPLETED");
  });

  it("says nothing matched and suggests another mode", async () => {
    stubApi({ "/search": { mode_used: "hybrid", results: [] } });
    renderSearch();

    expect(await screen.findByText("Nothing matched")).toBeInTheDocument();
    expect(screen.getByText(/another search mode/)).toBeInTheDocument();
  });

  it("explains an unavailable semantic search and offers keyword search", async () => {
    stubApi({ "/search": { status: 409, body: { detail: { reason: "semantic_unavailable" } } } });
    const onChange = renderSearch(state({ mode: "semantic" }));

    expect(await screen.findByText("Semantic search is not available")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Search by keyword instead" }));
    expect(onChange).toHaveBeenCalledWith({ mode: "keyword" });
  });

  it("says which mode was used when hybrid fell back to keyword", async () => {
    stubApi({ "/search": { mode_used: "keyword", results: [hit()] } });
    renderSearch();

    // The loading spinner is also a status, so wait for the notice by its text.
    expect(await screen.findByText(/Showing keyword results/)).toBeInTheDocument();
  });

  it("changes the query on submit and the mode on choosing one", async () => {
    stubApi({ "/search": { mode_used: "hybrid", results: [] } });
    const onChange = renderSearch(state({ q: "" }));

    await userEvent.type(screen.getByLabelText("Search the text of your documents"), "  late fee ");
    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(onChange).toHaveBeenCalledWith({ q: "late fee" });

    await userEvent.click(screen.getByRole("radio", { name: "Semantic" }));
    expect(onChange).toHaveBeenCalledWith({ mode: "semantic" });
  });

  it("shows an error with a retry", async () => {
    stubApi({ "/search": { status: 502, body: { detail: "x" } } });
    renderSearch();

    // A server error is retried once (after a second) before it is shown.
    expect(await screen.findByRole("alert", {}, { timeout: 4000 })).toHaveTextContent(/API could not be reached/);
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});
