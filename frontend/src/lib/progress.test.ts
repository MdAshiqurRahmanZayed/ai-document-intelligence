import { describe, expect, it } from "vitest";

import { isInProgress, processingProgress } from "./progress";
import type { DocumentStatus, EventStatus, ProcessingEvent, Stage } from "./types";

const ev = (stage: Stage, status: EventStatus, attempt = 1, duration_ms: number | null = null, error_message: string | null = null): ProcessingEvent => ({
  stage,
  status,
  attempt,
  duration_ms,
  error_code: null,
  error_message,
  created_at: "2026-11-03T10:00:00Z",
});

const doc = (status: DocumentStatus, source_type = "pdf", error_message: string | null = null) => ({ status, source_type, error_message });

describe("processingProgress with history", () => {
  it("scanned PDF, text recognition running: 40% and 'Recognising text'", () => {
    const p = processingProgress(doc("PROCESSING"), [ev("ingest", "started"), ev("ingest", "succeeded", 1, 12), ev("ocr", "started")]);

    expect(p.percent).toBe(40);
    expect(p.label).toBe("Recognising text");
    expect(p.steps.map((s) => s.key)).toEqual(["uploaded", "ingest", "ocr", "extract", "done"]);
    expect(p.finished).toBeNull();
  });

  it("spreadsheet skips recognition: 50% while extracting", () => {
    const p = processingProgress(doc("PROCESSING", "spreadsheet"), [ev("ingest", "started"), ev("ingest", "succeeded"), ev("extract", "started")]);

    expect(p.steps.map((s) => s.key)).toEqual(["uploaded", "ingest", "extract", "done"]);
    expect(p.percent).toBe(50);
    expect(p.label).toBe("Extracting invoices");
  });

  it("queued with no history: floor percentage and 'Waiting for a worker'", () => {
    const p = processingProgress(doc("QUEUED"), []);

    expect(p.percent).toBeGreaterThanOrEqual(10);
    expect(p.percent).toBeLessThan(40);
    expect(p.label).toBe("Waiting for a worker");
    expect(p.steps[1].state).toBe("waiting");
  });

  it("a failed recognition step is marked with its error and later steps wait", () => {
    const p = processingProgress(doc("FAILED"), [
      ev("ingest", "succeeded"),
      ev("ocr", "started"),
      ev("ocr", "failed", 1, null, "TesseractError"),
    ]);

    expect(p.finished).toBe("failed");
    expect(p.failedStep).toBe("ocr");
    const ocr = p.steps.find((s) => s.key === "ocr")!;
    expect(ocr).toMatchObject({ state: "failed", error: "TesseractError" });
    expect(p.steps.find((s) => s.key === "extract")!.state).toBe("waiting");
    expect(p.label).toBe("Failed");
  });

  it("a document that failed before any event fails at its first step", () => {
    const p = processingProgress(doc("FAILED", "pdf", "queue_unavailable"), []);

    expect(p.failedStep).toBe("ingest");
    expect(p.steps.find((s) => s.key === "ingest")).toMatchObject({ state: "failed", error: "queue_unavailable" });
  });

  it("shows the attempt number of a retried step", () => {
    const p = processingProgress(doc("PROCESSING"), [ev("ingest", "failed", 1, null, "boom"), ev("ingest", "started", 2)]);

    const ingest = p.steps.find((s) => s.key === "ingest")!;
    expect(ingest).toMatchObject({ state: "running", attempt: 2 });
  });

  it("finished: complete, every step done, 100%", () => {
    const p = processingProgress(doc("COMPLETED"), [
      ev("ingest", "succeeded", 1, 10),
      ev("extract", "succeeded", 1, 2000),
    ]);

    expect(p.finished).toBe("complete");
    expect(p.percent).toBe(100);
    expect(p.label).toBe("Complete");
    expect(p.steps.every((s) => s.state === "done")).toBe(true);
    expect(p.steps.map((s) => s.key)).toEqual(["uploaded", "ingest", "extract", "done"]);
    expect(p.steps.find((s) => s.key === "extract")!.durationMs).toBe(2000);
  });

  it("a finished document without extraction does not list the extract step", () => {
    const p = processingProgress(doc("COMPLETED", "spreadsheet"), [ev("ingest", "succeeded")]);

    expect(p.steps.map((s) => s.key)).toEqual(["uploaded", "ingest", "done"]);
  });

  it("a digital PDF that went straight to extraction does not expect recognition", () => {
    const p = processingProgress(doc("PROCESSING"), [ev("ingest", "succeeded"), ev("extract", "started")]);

    expect(p.steps.map((s) => s.key)).toEqual(["uploaded", "ingest", "extract", "done"]);
  });

  it("an image expects recognition", () => {
    const p = processingProgress(doc("PROCESSING", "image"), [ev("ingest", "started")]);

    expect(p.steps.map((s) => s.key)).toContain("ocr");
  });

  it("the percentage never goes down as a scanned document advances", () => {
    const history: ProcessingEvent[][] = [
      [],
      [ev("ingest", "started")],
      [ev("ingest", "succeeded")],
      [ev("ingest", "succeeded"), ev("ocr", "started")],
      [ev("ingest", "succeeded"), ev("ocr", "succeeded")],
      [ev("ingest", "succeeded"), ev("ocr", "succeeded"), ev("extract", "started")],
    ];
    const percents = history.map((events, i) => processingProgress(doc(i === 0 ? "QUEUED" : "PROCESSING"), events).percent);

    expect(percents).toEqual([...percents].sort((a, b) => a - b));
  });
});

describe("processingProgress without history (list rows)", () => {
  it.each([
    ["QUEUED", "Waiting for a worker", false],
    ["PROCESSING", "Processing", false],
    ["COMPLETED", "Complete", true],
    ["NEEDS_REVIEW", "Needs review", true],
    ["FAILED", "Failed", true],
  ] as const)("%s", (status, label, isFinal) => {
    const p = processingProgress(doc(status));
    expect(p.label).toBe(label);
    expect(p.exact).toBe(false);
    expect(p.finished !== null).toBe(isFinal);
    expect(p.percent).toBeGreaterThanOrEqual(5);
  });
});

describe("isInProgress", () => {
  it.each([["UPLOADED", true], ["QUEUED", true], ["PROCESSING", true], ["COMPLETED", false], ["NEEDS_REVIEW", false], ["FAILED", false]] as const)(
    "%s -> %s",
    (status, expected) => expect(isInProgress(status)).toBe(expected),
  );
});
