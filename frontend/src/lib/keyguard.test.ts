import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, resolve } from "node:path";

import { describe, expect, it } from "vitest";

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sources(path);
    return /\.(ts|tsx)$/.test(name) && !/\.test\./.test(name) ? [path] : [];
  });
}

describe("API key stays on the server", () => {
  const src = resolve(__dirname, "..");
  const files = sources(src);

  it("is read only by the two server route handlers (the API proxy and the file stream)", () => {
    const readers = files.filter((f) => /process\.env\.API_KEY/.test(readFileSync(f, "utf-8")));
    expect(readers.map((f) => f.slice(src.length)).sort()).toEqual(["/app/api/backend/[...path]/route.ts", "/app/api/files/[id]/route.ts"]);
  });

  it("is never exposed through a NEXT_PUBLIC variable", () => {
    const leaks = files.filter((f) => /NEXT_PUBLIC_\w*KEY/.test(readFileSync(f, "utf-8")));
    expect(leaks).toEqual([]);
  });
});
