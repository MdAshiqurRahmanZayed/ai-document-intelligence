// Forwards browser requests to the API and adds the secret key on the server.
// The key lives only in server environment variables; it is never sent to the browser.

export interface ProxyEnv {
  /** Base URL of the API as the web server reaches it (e.g. http://api:8000). */
  url: string;
  /** Shared secret for the API's X-API-Key header; unset means the API is open. */
  key?: string;
}

const API_RESOURCES = new Set(["documents", "search", "chat", "jobs", "cross-verify"]);
const SESSION_PATH = /^\/api\/v1\/chat\/sessions\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const SEGMENT = /^[A-Za-z0-9._~-]+$/;

/** Maps a path under /api/backend to the API path it may reach, or null when it may not. */
export function upstreamPath(segments: string[]): string | null {
  if (segments.length === 0 || !segments.every((s) => SEGMENT.test(s) && s !== "." && s !== "..")) {
    return null;
  }
  if (segments.length === 1 && segments[0] === "readyz") return "/readyz";
  if (!API_RESOURCES.has(segments[0])) return null;
  return `/api/v1/${segments.join("/")}`;
}

function json(status: number, detail: string): Response {
  return Response.json({ detail }, { status });
}

export async function forward(
  request: Request,
  segments: string[],
  env: ProxyEnv,
  fetchFn: typeof fetch = fetch,
): Promise<Response> {
  const path = upstreamPath(segments);
  // DELETE is allowed for one thing only: removing a chat session.
  const allowed = request.method === "DELETE" ? path !== null && SESSION_PATH.test(path) : ["GET", "POST", "PATCH"].includes(request.method);
  if (!path || !allowed) {
    return json(404, "Not found");
  }

  const headers = new Headers();
  for (const name of ["content-type", "accept"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  // The readiness probe is open on the API; every other call carries the key.
  if (env.key && path !== "/readyz") headers.set("x-api-key", env.key);

  const hasBody = request.method !== "GET" && request.body !== null;
  const init: RequestInit & { duplex?: "half" } = {
    method: request.method,
    headers,
    body: hasBody ? request.body : undefined,
    redirect: "manual",
    cache: "no-store",
    signal: request.signal,
  };
  // A streamed request body (large uploads) needs half-duplex mode.
  if (hasBody) init.duplex = "half";

  const search = new URL(request.url).search;
  let upstream: Response;
  try {
    upstream = await fetchFn(`${env.url.replace(/\/$/, "")}${path}${search}`, init);
  } catch {
    return json(502, "The API could not be reached");
  }

  // Only the status, body and content type go back (plus the no-buffering headers of a stream);
  // nothing else the API sent is copied.
  const out = new Headers();
  const type = upstream.headers.get("content-type");
  if (type) out.set("content-type", type);
  // An event stream (chat) must reach the browser as it is written, not when it ends.
  if (type?.startsWith("text/event-stream")) {
    out.set("cache-control", "no-cache, no-transform");
    out.set("x-accel-buffering", "no");
  }
  const empty = upstream.status === 204 || upstream.status === 304;
  return new Response(empty ? null : upstream.body, { status: upstream.status, headers: out });
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * Streams a stored original through the web server. The API gives a signed storage link that only the
 * server can reach (inside Compose the storage host is not resolvable from a browser) and that would
 * need CORS for the PDF viewer; fetching it here and answering from our own origin avoids both.
 * The link comes from the API, never from the client, so the client cannot choose what is fetched.
 */
export async function forwardFile(
  request: Request,
  id: string,
  env: ProxyEnv,
  fetchFn: typeof fetch = fetch,
): Promise<Response> {
  if (!UUID.test(id) || request.method !== "GET") return json(404, "Not found");

  const headers = new Headers();
  if (env.key) headers.set("x-api-key", env.key);
  let link: string;
  try {
    const res = await fetchFn(`${env.url.replace(/\/$/, "")}/api/v1/documents/${id}/file`, {
      headers,
      redirect: "manual",
      cache: "no-store",
    });
    if (res.status === 404) return json(404, "Not found");
    if (!res.ok) return json(502, "The API could not give a link to the file");
    link = ((await res.json()) as { url: string }).url;
  } catch {
    return json(502, "The API could not be reached");
  }

  // The viewer reads the PDF in ranges, so a Range request is passed on.
  const range = request.headers.get("range");
  let file: Response;
  try {
    file = await fetchFn(link, {
      headers: range ? { range } : undefined,
      redirect: "manual",
      cache: "no-store",
      signal: request.signal,
    });
  } catch {
    return json(502, "The file could not be read from storage");
  }
  if (!file.ok) return json(502, "The file could not be read from storage");

  const out = new Headers();
  for (const name of ["content-type", "content-length", "content-range", "accept-ranges"]) {
    const value = file.headers.get(name);
    if (value) out.set(name, value);
  }
  // Uploaded content is served from our origin: never sniffed, never allowed to run scripts.
  out.set("x-content-type-options", "nosniff");
  out.set("content-security-policy", "sandbox");
  out.set("content-disposition", new URL(request.url).searchParams.has("download") ? "attachment" : "inline");
  return new Response(file.body, { status: file.status, headers: out });
}
