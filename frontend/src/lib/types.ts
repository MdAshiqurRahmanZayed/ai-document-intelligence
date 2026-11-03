// Shapes of the API's JSON, written from docs/api.md. Money stays a decimal string, never a number.

export type DocumentStatus =
  | "UPLOADED"
  | "QUEUED"
  | "PROCESSING"
  | "COMPLETED"
  | "NEEDS_REVIEW"
  | "FAILED";

export const DOCUMENT_STATUSES: DocumentStatus[] = [
  "UPLOADED",
  "QUEUED",
  "PROCESSING",
  "COMPLETED",
  "NEEDS_REVIEW",
  "FAILED",
];

export type SourceType = "pdf" | "image" | "spreadsheet" | string;

export interface InvoiceSummary {
  invoice_index: number;
  invoice_number: string | null;
  supplier_name: string | null;
  invoice_date: string | null;
  total: string | null;
  currency: string | null;
}

export interface DocumentListItem {
  id: string;
  filename: string;
  status: DocumentStatus;
  source_type: SourceType | null;
  page_count: number | null;
  error_code: string | null;
  created_at: string;
  updated_at: string;
  invoices: InvoiceSummary[];
}

export interface DocumentList {
  items: DocumentListItem[];
  next_cursor: string | null;
}

export type Stage = "ingest" | "ocr" | "extract" | "embed";
export type EventStatus = "started" | "succeeded" | "failed";

export interface ProcessingEvent {
  stage: Stage;
  status: EventStatus;
  attempt: number;
  duration_ms: number | null;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
}

export interface DocumentDetail extends Omit<DocumentListItem, "invoices"> {
  mime: string;
  size: number;
  error_message: string | null;
  events: ProcessingEvent[];
}

export interface LineItem {
  description: string | null;
  quantity: string | null;
  unit_price: string | null;
  amount: string | null;
}

export interface InvoiceData {
  invoice_number: string | null;
  invoice_date: string | null;
  supplier_name: string | null;
  customer_name: string | null;
  subtotal: string | null;
  tax: string | null;
  total: string | null;
  currency: string | null;
  line_items: LineItem[];
}

export type Severity = "error" | "warning";

export interface Finding {
  code: string;
  field: string | null;
  severity: Severity;
  message: string;
  related_document_id: string | null;
}

export interface InvoiceResult {
  extraction_id: string;
  invoice_index: number;
  version: number;
  data: InvoiceData;
  field_confidence: Record<string, number>;
  grounding: Record<string, string>;
  model: string;
  prompt_version: string;
  validation_errors: Finding[];
}

export interface DocumentResult {
  document_id: string;
  status: DocumentStatus;
  invoices: InvoiceResult[];
  document_errors: Finding[];
}

export interface Correction {
  invoice_index: number;
  field: string;
  old_value: string | null;
  new_value: string | null;
  edited_by: string;
  created_at: string;
}

export type FromStage = "ingest" | "extract";

export interface ReprocessResponse {
  document_id: string;
  status: DocumentStatus;
  from_stage: FromStage;
}

export interface RetryFailedResponse {
  queued: string[];
  not_queued: number;
}

export type UploadStatus = "accepted" | "duplicate" | "rejected";

export interface UploadResult {
  filename: string;
  status: UploadStatus;
  document_id: string | null;
  reason: string | null;
}

export type SearchMode = "keyword" | "semantic" | "hybrid";

export interface SearchHit {
  document_id: string;
  filename: string;
  status: DocumentStatus;
  page_no: number | null;
  score: number;
  snippet: string;
  invoices: InvoiceSummary[];
}

export interface SearchResponse {
  mode_used: SearchMode;
  results: SearchHit[];
}

export interface FileLink {
  url: string;
  expires_in: number;
}

/** Invoice filters shared by the list and the search. All optional, combined with AND. */
export interface DocumentFilters {
  status?: DocumentStatus | "";
  supplier?: string;
  invoice_number?: string;
  date_from?: string;
  date_to?: string;
  amount_min?: string;
  amount_max?: string;
  currency?: string;
}

/** Editable invoice fields, as the PATCH body's `fields`. `null` clears a value. */
export type InvoicePatch = Partial<Omit<InvoiceData, "line_items">> & {
  line_items?: LineItem[];
};
