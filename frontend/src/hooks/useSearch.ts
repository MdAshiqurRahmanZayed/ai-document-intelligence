"use client";

import { useQuery } from "@tanstack/react-query";

import { api, ApiError } from "@/lib/api";
import type { DocumentFilters, SearchMode } from "@/lib/types";

/** Runs a search. A blank query makes no request at all. */
export function useSearch(query: string, mode: SearchMode, filters: DocumentFilters) {
  const text = query.trim();
  return useQuery({
    queryKey: ["search", text, mode, filters],
    queryFn: () => api.search(text, mode, filters),
    enabled: text !== "",
    retry: (count, error) => count < 1 && !(error instanceof ApiError && error.status >= 400 && error.status < 500),
  });
}
