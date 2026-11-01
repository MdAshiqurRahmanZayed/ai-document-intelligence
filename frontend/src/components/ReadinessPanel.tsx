"use client";

import { useEffect, useState } from "react";

import { StatusBadge, type Status } from "@/components/ui/StatusBadge";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const CHECKS = ["database", "redis", "storage"];
const POLL_MS = 5000;

export function ReadinessPanel() {
  const [api, setApi] = useState<Status>("loading");
  const [checks, setChecks] = useState<Record<string, Status>>({});

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        // /readyz answers 503 with a JSON body when a dependency is down.
        const res = await fetch(`${API_URL}/readyz`, { cache: "no-store" });
        const body = await res.json();
        if (!cancelled) {
          setApi(body.status);
          setChecks(body.checks);
        }
      } catch {
        if (!cancelled) {
          setApi("error");
          setChecks({});
        }
      }
    }

    poll();
    const timer = setInterval(poll, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  return (
    <div className="flex flex-wrap gap-3">
      <StatusBadge label="API" status={api} />
      {CHECKS.map((name) => (
        <StatusBadge
          key={name}
          label={name}
          status={checks[name] ?? (api === "loading" ? "loading" : "error")}
        />
      ))}
    </div>
  );
}
