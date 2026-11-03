import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, api, parseError, toQuery } from "./api";
import { ERROR_CODES, FINDING_TITLES, REASONS, errorMessage, findingTitle } from "./messages";

afterEach(() => vi.unstubAllGlobals());

describe("parseError", () => {
  it("reads a plain string detail", () => {
    const e = parseError(401, { detail: "Invalid or missing API key" });
    expect(e).toMatchObject({ status: 401, message: "Invalid or missing API key", reason: null });
  });

  it("reads a reason", () => {
    const e = parseError(409, { detail: { reason: "document_busy" } });
    expect(e).toMatchObject({ status: 409, reason: "document_busy" });
  });

  it("reads a field and message", () => {
    const e = parseError(422, { detail: { field: "total", message: "not a number" } });
    expect(e).toMatchObject({ status: 422, field: "total", message: "not a number" });
  });

  it("reads FastAPI's validation list", () => {
    const e = parseError(422, { detail: [{ loc: ["query", "limit"], msg: "too big" }] });
    expect(e).toMatchObject({ field: "limit", message: "too big" });
  });

  it("copes with a missing body", () => {
    expect(parseError(500, null).message).toBe("HTTP 500");
  });
});

describe("toQuery", () => {
  it("drops empty values", () => {
    expect(toQuery({ a: "x", b: "", c: undefined, d: " ", e: 5 })).toBe("?a=x&e=5");
    expect(toQuery({})).toBe("");
  });
});

describe("requests", () => {
  function stub(body: unknown, status = 200) {
    const fn = vi.fn().mockResolvedValue(Response.json(body, { status }));
    vi.stubGlobal("fetch", fn);
    return fn;
  }

  it("lists documents through the proxy with filters and cursor", async () => {
    const fn = stub({ items: [], next_cursor: null });

    await api.listDocuments({ status: "FAILED", supplier: "acme" }, "abc");

    expect(fn.mock.calls[0][0]).toBe("/api/backend/documents?status=FAILED&supplier=acme&cursor=abc&limit=20");
  });

  it("sends only the given fields when correcting", async () => {
    const fn = stub({});

    await api.correctInvoice("d1", 0, { total: "120.00" }, "Maria");

    const [url, init] = fn.mock.calls[0];
    expect(url).toBe("/api/backend/documents/d1/invoices/0");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body)).toEqual({ fields: { total: "120.00" }, edited_by: "Maria" });
  });

  it("throws an ApiError carrying the reason", async () => {
    stub({ detail: { reason: "document_busy" } }, 409);

    await expect(api.reprocess("d1", "ingest")).rejects.toMatchObject({ status: 409, reason: "document_busy" });
  });

  it("turns a network failure into an ApiError with status 0", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("failed")));

    await expect(api.getDocument("d1")).rejects.toMatchObject({ status: 0 });
  });
});

describe("messages", () => {
  const apiDoc = readFileSync(resolve(__dirname, "../../../docs/api.md"), "utf-8");

  function codesIn(section: string): string[] {
    const start = apiDoc.indexOf(section);
    const rest = apiDoc.slice(start + section.length);
    const end = rest.search(/\n###? /);
    const table = rest.slice(0, end === -1 ? undefined : end);
    // The header cell of the reason table is also backticked; it is not a code.
    return [...table.matchAll(/^\| `([a-z_]+)`/gm)].map((m) => m[1]).filter((c) => c !== "reason");
  }

  it("has a title for every finding code in docs/api.md", () => {
    const codes = codesIn("### Validation findings");
    expect(codes.length).toBeGreaterThan(10);
    for (const code of codes) expect(FINDING_TITLES[code], code).toBeDefined();
  });

  it("has a sentence for every document error code in docs/api.md", () => {
    const codes = codesIn("### Document error codes (`error_code`)");
    expect(codes.length).toBeGreaterThan(5);
    for (const code of codes) expect(ERROR_CODES[code], code).toBeDefined();
  });

  it("has a sentence for every upload rejection reason in docs/api.md", () => {
    const codes = codesIn("### Rejection reasons (`status: \"rejected\"`)");
    expect(codes.length).toBe(5);
    for (const code of codes) expect(REASONS[code], code).toBeDefined();
  });

  it("explains a known reason and never shows the raw code", () => {
    const text = errorMessage(new ApiError(409, "x", "document_busy"));
    expect(text).toMatch(/still being processed/);
    expect(text).not.toMatch(/document_busy/);
  });

  it("falls back to a generic message with the status", () => {
    expect(errorMessage(new ApiError(418, "teapot"))).toBe("Request failed (418).");
    expect(errorMessage(new Error("boom"))).toBe("Something went wrong. Try again.");
  });

  it("names the field message for a 422", () => {
    expect(errorMessage(new ApiError(422, "not a number", null, "total"))).toBe("not a number");
  });

  it("makes a readable title for an unknown finding", () => {
    expect(findingTitle("brand_new_code")).toBe("brand new code");
  });
});
