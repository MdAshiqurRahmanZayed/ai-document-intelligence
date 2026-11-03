"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Input, Select } from "@/components/ui/Input";
import { DOC_LABELS } from "@/components/ui/StatusBadge";
import { hasFilters } from "@/lib/filters";
import { DOCUMENT_STATUSES, type DocumentFilters, type DocumentStatus } from "@/lib/types";

/** The invoice filters shared by the list and the search. Applies on submit. */
export function FilterBar({ value, onApply }: { value: DocumentFilters; onApply: (filters: DocumentFilters) => void }) {
  const [draft, setDraft] = useState<DocumentFilters>(value);
  const set = (key: keyof DocumentFilters) => (event: { target: { value: string } }) =>
    setDraft((d) => ({ ...d, [key]: event.target.value }));

  return (
    <form
      aria-label="Filters"
      onSubmit={(event) => {
        event.preventDefault();
        onApply(draft);
      }}
      className="grid grid-cols-2 gap-3 rounded-xl border border-zinc-200 bg-white p-4 md:grid-cols-4 dark:border-zinc-800 dark:bg-zinc-900"
    >
      <Select label="Status" value={draft.status ?? ""} onChange={set("status")}>
        <option value="">Any status</option>
        {DOCUMENT_STATUSES.map((s: DocumentStatus) => (
          <option key={s} value={s}>
            {DOC_LABELS[s]}
          </option>
        ))}
      </Select>
      <Input label="Supplier" value={draft.supplier ?? ""} onChange={set("supplier")} placeholder="e.g. Acme" />
      <Input label="Invoice number" value={draft.invoice_number ?? ""} onChange={set("invoice_number")} placeholder="e.g. INV-1042" />
      <Input label="Currency" value={draft.currency ?? ""} onChange={set("currency")} maxLength={3} placeholder="EUR" />
      <Input label="Date from" type="date" value={draft.date_from ?? ""} onChange={set("date_from")} />
      <Input label="Date to" type="date" value={draft.date_to ?? ""} onChange={set("date_to")} />
      <Input label="Amount from" inputMode="decimal" value={draft.amount_min ?? ""} onChange={set("amount_min")} placeholder="0.00" />
      <Input label="Amount to" inputMode="decimal" value={draft.amount_max ?? ""} onChange={set("amount_max")} placeholder="1000.00" />
      <div className="col-span-2 flex items-center justify-end gap-2 md:col-span-4">
        {hasFilters(value) && (
          <Button
            variant="ghost"
            onClick={() => {
              setDraft({});
              onApply({});
            }}
          >
            Clear filters
          </Button>
        )}
        <Button type="submit">Apply filters</Button>
      </div>
    </form>
  );
}
