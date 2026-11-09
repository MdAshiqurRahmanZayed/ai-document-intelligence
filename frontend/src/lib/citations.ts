export type AnswerPart = { kind: "text"; text: string } | { kind: "cite"; n: number };

const MARKER = /\[(\d+)\]/g;

/**
 * The answer as text and citation markers. A marker that names a source is a citation; one that does
 * not (the model invented a number) is dropped, so it never shows as text or as a chip.
 */
export function splitAnswer(text: string, known: ReadonlySet<number>): AnswerPart[] {
  const parts: AnswerPart[] = [];
  let last = 0;
  const addText = (value: string) => {
    if (value) parts.push({ kind: "text", text: value });
  };
  for (const match of text.matchAll(MARKER)) {
    addText(text.slice(last, match.index));
    const n = Number(match[1]);
    if (known.has(n)) parts.push({ kind: "cite", n });
    last = match.index + match[0].length;
  }
  addText(text.slice(last));
  return parts;
}
