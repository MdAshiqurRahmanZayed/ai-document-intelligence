"use client";

import { useEffect, useId, useState } from "react";

import type { ChatSource } from "@/lib/chatStream";
import { splitAnswer } from "@/lib/citations";

/** The answer as text, with each [n] shown as a numbered chip that reveals the quote of source n. */
export function AnswerText({
  text,
  sources,
  onActive,
}: {
  text: string;
  sources: ChatSource[];
  /** Told which source number a chip is pointing at (hover or focus), and null when none is. */
  onActive?: (n: number | null) => void;
}) {
  const known = new Set(sources.map((s) => s.n));
  return (
    <p className="leading-relaxed whitespace-pre-wrap">
      {splitAnswer(text, known).map((part, i) => {
        if (part.kind === "text") return <span key={i}>{part.text}</span>;
        const source = sources.find((s) => s.n === part.n);
        return source ? <CitationChip key={i} source={source} onActive={onActive} /> : null;
      })}
    </p>
  );
}

function CitationChip({ source, onActive }: { source: ChatSource; onActive?: (n: number | null) => void }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  useEffect(() => {
    onActive?.(open ? source.n : null);
    return () => onActive?.(null);
  }, [open, source.n, onActive]);
  return (
    <span className="relative mx-0.5 inline-block align-baseline">
      <button
        type="button"
        aria-describedby={open ? id : undefined}
        aria-label={`Source ${source.n}`}
        aria-expanded={open}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={() => setOpen((v) => !v)}
        className="rounded-full bg-indigo-100 px-1.5 text-xs font-semibold text-indigo-700 hover:bg-indigo-200 focus-visible:outline-2 focus-visible:outline-indigo-600 dark:bg-indigo-950 dark:text-indigo-300"
      >
        {source.n}
      </button>
      {open && (
        <span
          id={id}
          role="tooltip"
          className="absolute bottom-full left-0 z-10 mb-1 w-72 rounded-lg border border-zinc-200 bg-white p-2 text-xs font-normal whitespace-normal text-zinc-700 shadow-lg dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300"
        >
          <span className="block font-medium">
            {source.filename}, page {source.page_no}
          </span>
          {source.quote}
        </span>
      )}
    </span>
  );
}
