import { snippetParts } from "@/lib/snippet";

/** A search snippet with the matched words highlighted. Built from text nodes, never injected as HTML. */
export function Snippet({ snippet }: { snippet: string }) {
  return (
    <p className="text-sm text-zinc-600 dark:text-zinc-400">
      {snippetParts(snippet).map((part, i) =>
        part.mark ? (
          <mark key={i} className="rounded bg-yellow-200 px-0.5 text-zinc-900 dark:bg-yellow-500/40 dark:text-zinc-50">
            {part.text}
          </mark>
        ) : (
          <span key={i}>{part.text}</span>
        ),
      )}
    </p>
  );
}
