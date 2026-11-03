import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { InvoiceCard } from "./InvoiceCard";
import { finding, invoice, renderWithClient, stubApi } from "@/test/helpers";

const ID = "3f2a1b4c-5d6e-4f70-8a9b-0c1d2e3f4a5b";

beforeEach(() => localStorage.clear());
afterEach(() => vi.unstubAllGlobals());

function renderCard(inv = invoice(), busy = false) {
  return renderWithClient(<InvoiceCard documentId={ID} invoice={inv} busy={busy} />);
}

describe("findings", () => {
  it("marks the input of an error finding and lists the finding with its severity in words", () => {
    renderCard();

    const total = screen.getByLabelText("Total");
    expect(total).toHaveAttribute("aria-invalid", "true");
    const list = within(screen.getByRole("list", { name: "Validation findings" }));
    expect(list.getByText("Error")).toBeInTheDocument();
    expect(list.getByText("Total does not match")).toBeInTheDocument();
    expect(list.getByText(/subtotal 100.00 plus tax 20.00/)).toBeInTheDocument();
  });

  it("shows a warning in words and does not mark the input as invalid", () => {
    renderCard(invoice({ validation_errors: [finding({ code: "implausible_tax_rate", field: "tax", severity: "warning", message: "tax is 40% of the subtotal" })] }));

    expect(screen.getByText("Warning")).toBeInTheDocument();
    expect(screen.getByLabelText("Tax")).not.toHaveAttribute("aria-invalid");
  });

  it("links a duplicate finding to the related document", () => {
    renderCard(invoice({ validation_errors: [finding({ code: "duplicate_invoice", field: "invoice_number", message: "same number", related_document_id: "abc" })] }));

    expect(screen.getByRole("link", { name: "Open the related document" })).toHaveAttribute("href", "/documents/abc");
  });

  it("shows the model's confidence and source quote under a field", () => {
    renderCard(invoice({ validation_errors: [] }));

    expect(screen.getByText(/Confidence 95% · “Invoice No: INV-1042”/)).toBeInTheDocument();
  });
});

describe("saving a correction", () => {
  it("disables save until something changes", async () => {
    renderCard();
    const save = screen.getByRole("button", { name: "Save correction" });
    expect(save).toBeDisabled();

    await userEvent.type(screen.getByLabelText("Customer"), "!");
    expect(save).toBeEnabled();
  });

  it("sends only the changed field with the editor's name and shows success", async () => {
    const saved = invoice({ version: 2, validation_errors: [], data: { ...invoice().data, total: "120.00" } });
    const { calls } = stubApi({ "/invoices/0": saved });
    renderCard();

    const total = screen.getByLabelText("Total");
    await userEvent.clear(total);
    await userEvent.type(total, "120.00");
    await userEvent.clear(screen.getByLabelText("Edited by"));
    await userEvent.type(screen.getByLabelText("Edited by"), "Maria");
    await userEvent.click(screen.getByRole("button", { name: "Save correction" }));

    await waitFor(() => expect(calls.some((c) => c.method === "PATCH")).toBe(true));
    const patch = calls.find((c) => c.method === "PATCH")!;
    expect(patch.url).toBe(`/api/backend/documents/${ID}/invoices/0`);
    expect(patch.body).toEqual({ fields: { total: "120.00" }, edited_by: "Maria" });
    expect(await screen.findByText(/Correction saved/)).toBeInTheDocument();
    expect(localStorage.getItem("invoice-editor-name")).toBe("Maria");
    // The form starts again from the saved values, so it is clean and save is off.
    await waitFor(() => expect(screen.getByRole("button", { name: "Save correction" })).toBeDisabled());
  });

  it("sends nothing and shows an error at the field for text that is not a number", async () => {
    const { calls } = stubApi({});
    renderCard();

    const total = screen.getByLabelText("Total");
    await userEvent.clear(total);
    await userEvent.type(total, "abc");
    await userEvent.click(screen.getByRole("button", { name: "Save correction" }));

    expect(await screen.findByText("Enter a number, like 1234.50")).toBeInTheDocument();
    expect(calls.filter((c) => c.method === "PATCH")).toHaveLength(0);
  });

  it("shows the API's message at the named field and keeps what was typed", async () => {
    stubApi({ "/invoices/0": { status: 422, body: { detail: { field: "invoice_date", message: "Cannot read this as a date" } } } });
    renderCard();

    const customer = screen.getByLabelText("Customer");
    await userEvent.clear(customer);
    await userEvent.type(customer, "Initech");
    await userEvent.click(screen.getByRole("button", { name: "Save correction" }));

    expect(await screen.findByText("Cannot read this as a date")).toBeInTheDocument();
    expect(screen.getByLabelText("Invoice date")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("Customer")).toHaveValue("Initech");
  });

  it("tells the person the document is busy and keeps their edits", async () => {
    stubApi({ "/invoices/0": { status: 409, body: { detail: { reason: "document_busy" } } } });
    renderCard();

    const customer = screen.getByLabelText("Customer");
    await userEvent.clear(customer);
    await userEvent.type(customer, "Initech");
    await userEvent.click(screen.getByRole("button", { name: "Save correction" }));

    // The total finding is an alert too, so match on the message.
    expect(await screen.findByText(/still being processed/)).toBeInTheDocument();
    expect(screen.getByLabelText("Customer")).toHaveValue("Initech");
  });

  it("clears a value with null when its box is emptied", async () => {
    const { calls } = stubApi({ "/invoices/0": invoice({ validation_errors: [] }) });
    renderCard();

    await userEvent.clear(screen.getByLabelText("Tax"));
    await userEvent.click(screen.getByRole("button", { name: "Save correction" }));

    await waitFor(() => expect(calls.some((c) => c.method === "PATCH")).toBe(true));
    expect(calls.find((c) => c.method === "PATCH")!.body).toMatchObject({ fields: { tax: null } });
  });

  it("can add and remove line items, sending the whole list", async () => {
    const { calls } = stubApi({ "/invoices/0": invoice({ validation_errors: [] }) });
    renderCard();

    await userEvent.click(screen.getByRole("button", { name: "Add line" }));
    const descriptions = screen.getAllByLabelText("Description");
    await userEvent.type(descriptions[1], "Gadget");
    await userEvent.click(screen.getByRole("button", { name: "Save correction" }));

    await waitFor(() => expect(calls.some((c) => c.method === "PATCH")).toBe(true));
    const body = calls.find((c) => c.method === "PATCH")!.body as { fields: { line_items: unknown[] } };
    expect(body.fields.line_items).toHaveLength(2);
  });

  it("cannot be edited while the document is being processed", () => {
    renderCard(invoice(), true);

    expect(screen.getByLabelText("Total")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save correction" })).toBeDisabled();
    expect(screen.getByText(/being processed/)).toBeInTheDocument();
  });
});
