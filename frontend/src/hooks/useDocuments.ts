"use client";

import { useInfiniteQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { isInProgress } from "@/lib/progress";
import type { DocumentFilters } from "@/lib/types";

/** How often the list refreshes while something on it is still being processed. */
export const POLL_MS = 2000;

/** Documents newest first, a page at a time. Refreshes by itself only while one is in progress. */
export function useDocuments(filters: DocumentFilters) {
  return useInfiniteQuery({
    queryKey: ["documents", filters],
    queryFn: ({ pageParam }) => api.listDocuments(filters, pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
    refetchInterval: (query) => {
      const pages = query.state.data?.pages ?? [];
      return pages.some((page) => page.items.some((doc) => isInProgress(doc.status))) ? POLL_MS : false;
    },
  });
}
