import { cn } from "@/lib/cn";

type Tone = "indigo" | "green" | "red" | "amber";

const FILL: Record<Tone, string> = {
  indigo: "bg-indigo-600",
  green: "bg-emerald-500",
  red: "bg-red-500",
  amber: "bg-amber-500",
};

/** A labelled progress bar; `value` is 0 to 100 and is clamped. */
export function Progress({
  value,
  label,
  tone = "indigo",
  className,
}: {
  value: number;
  label: string;
  tone?: Tone;
  className?: string;
}) {
  const pct = Math.round(Math.min(100, Math.max(0, value)));
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={pct}
      className={cn("h-2 w-full overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800", className)}
    >
      <div className={cn("h-full rounded-full transition-[width] duration-300", FILL[tone])} style={{ width: `${pct}%` }} />
    </div>
  );
}
