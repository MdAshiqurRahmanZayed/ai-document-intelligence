"use client";

import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRef, useState } from "react";
import { useDropzone } from "react-dropzone";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Progress } from "@/components/ui/Progress";
import { Spinner } from "@/components/ui/Spinner";
import { cn } from "@/lib/cn";
import { formatBytes } from "@/lib/format";
import { errorMessage, reasonMessage } from "@/lib/messages";
import type { UploadResult } from "@/lib/types";
import { checkFile, runPool, UPLOAD_CONCURRENCY, uploadFile, type Uploader } from "@/lib/upload";

type Phase = "ready" | "sending" | "waiting" | "done" | "failed";

interface Item {
  id: number;
  file: File;
  /** Reason code when the browser already knows the file cannot be sent. */
  refused: string | null;
  phase: Phase;
  loaded: number;
  result?: UploadResult;
  error?: unknown;
}

let nextId = 1;

export function UploadForm({ upload = uploadFile }: { upload?: Uploader }) {
  const queryClient = useQueryClient();
  const [items, setItems] = useState<Item[]>([]);
  const [sending, setSending] = useState(false);
  const busy = useRef(false);

  const patch = (id: number, change: Partial<Item>) =>
    setItems((all) => all.map((item) => (item.id === id ? { ...item, ...change } : item)));

  const { getRootProps, getInputProps, isDragActive, open } = useDropzone({
    noClick: true,
    onDrop: (files) =>
      setItems((all) => [
        ...all,
        ...files.map((file) => ({
          id: nextId++,
          file,
          refused: checkFile(file),
          phase: "ready" as Phase,
          loaded: 0,
        })),
      ]),
  });

  const sendable = items.filter((i) => !i.refused && (i.phase === "ready" || i.phase === "failed"));

  async function send() {
    if (busy.current || sendable.length === 0) return;
    busy.current = true;
    setSending(true);
    await runPool(sendable, UPLOAD_CONCURRENCY, async (item) => {
      patch(item.id, { phase: "sending", loaded: 0, error: undefined });
      try {
        const result = await upload(item.file, {
          onProgress: (loaded) => patch(item.id, { loaded }),
          onSent: () => patch(item.id, { phase: "waiting", loaded: item.file.size }),
        });
        patch(item.id, { phase: "done", result, loaded: item.file.size });
      } catch (error) {
        patch(item.id, { phase: "failed", error });
      }
    });
    busy.current = false;
    setSending(false);
    queryClient.invalidateQueries({ queryKey: ["documents"] });
  }

  const inFlight = items.filter((i) => !i.refused && i.phase !== "ready");
  const totalBytes = inFlight.reduce((sum, i) => sum + i.file.size, 0);
  const sentBytes = inFlight.reduce((sum, i) => sum + (i.phase === "done" || i.phase === "waiting" ? i.file.size : i.loaded), 0);
  const overall = totalBytes ? (sentBytes / totalBytes) * 100 : 0;

  return (
    <div className="flex flex-col gap-6">
      <div
        {...getRootProps()}
        className={cn(
          "flex flex-col items-center gap-3 rounded-2xl border-2 border-dashed px-6 py-14 text-center transition-colors",
          isDragActive
            ? "border-indigo-500 bg-indigo-50 dark:bg-indigo-950/40"
            : "border-zinc-300 bg-white dark:border-zinc-700 dark:bg-zinc-900",
        )}
      >
        <input {...getInputProps()} aria-label="Choose files" />
        <div className="grid h-12 w-12 place-items-center rounded-full bg-indigo-100 text-xl text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300" aria-hidden>
          ↑
        </div>
        <p className="font-medium">{isDragActive ? "Drop to add the files" : "Drag invoices and receipts here"}</p>
        <p className="text-sm text-zinc-500">PDF, JPG, PNG, TIFF, XLSX, XLS or CSV, up to 100 MB each</p>
        <Button variant="secondary" onClick={open} disabled={sending}>
          Browse files
        </Button>
      </div>

      {items.length > 0 && (
        <Card className="flex flex-col gap-4">
          <div className="flex items-center justify-between gap-4">
            <h2 className="font-semibold">
              {items.length} {items.length === 1 ? "file" : "files"}
            </h2>
            <div className="flex gap-2">
              <Button variant="ghost" size="sm" disabled={sending} onClick={() => setItems((all) => all.filter((i) => i.phase !== "done" && !i.refused))}>
                Clear finished
              </Button>
              <Button onClick={send} loading={sending} disabled={sendable.length === 0}>
                Upload {sendable.length || ""} {sendable.length === 1 ? "file" : "files"}
              </Button>
            </div>
          </div>

          {inFlight.length > 0 && (
            <div className="flex flex-col gap-1">
              <div className="flex justify-between text-xs text-zinc-500">
                <span>Overall</span>
                <span>{Math.round(overall)}%</span>
              </div>
              <Progress value={overall} label="Overall upload" tone={overall >= 100 && !sending ? "green" : "indigo"} />
            </div>
          )}

          <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {items.map((item) => (
              <FileRow key={item.id} item={item} locked={sending} onRemove={() => setItems((all) => all.filter((i) => i.id !== item.id))} />
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

function FileRow({ item, locked, onRemove }: { item: Item; locked: boolean; onRemove: () => void }) {
  const pct = item.file.size ? Math.round((item.loaded / item.file.size) * 100) : 0;

  return (
    <li className="flex flex-col gap-2 py-3">
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          <p className="truncate font-medium">{item.file.name}</p>
          <p className="text-xs text-zinc-500">{formatBytes(item.file.size)}</p>
        </div>
        <div className="flex shrink-0 items-center gap-3 text-sm">
          <RowStatus item={item} pct={pct} />
          {item.phase !== "sending" && item.phase !== "waiting" && (
            <button type="button" aria-label={`Remove ${item.file.name}`} disabled={locked} onClick={onRemove} className="text-zinc-400 hover:text-zinc-700 disabled:opacity-40">
              ×
            </button>
          )}
        </div>
      </div>
      {(item.phase === "sending" || item.phase === "waiting") && (
        <Progress value={item.phase === "waiting" ? 100 : pct} label={`Upload of ${item.file.name}`} />
      )}
    </li>
  );
}

function RowStatus({ item, pct }: { item: Item; pct: number }) {
  if (item.refused) {
    return <span className="text-red-600 dark:text-red-400">Refused: {reasonMessage(item.refused)}</span>;
  }
  switch (item.phase) {
    case "sending":
      return <span className="tabular-nums text-indigo-700 dark:text-indigo-300">{pct}%</span>;
    case "waiting":
      return (
        <span className="inline-flex items-center gap-2 text-indigo-700 dark:text-indigo-300">
          <Spinner label="Processing on server" /> 100% sent, processing on server
        </span>
      );
    case "failed":
      return <span className="text-red-600 dark:text-red-400">Failed: {errorMessage(item.error)}</span>;
    case "done":
      return <ResultStatus result={item.result!} />;
    default:
      return <span className="text-zinc-500">Ready</span>;
  }
}

function ResultStatus({ result }: { result: UploadResult }) {
  if (result.status === "rejected") {
    return <span className="text-red-600 dark:text-red-400">Rejected: {reasonMessage(result.reason) ?? "not accepted"}</span>;
  }
  return (
    <span className="inline-flex items-center gap-2">
      <span className={result.status === "accepted" ? "text-emerald-700 dark:text-emerald-400" : "text-amber-700 dark:text-amber-400"}>
        {result.status === "accepted" ? "Accepted" : "Already uploaded"}
      </span>
      {result.document_id && (
        <Link href={`/documents/${result.document_id}`} className="font-medium text-indigo-600 hover:underline">
          View
        </Link>
      )}
    </span>
  );
}
