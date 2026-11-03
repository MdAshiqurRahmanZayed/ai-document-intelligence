import { Spinner } from "@/components/ui/Spinner";
import { cn } from "@/lib/cn";
import { formatDuration } from "@/lib/format";
import type { Step, StepState } from "@/lib/progress";

const ICON: Record<StepState, string> = { waiting: "○", running: "", done: "✓", failed: "✕" };
const TONE: Record<StepState, string> = {
  waiting: "border-zinc-300 text-zinc-400 dark:border-zinc-700",
  running: "border-indigo-500 text-indigo-600",
  done: "border-emerald-500 bg-emerald-500 text-white",
  failed: "border-red-500 bg-red-500 text-white",
};
const WORD: Record<StepState, string> = { waiting: "waiting", running: "running", done: "done", failed: "failed" };

/** The steps a document goes through, each marked waiting, running, done or failed. */
export function StepsTimeline({ steps }: { steps: Step[] }) {
  return (
    <ol aria-label="Processing steps" className="flex flex-col gap-3">
      {steps.map((step) => (
        <li key={step.key} data-state={step.state} className="flex items-start gap-3">
          <span className={cn("mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full border-2 text-xs font-bold", TONE[step.state])} aria-hidden>
            {step.state === "running" ? <Spinner label="" /> : ICON[step.state]}
          </span>
          <div className="min-w-0 text-sm">
            <p className="font-medium">
              {step.label} <span className="sr-only">({WORD[step.state]})</span>
              {step.attempt && step.attempt > 1 && <span className="ml-2 text-xs font-normal text-amber-700 dark:text-amber-400">attempt {step.attempt}</span>}
              {step.durationMs !== null && <span className="ml-2 text-xs font-normal text-zinc-500">{formatDuration(step.durationMs)}</span>}
            </p>
            {step.error && <p className="mt-0.5 break-words text-xs text-red-700 dark:text-red-400">{step.error}</p>}
          </div>
        </li>
      ))}
    </ol>
  );
}
