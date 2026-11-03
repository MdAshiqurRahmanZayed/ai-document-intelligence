import { DOCUMENT_STATUSES, type DocumentFilters, type DocumentStatus } from "./types";

export const FILTER_KEYS = [
  "status",
  "supplier",
  "invoice_number",
  "date_from",
  "date_to",
  "amount_min",
  "amount_max",
  "currency",
] as const satisfies readonly (keyof DocumentFilters)[];

/** Filters from a query string; an unknown status is ignored. */
export function filtersFromParams(params: URLSearchParams): DocumentFilters {
  const filters: DocumentFilters = {};
  for (const key of FILTER_KEYS) {
    const value = params.get(key)?.trim();
    if (!value) continue;
    if (key === "status") {
      if (DOCUMENT_STATUSES.includes(value as DocumentStatus)) filters.status = value as DocumentStatus;
    } else {
      filters[key] = value;
    }
  }
  return filters;
}

/** A query string holding the non-empty filters, keeping any other parameters of `base`. */
export function filtersToParams(filters: DocumentFilters, base?: URLSearchParams): URLSearchParams {
  const params = new URLSearchParams(base);
  for (const key of FILTER_KEYS) params.delete(key);
  for (const key of FILTER_KEYS) {
    const value = filters[key]?.trim();
    if (value) params.set(key, value);
  }
  return params;
}

export const hasFilters = (filters: DocumentFilters) => FILTER_KEYS.some((key) => Boolean(filters[key]?.trim()));
