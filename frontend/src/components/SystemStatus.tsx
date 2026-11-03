"use client";

import { useQuery } from "@tanstack/react-query";

import { API_BASE } from "@/lib/api";

interface Readiness {
  status: string;
  checks: Record<string, string>;
}

// /readyz answers 503 with a JSON body when a dependency is down, so a 503 is data, not an error.
async function fetchReadiness(): Promise<Readiness> {
  const res = await fetch(`${API_BASE}/readyz`, { cache: "no-store" });
  return res.json();
}

/** Small header indicator: one dot, and the failing parts on hover. */
export function SystemStatus() {
  const { data, isError } = useQuery({
    queryKey: ["readiness"],
    queryFn: fetchReadiness,
    refetchInterval: 10_000,
    retry: false,
  });

  const failing = data ? Object.entries(data.checks ?? {}).filter(([, v]) => v !== "ok") : [];
  const down = isError || (data && data.status !== "ok");
  const label = !data && !isError ? "Checking…" : down ? (failing.length ? `Degraded: ${failing.map(([k]) => k).join(", ")}` : "API unreachable") : "All systems running";
  const dot = !data && !isError ? "bg-zinc-400" : down ? "bg-red-500" : "bg-emerald-500";

  return (
    <span
      role="status"
      title={label}
      className="inline-flex items-center gap-2 text-xs text-zinc-600 dark:text-zinc-400"
    >
      <span className={`h-2 w-2 rounded-full ${dot}`} aria-hidden />
      <span className="hidden sm:inline">{label}</span>
    </span>
  );
}
