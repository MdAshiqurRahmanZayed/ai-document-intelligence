import type { DocumentStatus } from "@/lib/types";

export type Status = "ok" | "error" | "loading";

const styles: Record<Status, string> = {
  ok: "bg-green-100 text-green-800",
  error: "bg-red-100 text-red-800",
  loading: "bg-zinc-100 text-zinc-600",
};

export function StatusBadge({ status, label }: { status: Status; label: string }) {
  return (
    <span
      data-status={status}
      className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-sm font-medium ${styles[status]}`}
    >
      {label}
      <span className="font-mono text-xs uppercase">{status}</span>
    </span>
  );
}

// Document statuses: always a word as well as a colour.

const DOC_STYLES: Record<DocumentStatus, string> = {
  UPLOADED: "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
  QUEUED: "bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-300",
  PROCESSING: "bg-indigo-100 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-300",
  COMPLETED: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  NEEDS_REVIEW: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-300",
  FAILED: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
};

export const DOC_LABELS: Record<DocumentStatus, string> = {
  UPLOADED: "Uploaded",
  QUEUED: "Queued",
  PROCESSING: "Processing",
  COMPLETED: "Completed",
  NEEDS_REVIEW: "Needs review",
  FAILED: "Failed",
};

export function DocumentStatusBadge({ status }: { status: DocumentStatus }) {
  return (
    <span
      data-status={status}
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${DOC_STYLES[status]}`}
    >
      {DOC_LABELS[status]}
    </span>
  );
}
