"use client";

import Link from "next/link";

import { CorrectionHistory } from "@/components/CorrectionHistory";
import { FileViewer } from "@/components/FileViewer";
import { FindingsList } from "@/components/FindingsList";
import { InvoiceCard } from "@/components/InvoiceCard";
import { ReprocessButton } from "@/components/ReprocessButton";
import { StepsTimeline } from "@/components/StepsTimeline";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Progress } from "@/components/ui/Progress";
import { Spinner } from "@/components/ui/Spinner";
import { DocumentStatusBadge } from "@/components/ui/StatusBadge";
import { useDocument, useResult } from "@/hooks/useDocument";
import { ApiError } from "@/lib/api";
import { formatBytes, formatDateTime } from "@/lib/format";
import { errorCodeMessage } from "@/lib/messages";
import { isInProgress, processingProgress } from "@/lib/progress";
import type { DocumentDetail as Detail } from "@/lib/types";

export function DocumentDetail({ id }: { id: string }) {
  const doc = useDocument(id);

  if (doc.isPending) {
    return (
      <div className="flex justify-center py-20 text-zinc-500">
        <Spinner label="Loading the document" />
      </div>
    );
  }
  if (doc.error instanceof ApiError && doc.error.status === 404) {
    return (
      <EmptyState title="Document not found">
        <Link href="/documents" className="font-medium text-indigo-600 hover:underline">
          Back to the documents
        </Link>
      </EmptyState>
    );
  }
  if (doc.isError) return <ErrorState error={doc.error} onRetry={() => doc.refetch()} />;

  return <Loaded doc={doc.data} />;
}

function Loaded({ doc }: { doc: Detail }) {
  const progress = processingProgress(doc, doc.events);
  const busy = isInProgress(doc.status);
  const pages = doc.page_count ? `${doc.page_count} ${doc.page_count === 1 ? "page" : "pages"}` : null;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <Link href="/documents" className="text-sm text-zinc-500 hover:underline">
            ← Documents
          </Link>
          <h1 className="mt-1 flex flex-wrap items-center gap-3 break-all text-2xl font-semibold tracking-tight">
            {doc.filename}
            <DocumentStatusBadge status={doc.status} />
          </h1>
          <p className="mt-1 text-sm text-zinc-500">
            {[doc.source_type?.toUpperCase(), formatBytes(doc.size), pages, `uploaded ${formatDateTime(doc.created_at)}`].filter(Boolean).join(" · ")}
          </p>
        </div>
        <ReprocessButton id={doc.id} status={doc.status} />
      </div>

      {doc.status === "FAILED" && (
        <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 dark:border-red-900 dark:bg-red-950/40">
          <p className="font-medium text-red-900 dark:text-red-100">{errorCodeMessage(doc.error_code) ?? "Processing failed."}</p>
          {doc.error_message && <p className="mt-1 break-words font-mono text-xs text-red-800 dark:text-red-200">{doc.error_message}</p>}
          <p className="mt-2 text-sm text-red-800 dark:text-red-200">Use Reprocess to try again.</p>
        </div>
      )}

      <Card className="flex flex-col gap-4">
        <div className="flex items-center justify-between gap-3">
          <h2 className="font-semibold">Processing</h2>
          {!progress.finished && <span className="text-sm tabular-nums text-zinc-500">{progress.label} · {progress.percent}%</span>}
        </div>
        {!progress.finished && <Progress value={progress.percent} label={`Processing: ${progress.label}`} />}
        <StepsTimeline steps={progress.steps} />
      </Card>

      <div className="grid items-start gap-6 lg:grid-cols-2">
        <div className="lg:sticky lg:top-20">
          <FileViewer doc={doc} />
        </div>
        <Results id={doc.id} status={doc.status} busy={busy} />
      </div>

      <CorrectionHistory id={doc.id} status={doc.status} />
    </div>
  );
}

function Results({ id, status, busy }: { id: string; status: Detail["status"]; busy: boolean }) {
  const result = useResult(id, status);

  if (result.isPending) {
    return (
      <div className="flex justify-center py-12 text-zinc-500">
        <Spinner label="Loading the extracted values" />
      </div>
    );
  }
  if (result.isError) return <ErrorState error={result.error} onRetry={() => result.refetch()} />;

  const { invoices, document_errors } = result.data;
  return (
    <div className="flex flex-col gap-6">
      <FindingsList findings={document_errors} />
      {invoices.length === 0 ? (
        <EmptyState title={busy ? "Waiting for the extracted invoice" : "No invoice was extracted"}>
          {busy
            ? "The values appear here when extraction finishes."
            : "Extraction is switched off (no Google API key) or the document holds no invoice. Reprocess it once extraction is available."}
        </EmptyState>
      ) : (
        invoices.map((invoice) => (
          // A new version has new values and findings, so the form starts again from them.
          <InvoiceCard key={`${invoice.invoice_index}-${invoice.version}`} documentId={id} invoice={invoice} busy={busy} />
        ))
      )}
    </div>
  );
}
