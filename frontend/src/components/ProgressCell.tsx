import { Progress } from "@/components/ui/Progress";
import { errorCodeMessage } from "@/lib/messages";
import { processingProgress, type Progress as ProgressInfo } from "@/lib/progress";
import type { DocumentListItem } from "@/lib/types";

/** The processing position of a list row: a bar while it runs, the outcome once it stops. */
export function ProgressCell({ doc, progress = processingProgress(doc) }: { doc: Pick<DocumentListItem, "status" | "source_type" | "error_code">; progress?: ProgressInfo }) {
  if (progress.finished === "failed") {
    return (
      <span className="text-sm text-red-700 dark:text-red-400">
        {errorCodeMessage(doc.error_code) ?? "Processing failed"}
      </span>
    );
  }
  if (progress.finished) {
    return <span className="text-sm text-zinc-500">{progress.label}</span>;
  }
  return (
    <div className="flex min-w-40 flex-col gap-1">
      <div className="flex justify-between text-xs text-zinc-500">
        <span>{progress.label}</span>
        <span className="tabular-nums">{progress.percent}%</span>
      </div>
      <Progress value={progress.percent} label={`Processing: ${progress.label}`} />
    </div>
  );
}
