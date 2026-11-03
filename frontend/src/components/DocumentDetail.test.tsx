import { screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DocumentDetail } from "./DocumentDetail";
import { detail, event, invoice, renderWithClient, result, stubApi } from "@/test/helpers";

vi.mock("next/dynamic", () => ({ default: () => () => <div data-testid="pdf-viewer" /> }));

afterEach(() => vi.unstubAllGlobals());

const ID = detail().id;

describe("DocumentDetail", () => {
  it("shows the document, its steps and the extracted invoice beside the viewer", async () => {
    stubApi({ [`/documents/${ID}/result`]: result(), [`/documents/${ID}/corrections`]: { corrections: [] }, [`/documents/${ID}`]: detail() });
    renderWithClient(<DocumentDetail id={ID} />);

    expect(await screen.findByRole("heading", { name: /invoice\.pdf/ })).toBeInTheDocument();
    expect(screen.getByTestId("pdf-viewer")).toBeInTheDocument();
    expect(await screen.findByRole("form", { name: "Invoice 1" })).toBeInTheDocument();
    const steps = within(screen.getByRole("list", { name: "Processing steps" }));
    expect(steps.getByText(/Reading the file/)).toBeInTheDocument();
    expect(steps.getByText("12 ms")).toBeInTheDocument();
  });

  it("marks a failed step with its error and shows the failure with a way to retry", async () => {
    stubApi({
      [`/documents/${ID}/result`]: result([]),
      [`/documents/${ID}/corrections`]: { corrections: [] },
      [`/documents/${ID}`]: detail({
        status: "FAILED",
        error_code: "ocr_failed",
        error_message: "TesseractError",
        events: [event("ingest", "succeeded"), event("ocr", "started"), event("ocr", "failed", { error_message: "TesseractError" })],
      }),
    });
    renderWithClient(<DocumentDetail id={ID} />);

    const alert = await screen.findByText("Text recognition failed after several attempts.");
    expect(alert).toBeInTheDocument();
    const failed = document.querySelector('[data-state="failed"]')!;
    expect(failed).toHaveTextContent("Text recognition");
    expect(failed).toHaveTextContent("TesseractError");
    expect(screen.getByRole("button", { name: "Reprocess" })).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).toBeNull();
  });

  it("shows a progress bar while processing and offers no reprocess", async () => {
    stubApi({
      [`/documents/${ID}/result`]: result([]),
      [`/documents/${ID}/corrections`]: { corrections: [] },
      [`/documents/${ID}`]: detail({ status: "PROCESSING", source_type: "pdf", events: [event("ingest", "succeeded"), event("ocr", "started")] }),
    });
    renderWithClient(<DocumentDetail id={ID} />);

    const bar = await screen.findByRole("progressbar", { name: /Recognising text/ });
    expect(bar).toHaveAttribute("aria-valuenow", "40");
    expect(screen.queryByRole("button", { name: "Reprocess" })).toBeNull();
    expect(await screen.findByText("Waiting for the extracted invoice")).toBeInTheDocument();
  });

  it("says when nothing was extracted and does not show an empty form", async () => {
    stubApi({ [`/documents/${ID}/result`]: result([]), [`/documents/${ID}/corrections`]: { corrections: [] }, [`/documents/${ID}`]: detail({ status: "COMPLETED" }) });
    renderWithClient(<DocumentDetail id={ID} />);

    expect(await screen.findByText("No invoice was extracted")).toBeInTheDocument();
    expect(screen.queryByRole("form")).toBeNull();
  });

  it("shows several invoices, in order, each with its own findings", async () => {
    const second = invoice({ invoice_index: 1, validation_errors: [], data: { ...invoice().data, invoice_number: "INV-2" } });
    stubApi({ [`/documents/${ID}/result`]: result([invoice(), second]), [`/documents/${ID}/corrections`]: { corrections: [] }, [`/documents/${ID}`]: detail() });
    renderWithClient(<DocumentDetail id={ID} />);

    const forms = await screen.findAllByRole("form");
    expect(forms.map((f) => f.getAttribute("aria-label"))).toEqual(["Invoice 1", "Invoice 2"]);
    expect(within(forms[0]).getByLabelText("Invoice number")).toHaveValue("INV-1042");
    expect(within(forms[1]).getByLabelText("Invoice number")).toHaveValue("INV-2");
    expect(screen.getAllByRole("list", { name: "Validation findings" })).toHaveLength(1);
  });

  it("shows 'document not found' with a link to the list", async () => {
    stubApi({});
    renderWithClient(<DocumentDetail id={ID} />);

    expect(await screen.findByText("Document not found")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Back to the documents/ })).toHaveAttribute("href", "/documents");
  });

  it("shows the correction history when there is one", async () => {
    stubApi({
      [`/documents/${ID}/result`]: result(),
      [`/documents/${ID}/corrections`]: { corrections: [{ invoice_index: 0, field: "total", old_value: "130.00", new_value: "120.00", edited_by: "Maria", created_at: "2026-11-03T11:00:00Z" }] },
      [`/documents/${ID}`]: detail(),
    });
    renderWithClient(<DocumentDetail id={ID} />);

    const table = await screen.findByRole("table", { name: "Correction history" });
    expect(within(table).getByText("Maria")).toBeInTheDocument();
    expect(within(table).getByText("130.00")).toBeInTheDocument();
    expect(within(table).getByText("120.00")).toBeInTheDocument();
  });
});
