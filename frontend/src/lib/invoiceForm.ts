import { z } from "zod";

import type { InvoiceData, InvoicePatch, LineItem } from "./types";

// The browser only checks shape (is it a date, is it a number). The API reads the values and stays the authority.
const AMOUNT = /^-?\s*\d[\d.,\s]*$/;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

const amount = z.string().refine((v) => v.trim() === "" || AMOUNT.test(v.trim()), "Enter a number, like 1234.50");

export const invoiceFormSchema = z.object({
  invoice_number: z.string(),
  invoice_date: z
    .string()
    .refine((v) => v === "" || (ISO_DATE.test(v) && !Number.isNaN(Date.parse(v))), "Enter a valid date"),
  supplier_name: z.string(),
  customer_name: z.string(),
  subtotal: amount,
  tax: amount,
  total: amount,
  currency: z.string().refine((v) => v.trim() === "" || /^[A-Za-z]{3}$/.test(v.trim()), "Use a 3-letter code, like EUR"),
  line_items: z.array(
    z.object({ description: z.string(), quantity: amount, unit_price: amount, amount }),
  ),
});

export type InvoiceForm = z.infer<typeof invoiceFormSchema>;

export const SCALAR_FIELDS = [
  "invoice_number",
  "invoice_date",
  "supplier_name",
  "customer_name",
  "subtotal",
  "tax",
  "total",
  "currency",
] as const satisfies readonly (keyof InvoiceForm)[];

export type ScalarField = (typeof SCALAR_FIELDS)[number];

/** Form values from an invoice: a missing value is an empty box. */
export function toFormValues(data: InvoiceData): InvoiceForm {
  const text = (v: string | null) => v ?? "";
  return {
    invoice_number: text(data.invoice_number),
    invoice_date: text(data.invoice_date),
    supplier_name: text(data.supplier_name),
    customer_name: text(data.customer_name),
    subtotal: text(data.subtotal),
    tax: text(data.tax),
    total: text(data.total),
    currency: text(data.currency),
    line_items: data.line_items.map((l) => ({
      description: text(l.description),
      quantity: text(l.quantity),
      unit_price: text(l.unit_price),
      amount: text(l.amount),
    })),
  };
}

const clean = (v: string): string | null => (v.trim() === "" ? null : v.trim());

function lineItems(items: InvoiceForm["line_items"]): LineItem[] {
  return items.map((l) => ({
    description: clean(l.description),
    quantity: clean(l.quantity),
    unit_price: clean(l.unit_price),
    amount: clean(l.amount),
  }));
}

/**
 * Only what the person changed, ready for the PATCH body: an emptied box becomes `null` (clears the value),
 * a changed line-item list is sent whole (the API replaces it). Nothing changed gives an empty patch.
 */
export function toPatch(initial: InvoiceForm, current: InvoiceForm): InvoicePatch {
  const patch: InvoicePatch = {};
  for (const field of SCALAR_FIELDS) {
    if (clean(initial[field]) === clean(current[field])) continue;
    const value = clean(current[field]);
    patch[field] = field === "currency" && value ? value.toUpperCase() : value;
  }
  const before = JSON.stringify(lineItems(initial.line_items));
  const after = lineItems(current.line_items);
  if (before !== JSON.stringify(after)) patch.line_items = after;
  return patch;
}
