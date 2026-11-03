import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ReviewView } from "./ReviewView";
import { finding, invoice, listItem, renderWithClient, result, stubApi } from "@/test/helpers";

afterEach(() => vi.unstubAllGlobals());

const review = listItem({ id: "r1", filename: "needs.pdf", status: "NEEDS_REVIEW", invoices: [{ invoice_index: 0, invoice_number: "INV-9", supplier_name: "Acme", invoice_date: null, total: "5.00", currency: "EUR" }] });
const failed = listItem({ id: "f1", filename: "broken.pdf", status: "FAILED", error_code: "pdf_corrupt" });

function routes(extra: Record<string, unknown> = {}) {
  return {
    "status=NEEDS_REVIEW": { items: [review], next_cursor: null },
    "status=FAILED": { items: [failed], next_cursor: null },
    "/documents/r1/result": result([invoice({ validation_errors: [finding(), finding({ code: "old_date", field: "invoice_date", severity: "warning" })] })], { status: "NEEDS_REVIEW" }),
    ...extra,
  };
}

describe("ReviewView", () => {
  it("lists the documents to review with their findings, and the failed ones with the reason", async () => {
    stubApi(routes());
    renderWithClient(<ReviewView />);

    const queue = await screen.findByRole("table", { name: "Documents needing review" });
    expect(within(queue).getByRole("link", { name: "needs.pdf" })).toHaveAttribute("href", "/documents/r1");
    expect(within(queue).getByText("Acme")).toBeInTheDocument();
    expect(await within(queue).findByText("1 error")).toBeInTheDocument();
    expect(within(queue).getByText("1 warning")).toBeInTheDocument();

    const list = screen.getByRole("table", { name: "Failed documents" });
    expect(within(list).getByRole("link", { name: "broken.pdf" })).toBeInTheDocument();
    expect(within(list).getByText("The PDF is damaged and cannot be opened.")).toBeInTheDocument();
  });

  it("says nothing needs review when the queue is empty", async () => {
    stubApi(routes({ "status=NEEDS_REVIEW": { items: [], next_cursor: null }, "status=FAILED": { items: [], next_cursor: null } }));
    renderWithClient(<ReviewView />);

    expect(await screen.findByText("Nothing needs review")).toBeInTheDocument();
    expect(screen.getByText("No failed documents")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry all failed" })).toBeNull();
  });

  it("asks before retrying and then reports how many were queued", async () => {
    const { calls } = stubApi(routes({ "/jobs/retry-failed": { queued: ["f1", "f2"], not_queued: 0 } }));
    renderWithClient(<ReviewView />);

    await userEvent.click(await screen.findByRole("button", { name: "Retry all failed" }));
    expect(calls.some((c) => c.method === "POST")).toBe(false);
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Retry all" }));

    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.url.includes("/jobs/retry-failed"))).toBe(true));
    expect((await screen.findAllByText(/2 queued/)).length).toBeGreaterThan(0);
  });

  it("reports documents that could not be queued", async () => {
    stubApi(routes({ "/jobs/retry-failed": { queued: ["f1"], not_queued: 2 } }));
    renderWithClient(<ReviewView />);

    await userEvent.click(await screen.findByRole("button", { name: "Retry all failed" }));
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Retry all" }));

    expect((await screen.findAllByText(/1 queued, 2 (not queued|could not be queued)/)).length).toBeGreaterThan(0);
  });
});
