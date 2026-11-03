"use client";

import dynamic from "next/dynamic";

import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { formatBytes } from "@/lib/format";
import type { DocumentDetail } from "@/lib/types";

// pdf.js needs the browser, so the viewer is loaded only there and only when a PDF is opened.
const PdfViewer = dynamic(() => import("./PdfViewer"), {
  ssr: false,
  loading: () => (
    <div className="grid min-h-48 place-items-center">
      <Spinner label="Loading the viewer" />
    </div>
  ),
});

const fileUrl = (id: string, download = false) => `/api/files/${id}${download ? "?download=1" : ""}`;

/** The original next to the result: a PDF viewer, an image, or a download for what a browser cannot show. */
export function FileViewer({ doc }: { doc: Pick<DocumentDetail, "id" | "filename" | "mime" | "size" | "source_type"> }) {
  const isPdf = doc.mime === "application/pdf" || doc.source_type === "pdf";
  // Browsers other than Safari cannot draw TIFF, so it is offered as a download.
  const isImage = doc.mime.startsWith("image/") && doc.mime !== "image/tiff";

  return (
    <Card className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-3">
        <h2 className="font-semibold">Original</h2>
        <a href={fileUrl(doc.id, true)} className="text-sm font-medium text-indigo-600 hover:underline">
          Download ({formatBytes(doc.size)})
        </a>
      </div>
      {isPdf ? (
        <PdfViewer src={fileUrl(doc.id)} />
      ) : isImage ? (
        // eslint-disable-next-line @next/next/no-img-element -- a stored original streamed from our own route, not an optimisable asset
        <img src={fileUrl(doc.id)} alt={`Scan of ${doc.filename}`} className="w-full rounded-lg border border-zinc-200 dark:border-zinc-800" />
      ) : (
        <p className="rounded-lg bg-zinc-50 p-4 text-sm text-zinc-600 dark:bg-zinc-950 dark:text-zinc-400">
          This file type cannot be previewed in the browser. Download it to open it; the extracted values are shown beside it.
        </p>
      )}
    </Card>
  );
}
