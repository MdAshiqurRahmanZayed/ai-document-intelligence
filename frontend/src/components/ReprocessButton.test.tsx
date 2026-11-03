import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ReprocessButton } from "./ReprocessButton";
import { renderWithClient, stubApi } from "@/test/helpers";

afterEach(() => vi.unstubAllGlobals());

describe("ReprocessButton", () => {
  it.each(["FAILED", "NEEDS_REVIEW", "COMPLETED"] as const)("is offered for %s documents", (status) => {
    renderWithClient(<ReprocessButton id="d1" status={status} />);
    expect(screen.getByRole("button", { name: "Reprocess" })).toBeInTheDocument();
  });

  it.each(["UPLOADED", "QUEUED", "PROCESSING"] as const)("is not offered while a document is %s", (status) => {
    renderWithClient(<ReprocessButton id="d1" status={status} />);
    expect(screen.queryByRole("button", { name: "Reprocess" })).toBeNull();
  });

  it("asks for confirmation, warns about corrections, and sends the chosen start", async () => {
    const { calls } = stubApi({ "/reprocess": { document_id: "d1", status: "QUEUED", from_stage: "extract" } });
    renderWithClient(<ReprocessButton id="d1" status="FAILED" />);

    await userEvent.click(screen.getByRole("button", { name: "Reprocess" }));
    expect(screen.getByRole("dialog")).toHaveTextContent(/manual corrections stay in the history but stop being current/);
    expect(calls).toHaveLength(0);

    await userEvent.click(screen.getByRole("radio", { name: /Extraction only/ }));
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Reprocess" }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0]).toMatchObject({ url: "/api/backend/documents/d1/reprocess", method: "POST", body: { from_stage: "extract" } });
    expect(await screen.findByText("Queued for processing again.")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("sends nothing when cancelled", async () => {
    const { calls } = stubApi({});
    renderWithClient(<ReprocessButton id="d1" status="FAILED" />);

    await userEvent.click(screen.getByRole("button", { name: "Reprocess" }));
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(calls).toHaveLength(0);
  });

  it.each([
    ["extraction_disabled", /no Google API key/],
    ["no_text", /no readable text/],
    ["already_queued", /already queued/],
  ])("explains the %s answer and keeps the dialog open", async (reason, message) => {
    stubApi({ "/reprocess": { status: 409, body: { detail: { reason } } } });
    renderWithClient(<ReprocessButton id="d1" status="COMPLETED" />);

    await userEvent.click(screen.getByRole("button", { name: "Reprocess" }));
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Reprocess" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});
