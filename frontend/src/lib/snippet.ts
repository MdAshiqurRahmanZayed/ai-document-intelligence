export interface SnippetPart {
  text: string;
  mark: boolean;
}

// The API escapes everything from the document except its own <mark> tags, so what is left between
// the marks is entity-escaped text. It is decoded here only to be shown as text.
const ENTITIES: Record<string, string> = { "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'", "&#x27;": "'", "&amp;": "&" };
const decode = (text: string) => text.replace(/&(?:lt|gt|quot|amp|#39|#x27);/g, (entity) => ENTITIES[entity]);

/**
 * Splits a search snippet into plain text and highlighted words. Only `<mark>` is understood; any other
 * markup stays literal text, so the result is safe to render as React text nodes (never as HTML).
 */
export function snippetParts(snippet: string): SnippetPart[] {
  const parts: SnippetPart[] = [];
  const marked = /<mark>([\s\S]*?)<\/mark>/g;
  let last = 0;
  for (const match of snippet.matchAll(marked)) {
    if (match.index > last) parts.push({ text: decode(snippet.slice(last, match.index)), mark: false });
    parts.push({ text: decode(match[1]), mark: true });
    last = match.index + match[0].length;
  }
  if (last < snippet.length) parts.push({ text: decode(snippet.slice(last)), mark: false });
  return parts;
}
