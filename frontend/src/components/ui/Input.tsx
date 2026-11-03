import { useId, type InputHTMLAttributes, type Ref, type SelectHTMLAttributes } from "react";

import { cn } from "@/lib/cn";

const FIELD =
  "block w-full rounded-lg border bg-white px-3 py-2 text-sm text-zinc-900 shadow-sm placeholder:text-zinc-400 " +
  "focus:outline-2 focus:outline-offset-0 focus:outline-indigo-500 dark:bg-zinc-900 dark:text-zinc-100 " +
  "disabled:cursor-not-allowed disabled:opacity-60";

interface FieldProps {
  label: string;
  error?: string;
  /** A softer problem than an error (a validation warning): amber instead of red. */
  warning?: string;
  hint?: string;
}

function Field({ id, label, error, warning, hint, children }: FieldProps & { id: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-xs font-medium text-zinc-600 dark:text-zinc-400">
        {label}
      </label>
      {children}
      {error ? (
        <p id={`${id}-error`} role="alert" className="text-xs text-red-600 dark:text-red-400">
          {error}
        </p>
      ) : warning ? (
        <p className="text-xs text-amber-700 dark:text-amber-400">{warning}</p>
      ) : (
        hint && <p className="text-xs text-zinc-500">{hint}</p>
      )}
    </div>
  );
}

export interface InputProps extends InputHTMLAttributes<HTMLInputElement>, FieldProps {
  ref?: Ref<HTMLInputElement>;
}

export function Input({ label, error, warning, hint, className, ...rest }: InputProps) {
  const id = useId();
  return (
    <Field id={id} label={label} error={error} warning={warning} hint={hint}>
      <input
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${id}-error` : undefined}
        className={cn(
          FIELD,
          error
            ? "border-red-500 bg-red-50/50 dark:bg-red-950/20"
            : warning
              ? "border-amber-500 bg-amber-50/50 dark:bg-amber-950/20"
              : "border-zinc-300 dark:border-zinc-700",
          className,
        )}
        {...rest}
      />
    </Field>
  );
}

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement>, FieldProps {
  ref?: Ref<HTMLSelectElement>;
}

export function Select({ label, error, warning, hint, className, children, ...rest }: SelectProps) {
  const id = useId();
  return (
    <Field id={id} label={label} error={error} warning={warning} hint={hint}>
      <select
        id={id}
        aria-invalid={error ? true : undefined}
        className={cn(FIELD, "border-zinc-300 dark:border-zinc-700", className)}
        {...rest}
      >
        {children}
      </select>
    </Field>
  );
}
