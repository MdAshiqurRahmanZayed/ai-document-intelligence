import { afterEach, describe, expect, it, vi } from "vitest";

import { checkFile, runPool, uploadFile } from "./upload";

describe("checkFile", () => {
  it.each([
    ["a.pdf", 10, null],
    ["scan.JPG", 10, null],
    ["data.csv", 10, null],
    ["notes.docx", 10, "unsupported_type"],
    ["noext", 10, "unsupported_type"],
    ["empty.pdf", 0, "empty_file"],
    ["huge.pdf", 101 * 1024 * 1024, "file_too_large"],
  ])("%s (%i bytes) -> %s", (name, size, expected) => {
    expect(checkFile({ name, size })).toBe(expected);
  });
});

class FakeXHR {
  static last: FakeXHR;
  upload: { onprogress?: (e: unknown) => void; onload?: () => void } = {};
  onload?: () => void;
  onerror?: () => void;
  status = 0;
  responseText = "";
  sent: FormData | null = null;
  constructor() {
    FakeXHR.last = this;
  }
  open = vi.fn();
  send(body: FormData) {
    this.sent = body;
  }
  progress(loaded: number, total: number) {
    this.upload.onprogress?.({ lengthComputable: true, loaded, total });
  }
  finish(status: number, body: unknown) {
    this.upload.onload?.();
    this.status = status;
    this.responseText = JSON.stringify(body);
    this.onload?.();
  }
}

describe("uploadFile", () => {
  afterEach(() => vi.unstubAllGlobals());

  function start() {
    vi.stubGlobal("XMLHttpRequest", FakeXHR);
    const onProgress = vi.fn();
    const onSent = vi.fn();
    const promise = uploadFile(new File(["x"], "a.pdf"), { onProgress, onSent });
    return { onProgress, onSent, promise };
  }

  it("posts the file to the proxy and reports bytes", () => {
    const { onProgress } = start();
    const xhr = FakeXHR.last;

    xhr.progress(3, 10);

    expect(xhr.open).toHaveBeenCalledWith("POST", "/api/backend/documents");
    expect(xhr.sent?.get("files")).toBeInstanceOf(File);
    expect(onProgress).toHaveBeenCalledWith(3, 10);
  });

  it("says when all bytes are sent, then resolves with the file's result", async () => {
    const { onSent, promise } = start();

    FakeXHR.last.finish(202, { results: [{ filename: "a.pdf", status: "accepted", document_id: "d1", reason: null }] });

    expect(onSent).toHaveBeenCalled();
    await expect(promise).resolves.toMatchObject({ status: "accepted", document_id: "d1" });
  });

  it("rejects with the API's error", async () => {
    const { promise } = start();
    FakeXHR.last.finish(422, { detail: "no files" });
    await expect(promise).rejects.toMatchObject({ status: 422 });
  });

  it("rejects with status 0 on a network error", async () => {
    const { promise } = start();
    FakeXHR.last.onerror?.();
    await expect(promise).rejects.toMatchObject({ status: 0 });
  });
});

describe("runPool", () => {
  it("never runs more than the limit at once and runs everything", async () => {
    let active = 0;
    let peak = 0;
    const done: number[] = [];

    await runPool([1, 2, 3, 4, 5, 6, 7], 3, async (n) => {
      active += 1;
      peak = Math.max(peak, active);
      await new Promise((r) => setTimeout(r, 5));
      active -= 1;
      done.push(n);
    });

    expect(peak).toBe(3);
    expect(done.sort()).toEqual([1, 2, 3, 4, 5, 6, 7]);
  });
});
