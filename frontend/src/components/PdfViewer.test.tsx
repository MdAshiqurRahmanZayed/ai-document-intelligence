import { render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import PdfViewer from "./PdfViewer";

// pdf.js needs a browser worker, so react-pdf is replaced. The fake Document behaves like the real one
// for a locked file: it asks for a password (onPassword) instead of loading.
let locked = true;
vi.mock("react-pdf", () => ({
  pdfjs: { GlobalWorkerOptions: {} },
  Document: ({ children, onPassword, onLoadSuccess }: { children: ReactNode; onPassword: () => void; onLoadSuccess: (p: { numPages: number }) => void }) => {
    // Called after render, as pdf.js does once it has read the file header.
    queueMicrotask(() => (locked ? onPassword() : onLoadSuccess({ numPages: 3 })));
    return <div data-testid="document">{children}</div>;
  },
  Page: ({ pageNumber }: { pageNumber: number }) => <div data-testid="page">page {pageNumber}</div>,
}));

beforeAll(() => {
  vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} unobserve() {} });
});
afterEach(() => vi.restoreAllMocks());

describe("PdfViewer", () => {
  it("says a password-protected PDF cannot be previewed, without a browser password prompt", async () => {
    locked = true;
    const prompt = vi.spyOn(window, "prompt");
    render(<PdfViewer src="/api/files/x" />);

    expect(await screen.findByRole("alert")).toHaveTextContent(/password-protected/i);
    expect(prompt).not.toHaveBeenCalled();
    expect(screen.queryByTestId("document")).toBeNull();
    expect(screen.queryByRole("button", { name: "Next" })).toBeNull();
  });

  it("shows the pages with Previous and Next for a normal PDF", async () => {
    locked = false;
    render(<PdfViewer src="/api/files/x" />);

    await waitFor(() => expect(screen.getByText("Page 1 of 3")).toBeInTheDocument());
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Next" })).toBeEnabled();
  });
});
