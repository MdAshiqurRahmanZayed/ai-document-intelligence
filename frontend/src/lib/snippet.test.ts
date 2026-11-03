import { describe, expect, it } from "vitest";

import { snippetParts } from "./snippet";

describe("snippetParts", () => {
  it("splits text and highlighted words", () => {
    expect(snippetParts("… <mark>Payment</mark> is due within <mark>thirty</mark> days …")).toEqual([
      { text: "… ", mark: false },
      { text: "Payment", mark: true },
      { text: " is due within ", mark: false },
      { text: "thirty", mark: true },
      { text: " days …", mark: false },
    ]);
  });

  it("decodes the API's escaping so markup shows as the text it is", () => {
    expect(snippetParts("&lt;b&gt;Tom &amp; Jerry&lt;/b&gt; <mark>won</mark>")).toEqual([
      { text: "<b>Tom & Jerry</b> ", mark: false },
      { text: "won", mark: true },
    ]);
  });

  it("keeps any other markup literal", () => {
    expect(snippetParts("<script>alert(1)</script> <mark>x</mark>")).toEqual([
      { text: "<script>alert(1)</script> ", mark: false },
      { text: "x", mark: true },
    ]);
  });

  it("handles plain text and the empty string", () => {
    expect(snippetParts("nothing marked")).toEqual([{ text: "nothing marked", mark: false }]);
    expect(snippetParts("")).toEqual([]);
  });
});
