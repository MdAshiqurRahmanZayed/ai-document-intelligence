import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { vi } from "vitest";

import { ToastProvider } from "@/components/ui/Toast";
import type {
  DocumentDetail,
  DocumentListItem,
  DocumentResult,
  Finding,
  InvoiceResult,
  ProcessingEvent,
} from "@/lib/types";

export function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return { client, ...render(<QueryClientProvider client={client}><ToastProvider>{ui}</ToastProvider></QueryClientProvider>) };
}

export const event = (
  stage: ProcessingEvent["stage"],
  status: ProcessingEvent["status"],
  extra: Partial<ProcessingEvent> = {},
): ProcessingEvent => ({
  stage,
  status,
  attempt: 1,
  duration_ms: null,
  error_code: null,
  error_message: null,
  created_at: "2026-11-03T10:00:00Z",
  ...extra,
});

export const detail = (extra: Partial<DocumentDetail> = {}): DocumentDetail => ({
  id: "3f2a1b4c-5d6e-4f70-8a9b-0c1d2e3f4a5b",
  filename: "invoice.pdf",
  mime: "application/pdf",
  size: 48213,
  status: "NEEDS_REVIEW",
  source_type: "pdf",
  page_count: 2,
  error_code: null,
  error_message: null,
  created_at: "2026-11-03T10:00:00Z",
  updated_at: "2026-11-03T10:00:02Z",
  events: [event("ingest", "succeeded", { duration_ms: 12 }), event("extract", "succeeded", { duration_ms: 2000 })],
  ...extra,
});

export const finding = (extra: Partial<Finding> = {}): Finding => ({
  code: "total_mismatch",
  field: "total",
  severity: "error",
  message: "subtotal 100.00 plus tax 20.00 is 120.00, not 130.00",
  related_document_id: null,
  ...extra,
});

export const invoice = (extra: Partial<InvoiceResult> = {}): InvoiceResult => ({
  extraction_id: "9c1b",
  invoice_index: 0,
  version: 1,
  data: {
    invoice_number: "INV-1042",
    invoice_date: "2026-01-05",
    supplier_name: "Acme Ltd",
    customer_name: "Globex",
    subtotal: "100.00",
    tax: "20.00",
    total: "130.00",
    currency: "EUR",
    line_items: [{ description: "Widget", quantity: "2", unit_price: "50.00", amount: "100.00" }],
  },
  field_confidence: { invoice_number: 0.95, total: 0.9 },
  grounding: { invoice_number: "Invoice No: INV-1042" },
  model: "gemini-2.5-flash",
  prompt_version: "v1",
  validation_errors: [finding()],
  ...extra,
});

export const result = (invoices: InvoiceResult[] = [invoice()], extra: Partial<DocumentResult> = {}): DocumentResult => ({
  document_id: detail().id,
  status: "NEEDS_REVIEW",
  invoices,
  document_errors: [],
  ...extra,
});

export const listItem = (extra: Partial<DocumentListItem> = {}): DocumentListItem => ({
  id: "d1",
  filename: "a.pdf",
  status: "COMPLETED",
  source_type: "pdf",
  page_count: 1,
  error_code: null,
  created_at: "2026-11-03T10:00:00Z",
  updated_at: "2026-11-03T10:00:00Z",
  invoices: [],
  ...extra,
});

/** Routes fetch calls by URL fragment to a status and JSON body; anything else is a 404. */
export function stubApi(routes: Record<string, unknown | { status: number; body: unknown }>) {
  const calls: { url: string; method: string; body: unknown }[] = [];
  const fn = vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, method: init?.method ?? "GET", body: init?.body ? JSON.parse(String(init.body)) : undefined });
    const key = Object.keys(routes)
      .sort((a, b) => b.length - a.length)
      .find((k) => url.includes(k));
    if (!key) return Response.json({ detail: "Not found" }, { status: 404 });
    const hit = routes[key] as { status?: number; body?: unknown } | undefined;
    if (hit && typeof hit === "object" && "status" in hit && "body" in hit) return Response.json(hit.body, { status: hit.status });
    return Response.json(hit);
  });
  vi.stubGlobal("fetch", fn);
  return { fn, calls };
}
