import { describe, expect, it } from "vitest";

import { filtersFromParams, filtersToParams, hasFilters } from "./filters";

describe("filters in the address", () => {
  it("round-trips the non-empty filters", () => {
    const filters = { status: "FAILED" as const, supplier: "acme", amount_min: "10" };
    const params = filtersToParams(filters);

    expect(params.toString()).toBe("status=FAILED&supplier=acme&amount_min=10");
    expect(filtersFromParams(params)).toEqual(filters);
  });

  it("ignores an unknown status and blank values", () => {
    const params = new URLSearchParams("status=BOGUS&supplier=%20&currency=eur");
    expect(filtersFromParams(params)).toEqual({ currency: "eur" });
  });

  it("keeps other parameters and replaces old filters", () => {
    const base = new URLSearchParams("q=freight&mode=keyword&status=FAILED");
    const params = filtersToParams({ supplier: "acme" }, base);

    expect(params.get("q")).toBe("freight");
    expect(params.get("mode")).toBe("keyword");
    expect(params.has("status")).toBe(false);
    expect(params.get("supplier")).toBe("acme");
  });

  it("knows when any filter is set", () => {
    expect(hasFilters({})).toBe(false);
    expect(hasFilters({ supplier: " " })).toBe(false);
    expect(hasFilters({ supplier: "a" })).toBe(true);
  });
});
