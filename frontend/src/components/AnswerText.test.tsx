import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { AnswerText } from "./AnswerText";
import type { ChatSource } from "@/lib/chatStream";

const source = (n: number, quote: string): ChatSource => ({ n, document_id: `d${n}`, filename: `f${n}.pdf`, page_no: n, quote });

describe("AnswerText", () => {
  it("shows a chip for a known marker and its quote on focus", async () => {
    render(<AnswerText text="Cirrus billed it [2]." sources={[source(1, "one"), source(2, "Hosting 4500 SEK")]} />);

    const chip = screen.getByRole("button", { name: "Source 2" });
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
    await userEvent.tab();

    expect(chip).toHaveFocus();
    expect(screen.getByRole("tooltip")).toHaveTextContent("Hosting 4500 SEK");
    expect(screen.getByRole("tooltip")).toHaveTextContent("f2.pdf, page 2");
  });

  it("shows the quote on hover and hides it again", async () => {
    render(<AnswerText text="x [1]" sources={[source(1, "the quote")]} />);

    await userEvent.hover(screen.getByRole("button", { name: "Source 1" }));
    expect(screen.getByRole("tooltip")).toHaveTextContent("the quote");
    await userEvent.unhover(screen.getByRole("button", { name: "Source 1" }));
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });

  it("shows no chip and no text for a marker without a source", () => {
    const { container } = render(<AnswerText text="Only [9] here." sources={[source(1, "q")]} />);

    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(container).toHaveTextContent("Only here.");
    expect(container).not.toHaveTextContent("[9]");
  });

  it("shows markup in an answer or a quote as text", async () => {
    const { container } = render(
      <AnswerText text="<img src=x onerror=alert(1)> [1]" sources={[source(1, "<script>alert(1)</script>")]} />,
    );

    await userEvent.hover(screen.getByRole("button", { name: "Source 1" }));

    expect(container.querySelector("img, script")).toBeNull();
    expect(container).toHaveTextContent("<img src=x onerror=alert(1)>");
    expect(screen.getByRole("tooltip")).toHaveTextContent("<script>alert(1)</script>");
  });
});
