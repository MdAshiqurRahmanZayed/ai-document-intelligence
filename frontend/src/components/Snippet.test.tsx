import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Snippet } from "./Snippet";

describe("Snippet", () => {
  it("highlights marked words as mark elements", () => {
    render(<Snippet snippet="due in <mark>thirty</mark> days" />);
    expect(screen.getByText("thirty").tagName).toBe("MARK");
  });

  it("shows a script from the document as text and runs nothing", () => {
    const { container } = render(<Snippet snippet="&lt;script&gt;alert(1)&lt;/script&gt; around <mark>freight</mark>" />);

    expect(container.querySelector("script")).toBeNull();
    expect(container).toHaveTextContent("<script>alert(1)</script> around freight");
    expect(screen.getByText("freight").tagName).toBe("MARK");
  });

  it("does not turn raw markup into elements even if the API sent it unescaped", () => {
    const { container } = render(<Snippet snippet={'<img src=x onerror="alert(1)"> <mark>hit</mark>'} />);

    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelectorAll("mark")).toHaveLength(1);
  });
});
