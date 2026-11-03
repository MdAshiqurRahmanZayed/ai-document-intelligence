"use client";

import { useEffect, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";

// The worker must be set in the module that renders the pages (see react-pdf's README).
pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();

/** One page at a time with previous and next, so a 1000-page PDF costs one canvas, not a thousand. */
export default function PdfViewer({ src }: { src: string }) {
  const [pages, setPages] = useState(0);
  const [page, setPage] = useState(1);
  const [width, setWidth] = useState(560);
  // A password-protected PDF makes pdf.js ask for a password with a browser prompt by default; the system cannot open
  // these, so the viewer says so instead and never supplies one.
  const [locked, setLocked] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(240, Math.floor(entry.contentRect.width))));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <div className="flex flex-col gap-3">
      <div ref={box} className="overflow-hidden rounded-lg border border-zinc-200 bg-zinc-100 dark:border-zinc-800 dark:bg-zinc-950">
        {locked ? (
          <ViewerMessage>
            <p role="alert" className="max-w-xs text-center">
              This PDF is password-protected, so it cannot be previewed or read. Remove the password and upload it again.
            </p>
          </ViewerMessage>
        ) : (
          <Document
            file={src}
            suspense={false}
            onPassword={() => setLocked(true)}
            onLoadSuccess={({ numPages }) => setPages(numPages)}
            loading={<ViewerMessage><Spinner label="Loading the PDF" /></ViewerMessage>}
            error={<ViewerMessage>The PDF could not be displayed. Download it instead.</ViewerMessage>}
          >
            <Page pageNumber={page} width={width} loading={<ViewerMessage><Spinner label="Loading the page" /></ViewerMessage>} />
          </Document>
        )}
      </div>
      {pages > 0 && (
        <div className="flex items-center justify-between gap-2 text-sm">
          <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
            Previous
          </Button>
          <span aria-live="polite">
            Page {page} of {pages}
          </span>
          <Button variant="secondary" size="sm" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>
            Next
          </Button>
        </div>
      )}
    </div>
  );
}

function ViewerMessage({ children }: { children: React.ReactNode }) {
  return <div className="grid min-h-48 place-items-center p-6 text-sm text-zinc-500">{children}</div>;
}
