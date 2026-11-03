import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { UploadForm } from "./UploadForm";
import type { UploadResult } from "@/lib/types";
import type { Uploader } from "@/lib/upload";

function renderForm(upload: Uploader) {
  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>
      <UploadForm upload={upload} />
    </QueryClientProvider>,
  );
}

function drop(...files: File[]) {
  const input = screen.getByLabelText("Choose files");
  fireEvent.change(input, { target: { files } });
}

const file = (name: string, size = 10) => new File([new Uint8Array(size)], name);
const accepted = (name: string, id = "d1"): UploadResult => ({ filename: name, status: "accepted", document_id: id, reason: null });

describe("UploadForm", () => {
  it("lists dropped files with name and size, and removes one", async () => {
    renderForm(vi.fn());
    drop(file("a.pdf", 2048), file("b.csv"), file("c.png"));

    expect(await screen.findByText("a.pdf")).toBeInTheDocument();
    expect(screen.getByText("2.0 KB")).toBeInTheDocument();
    expect(screen.getByText("3 files")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Remove b.csv" }));
    expect(screen.getByText("2 files")).toBeInTheDocument();
    expect(screen.queryByText("b.csv")).toBeNull();
  });

  it("refuses an unsupported file with a reason and sends only the valid ones", async () => {
    const upload = vi.fn<Uploader>().mockImplementation(async (f) => accepted(f.name));
    renderForm(upload);
    drop(file("notes.docx"), file("a.pdf"), file("b.csv"));

    expect(await screen.findByText(/This file type is not supported/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /^Upload 2 files/ }));

    await waitFor(() => expect(upload).toHaveBeenCalledTimes(2));
    expect(upload.mock.calls.map(([f]) => f.name).sort()).toEqual(["a.pdf", "b.csv"]);
  });

  it("refuses an empty file", async () => {
    renderForm(vi.fn());
    drop(new File([], "empty.pdf"));
    expect(await screen.findByText(/The file is empty/)).toBeInTheDocument();
  });

  it("shows percentages, then 'processing on server', then the result", async () => {
    let hooks!: Parameters<Uploader>[1];
    let finish!: (r: UploadResult) => void;
    const upload: Uploader = (_f, h) => {
      hooks = h;
      return new Promise((resolve) => (finish = resolve));
    };
    renderForm(upload);
    drop(file("big.pdf", 1000));
    fireEvent.click(await screen.findByRole("button", { name: /^Upload 1 file/ }));

    await waitFor(() => expect(hooks).toBeDefined());
    act(() => hooks.onProgress(300, 1000));
    // The file row and the overall bar both show the percentage.
    expect(await screen.findAllByText("30%")).toHaveLength(2);
    expect(screen.getByRole("progressbar", { name: "Upload of big.pdf" })).toHaveAttribute("aria-valuenow", "30");
    expect(screen.getByRole("progressbar", { name: "Overall upload" })).toHaveAttribute("aria-valuenow", "30");

    act(() => hooks.onSent());
    expect(await screen.findByText(/processing on server/)).toBeInTheDocument();

    await act(async () => finish(accepted("big.pdf", "d9")));
    expect(await screen.findByText("Accepted")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View" })).toHaveAttribute("href", "/documents/d9");
  });

  it("shows accepted, duplicate and rejected results with readable reasons", async () => {
    const results: Record<string, UploadResult> = {
      "a.pdf": accepted("a.pdf"),
      "b.pdf": { filename: "b.pdf", status: "duplicate", document_id: "d2", reason: null },
      "c.pdf": { filename: "c.pdf", status: "rejected", document_id: null, reason: "empty_file" },
    };
    renderForm(async (f) => results[f.name]);
    drop(file("a.pdf"), file("b.pdf"), file("c.pdf"));
    fireEvent.click(await screen.findByRole("button", { name: /^Upload 3 files/ }));

    expect(await screen.findByText("Accepted")).toBeInTheDocument();
    expect(screen.getByText("Already uploaded")).toBeInTheDocument();
    expect(screen.getByText(/Rejected: The file is empty/)).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "View" })).toHaveLength(2);
  });

  it("keeps the files when the request fails so they can be sent again", async () => {
    const { ApiError } = await import("@/lib/api");
    const upload = vi.fn<Uploader>().mockRejectedValueOnce(new ApiError(0, "x")).mockResolvedValueOnce(accepted("a.pdf"));
    renderForm(upload);
    drop(file("a.pdf"));
    fireEvent.click(await screen.findByRole("button", { name: /^Upload 1 file/ }));

    expect(await screen.findByText(/Failed: The server could not be reached/)).toBeInTheDocument();
    expect(screen.getByText("a.pdf")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /^Upload 1 file/ }));
    expect(await screen.findByText("Accepted")).toBeInTheDocument();
  });

  it("makes no second request when send is pressed twice", async () => {
    let finish!: (r: UploadResult) => void;
    const upload = vi.fn<Uploader>().mockImplementation(() => new Promise((resolve) => (finish = resolve)));
    renderForm(upload);
    drop(file("a.pdf"));
    const button = await screen.findByRole("button", { name: /^Upload 1 file/ });

    fireEvent.click(button);
    fireEvent.click(button);

    expect(upload).toHaveBeenCalledTimes(1);
    await act(async () => finish(accepted("a.pdf")));
  });
});
