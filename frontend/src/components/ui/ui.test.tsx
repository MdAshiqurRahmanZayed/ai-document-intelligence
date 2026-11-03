import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Button } from "./Button";
import { EmptyState } from "./EmptyState";
import { ErrorState } from "./ErrorState";
import { Input, Select } from "./Input";
import { Modal } from "./Modal";
import { Progress } from "./Progress";
import { DocumentStatusBadge } from "./StatusBadge";
import { ToastProvider, useToast } from "./Toast";
import { ApiError } from "@/lib/api";

afterEach(() => vi.useRealTimers());

describe("Button", () => {
  it("is disabled and shows a spinner while loading", () => {
    render(<Button loading>Save</Button>);
    expect(screen.getByRole("button", { name: /save/i })).toBeDisabled();
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("calls onClick", async () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Go</Button>);
    await userEvent.click(screen.getByRole("button", { name: "Go" }));
    expect(onClick).toHaveBeenCalledOnce();
  });
});

describe("Input and Select", () => {
  it("links the label and shows the error as an alert", () => {
    render(<Input label="Total" error="Not a number" />);
    const input = screen.getByLabelText("Total");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("alert")).toHaveTextContent("Not a number");
  });

  it("shows the hint when there is no error", () => {
    render(<Select label="Status" hint="Pick one"><option>a</option></Select>);
    expect(screen.getByLabelText("Status")).toBeInTheDocument();
    expect(screen.getByText("Pick one")).toBeInTheDocument();
  });
});

describe("Progress", () => {
  it("exposes its value and clamps it", () => {
    const { rerender } = render(<Progress value={30} label="Upload" />);
    expect(screen.getByRole("progressbar", { name: "Upload" })).toHaveAttribute("aria-valuenow", "30");
    rerender(<Progress value={140} label="Upload" />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "100");
    rerender(<Progress value={-5} label="Upload" />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "0");
  });
});

describe("DocumentStatusBadge", () => {
  it("shows the status as words", () => {
    render(<DocumentStatusBadge status="NEEDS_REVIEW" />);
    expect(screen.getByText("Needs review")).toHaveAttribute("data-status", "NEEDS_REVIEW");
  });
});

function Harness({ onClose = () => {} }: { onClose?: () => void }) {
  const [open, setOpen] = useState(true);
  return (
    <>
      <button>outside</button>
      <Modal open={open} title="Confirm" onClose={() => { setOpen(false); onClose(); }}>
        <button>first</button>
        <button>last</button>
      </Modal>
    </>
  );
}

describe("Modal", () => {
  it("focuses its first control and closes on Escape", async () => {
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);
    expect(screen.getByRole("dialog", { name: "Confirm" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "first" })).toHaveFocus();

    await userEvent.keyboard("{Escape}");

    expect(onClose).toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("keeps Tab inside the dialog", async () => {
    render(<Harness />);
    screen.getByRole("button", { name: "last" }).focus();
    await userEvent.tab();
    expect(screen.getByRole("button", { name: "first" })).toHaveFocus();
    await userEvent.tab({ shift: true });
    expect(screen.getByRole("button", { name: "last" })).toHaveFocus();
  });

  it("closes on a backdrop click", () => {
    const onClose = vi.fn();
    const { container } = render(<Modal open title="T" onClose={onClose}>x</Modal>);
    fireEvent.click(container.querySelector("[aria-hidden]")!);
    expect(onClose).toHaveBeenCalled();
  });
});

describe("Toast", () => {
  function Trigger() {
    const toast = useToast();
    return <button onClick={() => toast("Saved", "success")}>fire</button>;
  }

  it("shows a message and removes it after the duration", () => {
    vi.useFakeTimers();
    render(<ToastProvider duration={1000}><Trigger /></ToastProvider>);

    fireEvent.click(screen.getByText("fire"));
    expect(screen.getByText("Saved")).toBeInTheDocument();

    act(() => vi.advanceTimersByTime(1100));
    expect(screen.queryByText("Saved")).toBeNull();
  });
});

describe("EmptyState and ErrorState", () => {
  it("explains an empty list", () => {
    render(<EmptyState title="No documents">Upload some.</EmptyState>);
    expect(screen.getByText("No documents")).toBeInTheDocument();
  });

  it("shows a readable error with a retry", async () => {
    const onRetry = vi.fn();
    render(<ErrorState error={new ApiError(502, "x")} onRetry={onRetry} />);
    expect(screen.getByRole("alert")).toHaveTextContent(/API could not be reached/);
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});
