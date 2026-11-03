"use client";

import Link from "next/link";
import { useState } from "react";

import { FilterBar } from "@/components/FilterBar";
import { InvoiceSummaryCell } from "@/components/DocumentsView";
import { Snippet } from "@/components/Snippet";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Input } from "@/components/ui/Input";
import { Spinner } from "@/components/ui/Spinner";
import { DocumentStatusBadge } from "@/components/ui/StatusBadge";
import { useSearch } from "@/hooks/useSearch";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/cn";
import type { DocumentFilters, SearchMode } from "@/lib/types";

export interface SearchState {
  q: string;
  mode: SearchMode;
  filters: DocumentFilters;
}

const MODES: { value: SearchMode; label: string; help: string }[] = [
  { value: "hybrid", label: "Hybrid", help: "Words and meaning together" },
  { value: "keyword", label: "Keyword", help: "Exact words" },
  { value: "semantic", label: "Semantic", help: "Meaning, even without the same words" },
];

export function SearchView({ state, onChange }: { state: SearchState; onChange: (next: Partial<SearchState>) => void }) {
  const [draft, setDraft] = useState(state.q);
  const search = useSearch(state.q, state.mode, state.filters);

  return (
    <div className="flex flex-col gap-4">
      <Card className="flex flex-col gap-4">
        <form
          role="search"
          onSubmit={(event) => {
            event.preventDefault();
            onChange({ q: draft.trim() });
          }}
          className="flex flex-col gap-3 sm:flex-row sm:items-end"
        >
          <div className="flex-1">
            <Input label="Search the text of your documents" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="e.g. payment terms, freight, penalty clause" />
          </div>
          <Button type="submit">Search</Button>
        </form>

        <fieldset className="flex flex-wrap gap-2">
          <legend className="sr-only">Search mode</legend>
          {MODES.map((m) => (
            <label
              key={m.value}
              title={m.help}
              className={cn(
                "cursor-pointer rounded-full border px-3 py-1.5 text-sm font-medium transition-colors",
                state.mode === m.value
                  ? "border-indigo-600 bg-indigo-600 text-white"
                  : "border-zinc-300 text-zinc-700 hover:bg-zinc-50 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800",
              )}
            >
              <input type="radio" name="mode" value={m.value} checked={state.mode === m.value} onChange={() => onChange({ mode: m.value })} className="sr-only" />
              {m.label}
            </label>
          ))}
        </fieldset>
      </Card>

      <details className="group" open={Object.keys(state.filters).length > 0}>
        <summary className="cursor-pointer text-sm font-medium text-zinc-600 dark:text-zinc-400">Filters</summary>
        <div className="mt-3">
          <FilterBar key={JSON.stringify(state.filters)} value={state.filters} onApply={(filters) => onChange({ filters })} />
        </div>
      </details>

      <Results state={state} search={search} onChange={onChange} />
    </div>
  );
}

function Results({ state, search, onChange }: { state: SearchState; search: ReturnType<typeof useSearch>; onChange: (next: Partial<SearchState>) => void }) {
  if (state.q.trim() === "") {
    return <EmptyState title="Search your documents">Type a word or a question above.</EmptyState>;
  }
  if (search.isPending) {
    return (
      <div className="flex justify-center py-16 text-zinc-500">
        <Spinner label="Searching" />
      </div>
    );
  }
  if (search.error instanceof ApiError && search.error.reason === "semantic_unavailable") {
    return (
      <EmptyState title="Semantic search is not available">
        It needs a configured Google API key.{" "}
        <button type="button" onClick={() => onChange({ mode: "keyword" })} className="font-medium text-indigo-600 hover:underline">
          Search by keyword instead
        </button>
      </EmptyState>
    );
  }
  if (search.isError) return <ErrorState error={search.error} onRetry={() => search.refetch()} />;

  const { results, mode_used } = search.data;
  return (
    <div className="flex flex-col gap-3">
      {mode_used !== state.mode && (
        <p role="status" className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
          Showing {mode_used} results: {state.mode} search is not available without a Google API key.
        </p>
      )}
      {results.length === 0 ? (
        <EmptyState title="Nothing matched">Try another search mode, different words, or fewer filters.</EmptyState>
      ) : (
        <ul className="flex flex-col gap-3" aria-label="Search results">
          {results.map((hit) => (
            <li key={hit.document_id}>
              <Card className="flex flex-col gap-2">
                <div className="flex flex-wrap items-center gap-3">
                  <Link href={`/documents/${hit.document_id}`} className="font-medium text-indigo-600 hover:underline">
                    {hit.filename}
                  </Link>
                  <DocumentStatusBadge status={hit.status} />
                  {hit.page_no !== null && <span className="text-xs text-zinc-500">page {hit.page_no}</span>}
                </div>
                <Snippet snippet={hit.snippet} />
                <InvoiceSummaryCell invoices={hit.invoices} />
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
