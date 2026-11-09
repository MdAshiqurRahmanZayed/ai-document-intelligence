import { describe, expect, it } from "vitest";

import { splitAnswer } from "./citations";

describe("splitAnswer", () => {
  it("turns a marker that names a source into a citation", () => {
    expect(splitAnswer("Cirrus [2] billed it.", new Set([1, 2]))).toEqual([
      { kind: "text", text: "Cirrus " },
      { kind: "cite", n: 2 },
      { kind: "text", text: " billed it." },
    ]);
  });

  it("drops a marker that names no source", () => {
    expect(splitAnswer("A [9] B", new Set([1]))).toEqual([
      { kind: "text", text: "A " },
      { kind: "text", text: " B" },
    ]);
  });

  it("handles adjacent markers and a marker at either end", () => {
    expect(splitAnswer("[1][2]", new Set([1, 2]))).toEqual([
      { kind: "cite", n: 1 },
      { kind: "cite", n: 2 },
    ]);
  });

  it("leaves text without markers alone, including other brackets", () => {
    expect(splitAnswer("Total [EUR] 12", new Set([1]))).toEqual([{ kind: "text", text: "Total [EUR] 12" }]);
  });
});
