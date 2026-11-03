import { API_BASE, ApiError, parseError } from "./api";
import type { UploadResult } from "./types";

export const ALLOWED_EXTENSIONS = ["pdf", "jpg", "jpeg", "png", "tif", "tiff", "xlsx", "xls", "csv"];
/** The API's per-file limit (MAX_UPLOAD_MB, default 100). The API stays the authority. */
export const MAX_UPLOAD_BYTES = 100 * 1024 * 1024;
/** Files sent at the same time. */
export const UPLOAD_CONCURRENCY = 3;

/** Why a file cannot be sent (a reason code the messages table knows), or null when it can. */
export function checkFile(file: { name: string; size: number }): string | null {
  if (file.size === 0) return "empty_file";
  if (file.size > MAX_UPLOAD_BYTES) return "file_too_large";
  const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
  return ALLOWED_EXTENSIONS.includes(ext) ? null : "unsupported_type";
}

export interface UploadHooks {
  /** Bytes of the file sent so far. */
  onProgress: (loaded: number, total: number) => void;
  /** All bytes are sent; the server is still storing the file and answering. */
  onSent: () => void;
}

export type Uploader = (file: File, hooks: UploadHooks) => Promise<UploadResult>;

/** One file per request, so each has its own percentage and result. fetch cannot report upload bytes, XHR can. */
export const uploadFile: Uploader = (file, { onProgress, onSent }) =>
  new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}/documents`);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(event.loaded, event.total);
    };
    xhr.upload.onload = () => onSent();
    xhr.onerror = () => reject(new ApiError(0, "Network error"));
    xhr.onload = () => {
      let body: unknown = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        // not JSON: handled below
      }
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(parseError(xhr.status, body));
        return;
      }
      const result = (body as { results?: UploadResult[] } | null)?.results?.[0];
      if (result) resolve(result);
      else reject(new ApiError(xhr.status, "Unexpected response"));
    };
    const form = new FormData();
    form.append("files", file);
    xhr.send(form);
  });

/** Runs `task` over `items`, at most `limit` at a time. Failures are the task's to handle. */
export async function runPool<T>(items: T[], limit: number, task: (item: T) => Promise<void>): Promise<void> {
  const queue = [...items];
  const worker = async () => {
    for (let item = queue.shift(); item !== undefined; item = queue.shift()) await task(item);
  };
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker));
}
