"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { SearchView, type SearchState } from "@/components/SearchView";
import { filtersFromParams, filtersToParams } from "@/lib/filters";
import type { SearchMode } from "@/lib/types";

const MODES: SearchMode[] = ["hybrid", "keyword", "semantic"];

/** The query, the mode and the filters live in the address, so a search can be shared and survives a reload. */
export function SearchPage() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const mode = params.get("mode") as SearchMode;
  const state: SearchState = {
    q: params.get("q") ?? "",
    mode: MODES.includes(mode) ? mode : "hybrid",
    filters: filtersFromParams(params),
  };

  function change(next: Partial<SearchState>) {
    const merged = { ...state, ...next };
    const query = filtersToParams(merged.filters);
    if (merged.q) query.set("q", merged.q);
    if (merged.mode !== "hybrid") query.set("mode", merged.mode);
    const text = query.toString();
    router.replace(text ? `${pathname}?${text}` : pathname);
  }

  return <SearchView state={state} onChange={change} />;
}
