"use client";

import Link from "next/link";

import { FilterBar } from "@/components/FilterBar";
import { ProgressCell } from "@/components/ProgressCell";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { DocumentStatusBadge } from "@/components/ui/StatusBadge";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { useDocuments } from "@/hooks/useDocuments";
import { hasFilters } from "@/lib/filters";
import { formatAmount, formatDateTime } from "@/lib/format";
import type { DocumentFilters, InvoiceSummary } from "@/lib/types";

export function InvoiceSummaryCell({ invoices }: { invoices: InvoiceSummary[] }) {
  if (invoices.length === 0) return <span className="text-zinc-400">—</span>;
  return (
    <ul className="flex flex-col gap-1">
      {invoices.map((inv) => (
        <li key={inv.invoice_index} className="text-sm">
          <span className="font-medium">{inv.supplier_name ?? "Unknown supplier"}</span>
          <span className="text-zinc-500">
            {" "}
            · {inv.invoice_number ?? "no number"} · {formatAmount(inv.total, inv.currency)}
          </span>
        </li>
      ))}
    </ul>
  );
}

export function DocumentsView({ filters, onFiltersChange }: { filters: DocumentFilters; onFiltersChange: (f: DocumentFilters) => void }) {
  const query = useDocuments(filters);
  const docs = query.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <div className="flex flex-col gap-4">
      <FilterBar key={JSON.stringify(filters)} value={filters} onApply={onFiltersChange} />

      {query.isPending ? (
        <div className="flex justify-center py-16 text-zinc-500">
          <Spinner label="Loading documents" />
        </div>
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : docs.length === 0 ? (
        hasFilters(filters) ? (
          <EmptyState title="No documents match these filters">Try removing a filter.</EmptyState>
        ) : (
          <EmptyState title="No documents yet">
            <Link href="/upload" className="font-medium text-indigo-600 hover:underline">
              Upload your first documents
            </Link>
          </EmptyState>
        )
      ) : (
        <>
          <Table aria-label="Documents">
            <THead>
              <TR>
                <TH>Document</TH>
                <TH>Status</TH>
                <TH>Progress</TH>
                <TH>Invoices</TH>
                <TH>Uploaded</TH>
              </TR>
            </THead>
            <TBody>
              {docs.map((doc) => (
                <TR key={doc.id}>
                  <TD>
                    <Link href={`/documents/${doc.id}`} className="font-medium text-indigo-600 hover:underline">
                      {doc.filename}
                    </Link>
                    <p className="text-xs text-zinc-500">{doc.page_count ? `${doc.page_count} ${doc.page_count === 1 ? "page" : "pages"}` : ""}</p>
                  </TD>
                  <TD>
                    <DocumentStatusBadge status={doc.status} />
                  </TD>
                  <TD>
                    <ProgressCell doc={doc} />
                  </TD>
                  <TD>
                    <InvoiceSummaryCell invoices={doc.invoices} />
                  </TD>
                  <TD className="whitespace-nowrap text-zinc-500">{formatDateTime(doc.created_at)}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
          {query.hasNextPage && (
            <div className="flex justify-center">
              <Button variant="secondary" loading={query.isFetchingNextPage} onClick={() => query.fetchNextPage()}>
                Load more
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
