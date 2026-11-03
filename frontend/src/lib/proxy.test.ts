import { describe, expect, it, vi } from "vitest";

import { forward, forwardFile, upstreamPath } from "./proxy";

const ENV = { url: "http://api:8000", key: "s3cret" };

function upstreamReturning(res: Response) {
  return vi.fn<typeof fetch>().mockResolvedValue(res);
}

function sentHeaders(fetchFn: ReturnType<typeof upstreamReturning>): Headers {
  return new Headers(fetchFn.mock.calls[0][1]?.headers);
}

describe("upstreamPath", () => {
  it.each([
    [["documents"], "/api/v1/documents"],
    [["documents", "abc", "invoices", "0"], "/api/v1/documents/abc/invoices/0"],
    [["search"], "/api/v1/search"],
    [["jobs", "retry-failed"], "/api/v1/jobs/retry-failed"],
    [["readyz"], "/readyz"],
  ])("allows %j", (segments, expected) => {
    expect(upstreamPath(segments)).toBe(expected);
  });

  it.each([[[]], [["admin"]], [["documents", ".."]], [["documents", "a/b"]], [["docs"]], [["healthz"]]])(
    "refuses %j",
    (segments) => {
      expect(upstreamPath(segments)).toBeNull();
    },
  );
});

describe("forward", () => {
  it("adds the API key on the server and keeps the query string", async () => {
    const fetchFn = upstreamReturning(Response.json({ items: [] }));

    const res = await forward(
      new Request("http://web/api/backend/documents?status=FAILED"),
      ["documents"],
      ENV,
      fetchFn,
    );

    expect(fetchFn.mock.calls[0][0]).toBe("http://api:8000/api/v1/documents?status=FAILED");
    expect(sentHeaders(fetchFn).get("x-api-key")).toBe("s3cret");
    expect(await res.json()).toEqual({ items: [] });
  });

  it("sends no key header when none is configured", async () => {
    const fetchFn = upstreamReturning(Response.json({}));

    await forward(new Request("http://web/x"), ["documents"], { url: ENV.url }, fetchFn);

    expect(sentHeaders(fetchFn).has("x-api-key")).toBe(false);
  });

  it("does not send the key to the readiness probe", async () => {
    const fetchFn = upstreamReturning(Response.json({ status: "ok" }));

    await forward(new Request("http://web/x"), ["readyz"], ENV, fetchFn);

    expect(fetchFn.mock.calls[0][0]).toBe("http://api:8000/readyz");
    expect(sentHeaders(fetchFn).has("x-api-key")).toBe(false);
  });

  it("passes API errors through with the same status and body", async () => {
    const body = { detail: { reason: "document_busy" } };
    const fetchFn = upstreamReturning(Response.json(body, { status: 409 }));

    const res = await forward(
      new Request("http://web/x", { method: "PATCH", body: "{}" }),
      ["documents", "1", "invoices", "0"],
      ENV,
      fetchFn,
    );

    expect(res.status).toBe(409);
    expect(await res.json()).toEqual(body);
  });

  it("forwards the request body and content type", async () => {
    const fetchFn = upstreamReturning(Response.json({}, { status: 202 }));

    await forward(
      new Request("http://web/x", {
        method: "POST",
        body: '{"from_stage":"extract"}',
        headers: { "content-type": "application/json" },
      }),
      ["documents", "1", "reprocess"],
      ENV,
      fetchFn,
    );

    const init = fetchFn.mock.calls[0][1];
    expect(init?.method).toBe("POST");
    expect(sentHeaders(fetchFn).get("content-type")).toBe("application/json");
    expect(init?.body).toBeTruthy();
  });

  it("answers 502 when the API cannot be reached", async () => {
    const fetchFn = vi.fn<typeof fetch>().mockRejectedValue(new Error("ECONNREFUSED api:8000"));

    const res = await forward(new Request("http://web/x"), ["documents"], ENV, fetchFn);

    expect(res.status).toBe(502);
    expect(JSON.stringify(await res.json())).not.toContain("ECONNREFUSED");
  });

  it("refuses paths and methods outside the allowed set without calling the API", async () => {
    const fetchFn = upstreamReturning(Response.json({}));

    const badPath = await forward(new Request("http://web/x"), ["admin"], ENV, fetchFn);
    const badMethod = await forward(
      new Request("http://web/x", { method: "DELETE" }),
      ["documents"],
      ENV,
      fetchFn,
    );

    expect(badPath.status).toBe(404);
    expect(badMethod.status).toBe(404);
    expect(fetchFn).not.toHaveBeenCalled();
  });

  it("returns only the content type from the API's headers", async () => {
    const fetchFn = upstreamReturning(
      new Response("{}", { headers: { "content-type": "application/json", "set-cookie": "a=b", "x-secret": "1" } }),
    );

    const res = await forward(new Request("http://web/x"), ["documents"], ENV, fetchFn);

    expect(res.headers.get("content-type")).toBe("application/json");
    expect(res.headers.has("set-cookie")).toBe(false);
    expect(res.headers.has("x-secret")).toBe(false);
  });
});

describe("forwardFile", () => {
  const ID = "3f2a1b4c-5d6e-4f70-8a9b-0c1d2e3f4a5b";
  const STORAGE = "http://storage:8333/raw/original.pdf?X-Amz-Signature=abc";

  function twoStep(file: Response, link: Response = Response.json({ url: STORAGE, expires_in: 300 })) {
    return vi.fn<typeof fetch>().mockResolvedValueOnce(link).mockResolvedValueOnce(file);
  }

  it("asks the API for the link with the key, then streams the file from storage", async () => {
    const fetchFn = twoStep(new Response("%PDF-1.7", { headers: { "content-type": "application/pdf", "content-length": "8" } }));

    const res = await forwardFile(new Request(`http://web/api/files/${ID}`), ID, ENV, fetchFn);

    expect(fetchFn.mock.calls[0][0]).toBe(`http://api:8000/api/v1/documents/${ID}/file`);
    expect(new Headers(fetchFn.mock.calls[0][1]?.headers).get("x-api-key")).toBe("s3cret");
    expect(fetchFn.mock.calls[1][0]).toBe(STORAGE);
    expect(new Headers(fetchFn.mock.calls[1][1]?.headers).has("x-api-key")).toBe(false);
    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toBe("application/pdf");
    expect(await res.text()).toBe("%PDF-1.7");
  });

  it("passes a Range request on and answers 206", async () => {
    const fetchFn = twoStep(new Response("PDF", { status: 206, headers: { "content-range": "bytes 0-2/100", "content-type": "application/pdf" } }));

    const res = await forwardFile(new Request("http://web/x", { headers: { range: "bytes=0-2" } }), ID, ENV, fetchFn);

    expect(new Headers(fetchFn.mock.calls[1][1]?.headers).get("range")).toBe("bytes=0-2");
    expect(res.status).toBe(206);
    expect(res.headers.get("content-range")).toBe("bytes 0-2/100");
  });

  it("marks uploaded content as never sniffed and sandboxed, inline or as a download", async () => {
    const inline = await forwardFile(new Request("http://web/x"), ID, ENV, twoStep(new Response("x")));
    const download = await forwardFile(new Request("http://web/x?download=1"), ID, ENV, twoStep(new Response("x")));

    expect(inline.headers.get("x-content-type-options")).toBe("nosniff");
    expect(inline.headers.get("content-security-policy")).toBe("sandbox");
    expect(inline.headers.get("content-disposition")).toBe("inline");
    expect(download.headers.get("content-disposition")).toBe("attachment");
  });

  it("refuses an id that is not a UUID without calling anything", async () => {
    const fetchFn = vi.fn<typeof fetch>();

    const res = await forwardFile(new Request("http://web/x"), "../../etc/passwd", ENV, fetchFn);

    expect(res.status).toBe(404);
    expect(fetchFn).not.toHaveBeenCalled();
  });

  it("answers 404 for an unknown document and 502 when the API or storage fail", async () => {
    const unknown = await forwardFile(new Request("http://web/x"), ID, ENV, vi.fn<typeof fetch>().mockResolvedValue(Response.json({}, { status: 404 })));
    const apiDown = await forwardFile(new Request("http://web/x"), ID, ENV, vi.fn<typeof fetch>().mockRejectedValue(new Error("down")));
    const storageDown = await forwardFile(new Request("http://web/x"), ID, ENV, vi.fn<typeof fetch>().mockResolvedValueOnce(Response.json({ url: STORAGE })).mockRejectedValueOnce(new Error("down")));
    const missing = await forwardFile(new Request("http://web/x"), ID, ENV, twoStep(new Response("", { status: 403 })));

    expect([unknown.status, apiDown.status, storageDown.status, missing.status]).toEqual([404, 502, 502, 502]);
  });
});
