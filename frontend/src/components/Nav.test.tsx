import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Nav } from "./Nav";
import { renderWithClient, stubApi } from "@/test/helpers";

const pathname = vi.hoisted(() => ({ value: "/chat" }));
vi.mock("next/navigation", () => ({ usePathname: () => pathname.value }));

afterEach(() => vi.unstubAllGlobals());

describe("Nav", () => {
  it("has a Chat link that is the current page on /chat", () => {
    stubApi({ "/readyz": { status: "ok", checks: {} } });
    renderWithClient(<Nav />);

    const chat = screen.getByRole("link", { name: "Chat" });
    expect(chat).toHaveAttribute("href", "/chat");
    expect(chat).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Search" })).not.toHaveAttribute("aria-current");
  });

  it("does not mark Chat as current elsewhere", () => {
    pathname.value = "/search";
    stubApi({ "/readyz": { status: "ok", checks: {} } });
    renderWithClient(<Nav />);

    expect(screen.getByRole("link", { name: "Chat" })).not.toHaveAttribute("aria-current");
    pathname.value = "/chat";
  });
});
