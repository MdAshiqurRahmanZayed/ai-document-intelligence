import { Button } from "@/components/ui/Button";
import { errorMessage } from "@/lib/messages";

/** A failed request in words, with a way to try again. */
export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <div
      role="alert"
      className="flex flex-col items-center gap-3 rounded-xl border border-red-200 bg-red-50 px-6 py-10 text-center dark:border-red-900 dark:bg-red-950/40"
    >
      <p className="font-medium text-red-900 dark:text-red-100">Something went wrong</p>
      <p className="text-sm text-red-800 dark:text-red-200">{errorMessage(error)}</p>
      {onRetry && (
        <Button variant="secondary" size="sm" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}
