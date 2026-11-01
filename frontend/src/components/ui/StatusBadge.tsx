export type Status = "ok" | "error" | "loading";

const styles: Record<Status, string> = {
  ok: "bg-green-100 text-green-800",
  error: "bg-red-100 text-red-800",
  loading: "bg-zinc-100 text-zinc-600",
};

export function StatusBadge({ status, label }: { status: Status; label: string }) {
  return (
    <span
      data-status={status}
      className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-sm font-medium ${styles[status]}`}
    >
      {label}
      <span className="font-mono text-xs uppercase">{status}</span>
    </span>
  );
}
