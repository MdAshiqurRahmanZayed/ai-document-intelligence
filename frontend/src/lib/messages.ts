// Plain sentences for the API's codes, so a person never sees a raw reason or stack trace.
// The keys mirror the reference tables in docs/api.md; messages.test.ts checks they stay complete.
import { ApiError } from "./api";

/** Why the API turned a request down (`reason` of 409/503 bodies and `reason` of rejected uploads). */
export const REASONS: Record<string, string> = {
  document_busy: "This document is still being processed. Try again in a moment.",
  already_queued: "This document is already queued or being processed.",
  extraction_disabled: "Extraction is switched off because no Google API key is configured.",
  no_text: "This document has no readable text to extract from.",
  queue_unavailable: "The job queue is not available right now. Try again shortly.",
  semantic_unavailable: "Semantic search needs a configured Google API key.",
  chat_unavailable: "Chat needs a configured Google API key.",
  not_extracted: "That document has not been extracted yet.",
  empty_file: "The file is empty.",
  file_too_large: "The file is larger than the upload limit.",
  unsupported_type: "This file type is not supported.",
  storage_error: "The file could not be stored. Try again.",
};

/** Why a document failed (`error_code`). */
export const ERROR_CODES: Record<string, string> = {
  queue_unavailable: "The job could not be queued.",
  pdf_corrupt: "The PDF is damaged and cannot be opened.",
  pdf_encrypted: "The PDF is password protected.",
  pdf_empty: "The PDF has no pages.",
  image_corrupt: "The image is damaged or cannot be decoded.",
  spreadsheet_corrupt: "The spreadsheet is damaged and cannot be read.",
  spreadsheet_empty: "The spreadsheet has no data.",
  ingest_failed: "Reading the file failed after several attempts.",
  ocr_failed: "Text recognition failed after several attempts.",
  extraction_failed: "Extracting the invoice failed after several attempts.",
};

/** Titles of the validation findings. */
export const FINDING_TITLES: Record<string, string> = {
  missing_field: "Missing field",
  negative_amount: "Negative amount",
  implausible_amount: "Implausible amount",
  line_items_sum_mismatch: "Line items do not add up",
  total_mismatch: "Total does not match",
  future_date: "Date is in the future",
  invalid_currency: "Invalid currency",
  duplicate_invoice: "Duplicate invoice",
  no_invoice_found: "No invoice found",
  line_amount_mismatch: "Line amount mismatch",
  implausible_tax_rate: "Unusual tax rate",
  old_date: "Very old date",
  missing_currency: "Missing currency",
  low_confidence: "Low confidence",
  possible_duplicate: "Possible duplicate",
  ungrounded_field: "Value not found in the document",
  unparseable_value: "Value could not be read",
};

export const reasonMessage = (reason: string | null | undefined): string | null =>
  reason ? (REASONS[reason] ?? null) : null;

export const errorCodeMessage = (code: string | null | undefined): string | null =>
  code ? (ERROR_CODES[code] ?? null) : null;

export const findingTitle = (code: string): string => FINDING_TITLES[code] ?? code.replaceAll("_", " ");

/** One sentence for any failed request. */
export function errorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return "Something went wrong. Try again.";
  if (error.status === 0) return "The server could not be reached. Check your connection and try again.";
  if (error.status === 502) return "The API could not be reached. Try again shortly.";
  if (error.status === 401) return "The API refused the request: the API key is missing or wrong.";
  if (error.status === 404) return "Not found.";
  return reasonMessage(error.reason) ?? (error.field ? error.message : `Request failed (${error.status}).`);
}
