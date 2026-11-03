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

  describe("retrying selected failed documents", () => {
    const failedList = [
      listItem({ id: "f1", filename: "broken.pdf", status: "FAILED", error_code: "pdf_corrupt" }),
      listItem({ id: "f2", filename: "no-model.pdf", status: "FAILED", error_code: "extraction_failed" }),
      listItem({ id: "f3", filename: "other.pdf", status: "FAILED", error_code: "ocr_failed" }),
    ];
    const withThree = () =>
      routes({
        "status=FAILED": { items: failedList, next_cursor: null },
        "/documents/f1/reprocess": { document_id: "f1", status: "QUEUED", from_stage: "ingest" },
        "/documents/f2/reprocess": { document_id: "f2", status: "QUEUED", from_stage: "extract" },
      });

    it("keeps Retry selected disabled until a row is ticked", async () => {
      stubApi(withThree());
      renderWithClient(<ReviewView />);

      const button = await screen.findByRole("button", { name: "Retry selected" });
      expect(button).toBeDisabled();
      await userEvent.click(screen.getByRole("checkbox", { name: "Select broken.pdf" }));
      expect(screen.getByRole("button", { name: "Retry selected (1)" })).toBeEnabled();
    });

    it("retries only the ticked documents, each from the step that failed", async () => {
      const { calls } = stubApi(withThree());
      renderWithClient(<ReviewView />);

      await userEvent.click(await screen.findByRole("checkbox", { name: "Select broken.pdf" }));
      await userEvent.click(screen.getByRole("checkbox", { name: "Select no-model.pdf" }));
      await userEvent.click(screen.getByRole("button", { name: "Retry selected (2)" }));

      await waitFor(() => expect(calls.filter((c) => c.method === "POST")).toHaveLength(2));
      const posts = calls.filter((c) => c.method === "POST");
      expect(posts.find((c) => c.url.includes("/documents/f1/reprocess"))?.body).toEqual({ from_stage: "ingest" });
      expect(posts.find((c) => c.url.includes("/documents/f2/reprocess"))?.body).toEqual({ from_stage: "extract" });
      expect(posts.some((c) => c.url.includes("/documents/f3/reprocess"))).toBe(false);
      expect((await screen.findAllByText(/2 queued/)).length).toBeGreaterThan(0);
    });

    it("selects and clears every row with the header box", async () => {
      stubApi(withThree());
      renderWithClient(<ReviewView />);

      await userEvent.click(await screen.findByRole("checkbox", { name: "Select all failed documents" }));
      expect(screen.getByRole("button", { name: "Retry selected (3)" })).toBeEnabled();
      await userEvent.click(screen.getByRole("checkbox", { name: "Select all failed documents" }));
      expect(screen.getByRole("button", { name: "Retry selected" })).toBeDisabled();
    });

    it("reports the ones the server refused", async () => {
      stubApi(
        routes({
          "status=FAILED": { items: failedList, next_cursor: null },
          "/documents/f1/reprocess": { document_id: "f1", status: "QUEUED", from_stage: "ingest" },
          "/documents/f3/reprocess": { status: 409, body: { detail: { reason: "already_queued" } } },
        }),
      );
      renderWithClient(<ReviewView />);

      await userEvent.click(await screen.findByRole("checkbox", { name: "Select broken.pdf" }));
      await userEvent.click(screen.getByRole("checkbox", { name: "Select other.pdf" }));
      await userEvent.click(screen.getByRole("button", { name: "Retry selected (2)" }));

      expect((await screen.findAllByText(/1 queued, 1 could not be queued/)).length).toBeGreaterThan(0);
    });
  });

  it("reports documents that could not be queued", async () => {
    stubApi(routes({ "/jobs/retry-failed": { queued: ["f1"], not_queued: 2 } }));
    renderWithClient(<ReviewView />);

    await userEvent.click(await screen.findByRole("button", { name: "Retry all failed" }));
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Retry all" }));

    expect((await screen.findAllByText(/1 queued, 2 (not queued|could not be queued)/)).length).toBeGreaterThan(0);
  });
});
