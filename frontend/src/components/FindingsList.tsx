import Link from "next/link";

import { cn } from "@/lib/cn";
import { findingTitle } from "@/lib/messages";
import type { Finding } from "@/lib/types";

/** Validation findings: severity is written out, colour only reinforces it. */
export function FindingsList({ findings }: { findings: Finding[] }) {
  if (findings.length === 0) return null;
  const ordered = [...findings].sort((a, b) => (a.severity === b.severity ? 0 : a.severity === "error" ? -1 : 1));
  return (
    <ul aria-label="Validation findings" className="flex flex-col gap-2">
      {ordered.map((f, i) => (
        <li
          key={`${f.code}-${f.field}-${i}`}
          className={cn(
            "flex flex-col gap-0.5 rounded-lg border px-3 py-2 text-sm",
            f.severity === "error"
              ? "border-red-200 bg-red-50 text-red-900 dark:border-red-900 dark:bg-red-950/40 dark:text-red-100"
              : "border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-100",
          )}
        >
          <p className="flex flex-wrap items-center gap-2 font-medium">
            <span className="rounded bg-white/70 px-1.5 py-0.5 text-xs uppercase tracking-wide dark:bg-black/30">{f.severity === "error" ? "Error" : "Warning"}</span>
            {findingTitle(f.code)}
            {f.field && <span className="font-mono text-xs font-normal opacity-70">{f.field}</span>}
          </p>
          <p>{f.message}</p>
          {f.related_document_id && (
            <Link href={`/documents/${f.related_document_id}`} className="w-fit font-medium underline">
              Open the related document
            </Link>
          )}
        </li>
      ))}
    </ul>
  );
}
