import type { DocumentStatus, ProcessingEvent, SourceType, Stage } from "./types";

export type StepKey = "uploaded" | "ingest" | "ocr" | "extract" | "done";
export type StepState = "waiting" | "running" | "done" | "failed";

export interface Step {
  key: StepKey;
  label: string;
  state: StepState;
  durationMs: number | null;
  attempt: number | null;
  error: string | null;
}

export type Finished = "complete" | "needs_review" | "failed";

export interface Progress {
  /** 0 to 100: expected steps finished, not an estimate of time. */
  percent: number;
  /** The current step in words ("Recognising text"), or the final state. */
  label: string;
  steps: Step[];
  finished: Finished | null;
  failedStep: StepKey | null;
  /** False for a list row, which has no processing history and only a rough position. */
  exact: boolean;
}

export interface ProgressInput {
  status: DocumentStatus;
  source_type: SourceType | null;
  error_message?: string | null;
}

const LABELS: Record<StepKey, string> = {
  uploaded: "Uploaded",
  ingest: "Reading the file",
  ocr: "Text recognition",
  extract: "Extracting invoices",
  done: "Done",
};

const RUNNING: Record<StepKey, string> = {
  uploaded: "Uploaded",
  ingest: "Reading the file",
  ocr: "Recognising text",
  extract: "Extracting invoices",
  done: "Finishing",
};

const FLOOR = 10;

function finishedOf(status: DocumentStatus): Finished | null {
  if (status === "COMPLETED") return "complete";
  if (status === "NEEDS_REVIEW") return "needs_review";
  if (status === "FAILED") return "failed";
  return null;
}

const FINAL_LABEL: Record<Finished, string> = {
  complete: "Complete",
  needs_review: "Needs review",
  failed: "Failed",
};

/** Rough position from the status alone (a list row has no events). */
function coarse(doc: ProgressInput): Progress {
  const finished = finishedOf(doc.status);
  const table: Record<DocumentStatus, [number, string]> = {
    UPLOADED: [5, "Uploaded"],
    QUEUED: [FLOOR, "Waiting for a worker"],
    PROCESSING: [50, "Processing"],
    COMPLETED: [100, FINAL_LABEL.complete],
    NEEDS_REVIEW: [100, FINAL_LABEL.needs_review],
    FAILED: [100, FINAL_LABEL.failed],
  };
  const [percent, label] = table[doc.status];
  return { percent, label, steps: [], finished, failedStep: null, exact: false };
}

/** The state of one stage from its events (oldest first): the last event decides. */
function stageState(events: ProcessingEvent[], stage: Stage): Pick<Step, "state" | "durationMs" | "attempt" | "error"> {
  const mine = events.filter((e) => e.stage === stage);
  const last = mine[mine.length - 1];
  if (!last) return { state: "waiting", durationMs: null, attempt: null, error: null };
  const state: StepState = last.status === "started" ? "running" : last.status === "succeeded" ? "done" : "failed";
  return {
    state,
    durationMs: last.status === "succeeded" ? last.duration_ms : null,
    attempt: last.attempt,
    error: last.status === "failed" ? (last.error_message ?? last.error_code) : null,
  };
}

/**
 * Where a document is in processing, from its status and (when known) its processing history.
 * The percentage is the share of expected steps that finished. See the web-document-review spec.
 */
export function processingProgress(doc: ProgressInput, events?: ProcessingEvent[]): Progress {
  if (!events) return coarse(doc);

  const finished = finishedOf(doc.status);
  const has = (stage: Stage) => events.some((e) => e.stage === stage);

  // A settled document ran what it ran; one in progress or failed still has steps ahead of it.
  const settled = finished === "complete" || finished === "needs_review";
  // Text recognition applies to PDFs and images, until the document is seen taking the digital path.
  const ocrExpected = has("ocr") || (doc.source_type !== "spreadsheet" && !(has("extract") && !has("ocr")) && !settled);
  const extractExpected = has("extract") || !settled;

  const keys: StepKey[] = ["uploaded", "ingest"];
  if (ocrExpected) keys.push("ocr");
  if (extractExpected) keys.push("extract");
  keys.push("done");

  const steps: Step[] = keys.map((key) => {
    if (key === "uploaded") return { key, label: LABELS[key], state: "done", durationMs: null, attempt: null, error: null };
    if (key === "done") {
      const done = finished === "complete" || finished === "needs_review";
      return { key, label: LABELS[key], state: done ? "done" : "waiting", durationMs: null, attempt: null, error: null };
    }
    return { key, label: LABELS[key], ...stageState(events, key) };
  });

  const failed = steps.find((s) => s.state === "failed");
  // A document that failed before any event (for example the queue refused it) failed at its first step.
  const failedStep = finished === "failed" ? (failed ?? steps.find((s) => s.state !== "done" && s.key !== "uploaded"))?.key ?? null : null;
  if (finished === "failed" && failedStep) {
    const step = steps.find((s) => s.key === failedStep)!;
    step.state = "failed";
    step.error ??= doc.error_message ?? null;
  }

  // "Done" is part of the total but is only reached when the document settles.
  const doneCount = steps.filter((s) => s.key !== "done" && s.state === "done").length;
  const computed = Math.round((doneCount / steps.length) * 100);
  const percent = finished && finished !== "failed" ? 100 : Math.max(FLOOR, computed);

  const current = steps.find((s) => s.state !== "done");
  let label: string;
  if (finished) label = FINAL_LABEL[finished];
  else if (!current) label = RUNNING.done;
  else if (current.state === "running") label = RUNNING[current.key];
  else if (current.key === "ingest" && doc.status === "QUEUED") label = "Waiting for a worker";
  else label = RUNNING[current.key];

  return { percent, label, steps, finished, failedStep, exact: true };
}

/** Whether the document may still change by itself, so the page should keep refreshing. */
export function isInProgress(status: DocumentStatus): boolean {
  return status === "UPLOADED" || status === "QUEUED" || status === "PROCESSING";
}
