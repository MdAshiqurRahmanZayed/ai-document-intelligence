import type {
  Correction,
  DocumentDetail,
  DocumentFilters,
  DocumentList,
  DocumentResult,
  FileLink,
  FromStage,
  InvoicePatch,
  InvoiceResult,
  ReprocessResponse,
  RetryFailedResponse,
  SearchMode,
  SearchResponse,
} from "./types";

/** All browser calls go to the web server's own proxy, which adds the API key. */
export const API_BASE = "/api/backend";

/** An API error in one shape: the API answers with a string, a reason, or a field and message. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly reason: string | null = null,
    readonly field: string | null = null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** Builds an ApiError from a response status and its (possibly missing) JSON body. */
export function parseError(status: number, body: unknown): ApiError {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return new ApiError(status, detail);
  if (Array.isArray(detail)) {
    // FastAPI's own validation errors: a list of {loc, msg}.
    const first = detail[0] as { loc?: unknown[]; msg?: string } | undefined;
    const field = first?.loc ? String(first.loc[first.loc.length - 1]) : null;
    return new ApiError(status, first?.msg ?? "Invalid request", null, field);
  }
  if (detail && typeof detail === "object") {
    const d = detail as { reason?: string; field?: string; message?: string };
    return new ApiError(status, d.message ?? d.reason ?? `HTTP ${status}`, d.reason ?? null, d.field ?? null);
  }
  return new ApiError(status, `HTTP ${status}`);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { cache: "no-store", ...init });
  } catch {
    throw new ApiError(0, "Network error");
  }
  const body = await res.json().catch(() => null);
  if (!res.ok) throw parseError(res.status, body);
  return body as T;
}

/** Query string from the non-empty values of an object. */
export function toQuery(params: Record<string, string | number | undefined | null>): string {
  const q = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && String(value).trim() !== "") q.set(key, String(value));
  }
  const text = q.toString();
  return text ? `?${text}` : "";
}

const json = (body: unknown): RequestInit => ({
  headers: { "content-type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  listDocuments: (filters: DocumentFilters, cursor?: string | null, limit = 20) =>
    request<DocumentList>(`/documents${toQuery({ ...filters, cursor, limit })}`),

  getDocument: (id: string) => request<DocumentDetail>(`/documents/${id}`),

  getResult: (id: string) => request<DocumentResult>(`/documents/${id}/result`),

  getFileLink: (id: string) => request<FileLink>(`/documents/${id}/file`),

  getCorrections: (id: string) =>
    request<{ corrections: Correction[] }>(`/documents/${id}/corrections`).then((r) => r.corrections),

  correctInvoice: (id: string, index: number, fields: InvoicePatch, editedBy: string) =>
    request<InvoiceResult>(`/documents/${id}/invoices/${index}`, {
      method: "PATCH",
      ...json({ fields, edited_by: editedBy }),
    }),

  reprocess: (id: string, fromStage: FromStage) =>
    request<ReprocessResponse>(`/documents/${id}/reprocess`, {
      method: "POST",
      ...json({ from_stage: fromStage }),
    }),

  retryFailed: (limit = 100) =>
    request<RetryFailedResponse>(`/jobs/retry-failed${toQuery({ limit })}`, { method: "POST" }),

  search: (query: string, mode: SearchMode, filters: DocumentFilters, limit = 20) =>
    request<SearchResponse>(`/search${toQuery({ ...filters, q: query, mode, limit })}`),
};
