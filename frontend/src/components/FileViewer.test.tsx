import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { FileViewer } from "./FileViewer";

vi.mock("next/dynamic", () => ({ default: () => ({ src }: { src: string }) => <div data-testid="pdf-viewer" data-src={src} /> }));

const base = { id: "3f2a1b4c-5d6e-4f70-8a9b-0c1d2e3f4a5b", filename: "f", size: 2048 };

describe("FileViewer", () => {
  it("shows a PDF in the viewer, streamed from our own route", () => {
    render(<FileViewer doc={{ ...base, mime: "application/pdf", source_type: "pdf" }} />);
    expect(screen.getByTestId("pdf-viewer")).toHaveAttribute("data-src", `/api/files/${base.id}`);
  });

  it("shows an image as an image", () => {
    render(<FileViewer doc={{ ...base, filename: "scan.png", mime: "image/png", source_type: "image" }} />);
    expect(screen.getByRole("img", { name: "Scan of scan.png" })).toHaveAttribute("src", `/api/files/${base.id}`);
  });

  it("offers TIFF and spreadsheets as a download instead of a preview", () => {
    const { rerender } = render(<FileViewer doc={{ ...base, mime: "image/tiff", source_type: "image" }} />);
    expect(screen.queryByRole("img")).toBeNull();
    expect(screen.getByText(/cannot be previewed/)).toBeInTheDocument();

    rerender(<FileViewer doc={{ ...base, mime: "text/csv", source_type: "spreadsheet" }} />);
    expect(screen.getByText(/cannot be previewed/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Download/ })).toHaveAttribute("href", `/api/files/${base.id}?download=1`);
  });
});
