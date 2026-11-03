import { describe, expect, it } from "vitest";

import { invoiceFormSchema, toFormValues, toPatch } from "./invoiceForm";
import type { InvoiceData } from "./types";

const data: InvoiceData = {
  invoice_number: "INV-1042",
  invoice_date: "2026-01-05",
  supplier_name: "Acme Ltd",
  customer_name: null,
  subtotal: "100.00",
  tax: "20.00",
  total: "130.00",
  currency: "EUR",
  line_items: [{ description: "Widget", quantity: "2", unit_price: "50.00", amount: "100.00" }],
};

describe("toFormValues", () => {
  it("turns missing values into empty boxes", () => {
    const form = toFormValues(data);
    expect(form.customer_name).toBe("");
    expect(form.line_items[0].unit_price).toBe("50.00");
  });
});

describe("toPatch", () => {
  it("is empty when nothing changed", () => {
    const form = toFormValues(data);
    expect(toPatch(form, structuredClone(form))).toEqual({});
  });

  it("sends only the changed field", () => {
    const form = toFormValues(data);
    expect(toPatch(form, { ...form, total: "120.00" })).toEqual({ total: "120.00" });
  });

  it("emptying a box clears the value with null", () => {
    const form = toFormValues(data);
    expect(toPatch(form, { ...form, tax: "" })).toEqual({ tax: null });
  });

  it("ignores whitespace-only differences", () => {
    const form = toFormValues(data);
    expect(toPatch(form, { ...form, supplier_name: "  Acme Ltd " })).toEqual({});
  });

  it("upper-cases a currency", () => {
    const form = toFormValues(data);
    expect(toPatch(form, { ...form, currency: "usd" })).toEqual({ currency: "USD" });
  });

  it("sends the whole line-item list when any line changed", () => {
    const form = toFormValues(data);
    const current = { ...form, line_items: [...form.line_items, { description: "Gadget", quantity: "", unit_price: "", amount: "5" }] };

    expect(toPatch(form, current)).toEqual({
      line_items: [
        { description: "Widget", quantity: "2", unit_price: "50.00", amount: "100.00" },
        { description: "Gadget", quantity: null, unit_price: null, amount: "5" },
      ],
    });
  });
});

describe("invoiceFormSchema", () => {
  const ok = toFormValues(data);

  it("accepts the extracted values", () => {
    expect(invoiceFormSchema.safeParse(ok).success).toBe(true);
  });

  it.each(["1234.50", "1.234,50", "-5", ""])("accepts the amount %j", (total) => {
    expect(invoiceFormSchema.safeParse({ ...ok, total }).success).toBe(true);
  });

  it.each(["abc", "12abc", "€"])("rejects the amount %j", (total) => {
    const result = invoiceFormSchema.safeParse({ ...ok, total });
    expect(result.success).toBe(false);
    expect(result.error?.issues[0].path).toEqual(["total"]);
  });

  it("rejects a date that is not a date and a currency that is not a code", () => {
    expect(invoiceFormSchema.safeParse({ ...ok, invoice_date: "2026-13-45" }).success).toBe(false);
    expect(invoiceFormSchema.safeParse({ ...ok, currency: "EURO" }).success).toBe(false);
  });

  it("checks line-item amounts too", () => {
    const result = invoiceFormSchema.safeParse({ ...ok, line_items: [{ description: "x", quantity: "two", unit_price: "", amount: "" }] });
    expect(result.error?.issues[0].path).toEqual(["line_items", 0, "quantity"]);
  });
});
