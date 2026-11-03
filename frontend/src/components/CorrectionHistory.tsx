"use client";

import { Card } from "@/components/ui/Card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { useCorrections } from "@/hooks/useDocument";
import { formatDateTime } from "@/lib/format";
import type { DocumentStatus } from "@/lib/types";

/** Who changed what, newest first. Shown only when there is something to show. */
export function CorrectionHistory({ id, status }: { id: string; status: DocumentStatus }) {
  const { data } = useCorrections(id, status);
  if (!data || data.length === 0) return null;

  return (
    <Card className="flex flex-col gap-3">
      <h2 className="font-semibold">Correction history</h2>
      <Table aria-label="Correction history">
        <THead>
          <TR>
            <TH>Field</TH>
            <TH>Before</TH>
            <TH>After</TH>
            <TH>By</TH>
            <TH>When</TH>
          </TR>
        </THead>
        <TBody>
          {data.map((c, i) => (
            <TR key={`${c.created_at}-${c.field}-${i}`}>
              <TD className="font-mono text-xs">
                {c.field}
                {data.some((o) => o.invoice_index !== c.invoice_index) && <span className="text-zinc-400"> #{c.invoice_index + 1}</span>}
              </TD>
              <TD className="max-w-48 break-words text-zinc-500">{c.old_value ?? "—"}</TD>
              <TD className="max-w-48 break-words">{c.new_value ?? "—"}</TD>
              <TD>{c.edited_by}</TD>
              <TD className="whitespace-nowrap text-zinc-500">{formatDateTime(c.created_at)}</TD>
            </TR>
          ))}
        </TBody>
      </Table>
    </Card>
  );
}
