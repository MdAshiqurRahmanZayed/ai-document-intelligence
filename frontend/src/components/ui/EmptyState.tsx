import type { ReactNode } from "react";

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-zinc-300 px-6 py-14 text-center dark:border-zinc-700">
      <p className="font-medium">{title}</p>
      {children && <div className="text-sm text-zinc-500">{children}</div>}
    </div>
  );
}
