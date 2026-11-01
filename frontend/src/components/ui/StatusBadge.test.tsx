import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it.each(["ok", "error", "loading"] as const)("renders the %s variant", (status) => {
    render(<StatusBadge label="redis" status={status} />);

    expect(screen.getByText("redis").getAttribute("data-status")).toBe(status);
    expect(screen.getByText(status)).toBeTruthy();
  });
});
