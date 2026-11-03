"use client";

import { useQuery } from "@tanstack/react-query";

import { POLL_MS } from "@/hooks/useDocuments";
import { api, ApiError } from "@/lib/api";
import { isInProgress } from "@/lib/progress";
import type { DocumentStatus } from "@/lib/types";

const retryUnlessClientError = (count: number, error: unknown) =>
  count < 2 && !(error instanceof ApiError && error.status >= 400 && error.status < 500);

/** One document with its processing history; refreshes by itself only while it is in progress. */
export function useDocument(id: string) {
  return useQuery({
    queryKey: ["document", id],
    queryFn: () => api.getDocument(id),
    refetchInterval: (query) => (query.state.data && isInProgress(query.state.data.status) ? POLL_MS : false),
    retry: retryUnlessClientError,
  });
}

/** The extracted invoices. The status is part of the key so a finished extraction is fetched again. */
export function useResult(id: string, status: DocumentStatus | undefined) {
  return useQuery({
    queryKey: ["result", id, status],
    queryFn: () => api.getResult(id),
    enabled: status !== undefined,
    retry: retryUnlessClientError,
  });
}

export function useCorrections(id: string, status: DocumentStatus | undefined) {
  return useQuery({
    queryKey: ["corrections", id, status],
    queryFn: () => api.getCorrections(id),
    enabled: status !== undefined,
  });
}
