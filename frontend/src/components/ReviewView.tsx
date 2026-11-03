"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { InvoiceSummaryCell } from "@/components/DocumentsView";
import { FindingsCount } from "@/components/FindingsCount";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Modal } from "@/components/ui/Modal";
import { Spinner } from "@/components/ui/Spinner";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { useToast } from "@/components/ui/Toast";
import { useDocuments } from "@/hooks/useDocuments";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { errorCodeMessage, errorMessage } from "@/lib/messages";
import type { DocumentListItem, FromStage, RetryFailedResponse } from "@/lib/types";

export function ReviewView() {
  return (
    <div className="flex flex-col gap-8">
      <NeedsReview />
      <Failed />
    </div>
  );
}

function NeedsReview() {
  const query = useDocuments({ status: "NEEDS_REVIEW" });
  const docs = query.data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <section aria-labelledby="queue" className="flex flex-col gap-3">
      <h2 id="queue" className="text-lg font-semibold">
        Needs review {query.data && <span className="text-sm font-normal text-zinc-500">({docs.length}{query.hasNextPage ? "+" : ""})</span>}
      </h2>
      {query.isPending ? (
        <div className="flex justify-center py-10 text-zinc-500">
          <Spinner label="Loading the review queue" />
        </div>
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : docs.length === 0 ? (
        <EmptyState title="Nothing needs review">Documents with errors or low-confidence values show up here.</EmptyState>
      ) : (
        <>
          <Table aria-label="Documents needing review">
            <THead>
              <TR>
                <TH>Document</TH>
                <TH>Invoices</TH>
                <TH>Findings</TH>
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
                  </TD>
                  <TD>
                    <InvoiceSummaryCell invoices={doc.invoices} />
                  </TD>
                  <TD>
                    <FindingsCount id={doc.id} status={doc.status} />
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
    </section>
  );
}

/** Each document restarts from the step that failed, the same rule "Retry all" uses on the server. */
const fromStage = (doc: DocumentListItem): FromStage => (doc.error_code === "extraction_failed" ? "extract" : "ingest");

function Failed() {
  const query = useDocuments({ status: "FAILED" });
  const docs = query.data?.pages.flatMap((p) => p.items) ?? [];
  const [selected, setSelected] = useState<Set<string>>(new Set());
  // Documents that left the list (retried, or no longer failed) drop out of the selection.
  const chosen = docs.filter((d) => selected.has(d.id));
  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (!next.delete(id)) next.add(id);
      return next;
    });

  return (
    <section aria-labelledby="failed" className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-3">
        <h2 id="failed" className="text-lg font-semibold">
          Failed {query.data && <span className="text-sm font-normal text-zinc-500">({docs.length}{query.hasNextPage ? "+" : ""})</span>}
        </h2>
        {docs.length > 0 && (
          <div className="flex items-center gap-2">
            <RetrySelected chosen={chosen} onDone={(ids) => setSelected((prev) => new Set([...prev].filter((id) => !ids.includes(id))))} />
            <RetryAll />
          </div>
        )}
      </div>
      {query.isPending ? (
        <div className="flex justify-center py-10 text-zinc-500">
          <Spinner label="Loading failed documents" />
        </div>
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : docs.length === 0 ? (
        <EmptyState title="No failed documents" />
      ) : (
        <>
          <Table aria-label="Failed documents">
            <THead>
              <TR>
                <TH className="w-10">
                  <input
                    type="checkbox"
                    aria-label="Select all failed documents"
                    checked={chosen.length === docs.length}
                    ref={(el) => {
                      if (el) el.indeterminate = chosen.length > 0 && chosen.length < docs.length;
                    }}
                    onChange={(e) => setSelected(e.target.checked ? new Set(docs.map((d) => d.id)) : new Set())}
                  />
                </TH>
                <TH>Document</TH>
                <TH>Why it failed</TH>
                <TH>Uploaded</TH>
              </TR>
            </THead>
            <TBody>
              {docs.map((doc) => (
                <TR key={doc.id}>
                  <TD>
                    <input
                      type="checkbox"
                      aria-label={`Select ${doc.filename}`}
                      checked={selected.has(doc.id)}
                      onChange={() => toggle(doc.id)}
                    />
                  </TD>
                  <TD>
                    <Link href={`/documents/${doc.id}`} className="font-medium text-indigo-600 hover:underline">
                      {doc.filename}
                    </Link>
                  </TD>
                  <TD className="text-red-700 dark:text-red-400">{errorCodeMessage(doc.error_code) ?? "Processing failed."}</TD>
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
    </section>
  );
}

function RetrySelected({ chosen, onDone }: { chosen: DocumentListItem[]; onDone: (queuedIds: string[]) => void }) {
  const queryClient = useQueryClient();
  const toast = useToast();

  const retry = useMutation({
    mutationFn: async () => {
      const outcomes = await Promise.allSettled(chosen.map((doc) => api.reprocess(doc.id, fromStage(doc))));
      const queued = chosen.filter((_, i) => outcomes[i].status === "fulfilled").map((d) => d.id);
      return { queued, notQueued: chosen.length - queued.length };
    },
    onSuccess: ({ queued, notQueued }) => {
      toast(`${queued.length} queued${notQueued ? `, ${notQueued} could not be queued` : ""}.`, notQueued ? "info" : "success");
      onDone(queued);
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  return (
    <Button disabled={chosen.length === 0} loading={retry.isPending} onClick={() => retry.mutate()}>
      Retry selected{chosen.length > 0 && ` (${chosen.length})`}
    </Button>
  );
}

function RetryAll() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [done, setDone] = useState<RetryFailedResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const retry = useMutation({
    mutationFn: () => api.retryFailed(),
    onSuccess: (response) => {
      setDone(response);
      setOpen(false);
      toast(`${response.queued.length} queued${response.not_queued ? `, ${response.not_queued} could not be queued` : ""}.`, response.not_queued ? "info" : "success");
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
    onError: (e) => setError(errorMessage(e)),
  });

  return (
    <>
      <Button variant="secondary" onClick={() => { setError(null); setOpen(true); }}>
        Retry all failed
      </Button>
      <Modal open={open} title="Retry all failed documents?" onClose={() => setOpen(false)}>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">Every failed document is queued again, oldest first, from the step that failed.</p>
        {error && (
          <p role="alert" className="mt-3 text-sm text-red-700 dark:text-red-400">
            {error}
          </p>
        )}
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button loading={retry.isPending} onClick={() => retry.mutate()}>
            Retry all
          </Button>
        </div>
      </Modal>
      {done && (
        <span role="status" className="text-sm text-zinc-500">
          {done.queued.length} queued{done.not_queued > 0 && `, ${done.not_queued} not queued`}
        </span>
      )}
    </>
  );
}
