"use client";

import { useResult } from "@/hooks/useDocument";
import type { DocumentStatus } from "@/lib/types";

/** "2 errors · 1 warning" for a document, from its result (cached, and shared with its detail page). */
export function FindingsCount({ id, status }: { id: string; status: DocumentStatus }) {
  const { data, isPending, isError } = useResult(id, status);
  if (isPending) return <span className="text-zinc-400">…</span>;
  if (isError) return <span className="text-zinc-400">—</span>;

  const findings = [...data.document_errors, ...data.invoices.flatMap((i) => i.validation_errors)];
  const errors = findings.filter((f) => f.severity === "error").length;
  const warnings = findings.length - errors;
  const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;
  if (findings.length === 0) return <span className="text-zinc-500">none</span>;
  return (
    <span className="whitespace-nowrap text-sm">
      {errors > 0 && <span className="font-medium text-red-700 dark:text-red-400">{plural(errors, "error")}</span>}
      {errors > 0 && warnings > 0 && <span className="text-zinc-400"> · </span>}
      {warnings > 0 && <span className="text-amber-700 dark:text-amber-400">{plural(warnings, "warning")}</span>}
    </span>
  );
}
