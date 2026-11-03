"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useFieldArray, useForm } from "react-hook-form";

import { FindingsList } from "@/components/FindingsList";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { useToast } from "@/components/ui/Toast";
import { api, ApiError } from "@/lib/api";
import { invoiceFormSchema, SCALAR_FIELDS, toFormValues, toPatch, type InvoiceForm, type ScalarField } from "@/lib/invoiceForm";
import { errorMessage } from "@/lib/messages";
import type { Finding, InvoiceResult } from "@/lib/types";

const LABELS: Record<ScalarField, string> = {
  invoice_number: "Invoice number",
  invoice_date: "Invoice date",
  supplier_name: "Supplier",
  customer_name: "Customer",
  subtotal: "Subtotal",
  tax: "Tax",
  total: "Total",
  currency: "Currency",
};

const EDITOR_KEY = "invoice-editor-name";

function savedName(): string {
  try {
    return localStorage.getItem(EDITOR_KEY) || "web";
  } catch {
    return "web";
  }
}

function rememberName(name: string) {
  try {
    localStorage.setItem(EDITOR_KEY, name);
  } catch {
    // storage may be blocked; the name is only a convenience
  }
}

/** What the model said about a value: its confidence and the quote it came from. */
function provenance(invoice: InvoiceResult, field: string): string | undefined {
  const confidence = invoice.field_confidence[field];
  const quote = invoice.grounding[field];
  const parts = [confidence !== undefined && `Confidence ${Math.round(confidence * 100)}%`, quote && `“${quote}”`].filter(Boolean);
  return parts.length ? (parts.join(" · ") as string) : undefined;
}

export function InvoiceCard({ documentId, invoice, busy }: { documentId: string; invoice: InvoiceResult; busy: boolean }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const initial = toFormValues(invoice.data);
  const [editor, setEditor] = useState(savedName);
  const [formError, setFormError] = useState<string | null>(null);

  const {
    register,
    control,
    handleSubmit,
    reset,
    setError,
    formState: { errors, isDirty },
  } = useForm<InvoiceForm>({ resolver: zodResolver(invoiceFormSchema), defaultValues: initial });
  const lines = useFieldArray({ control, name: "line_items" });

  const save = useMutation({
    mutationFn: (values: InvoiceForm) => api.correctInvoice(documentId, invoice.invoice_index, toPatch(initial, values), editor.trim() || "web"),
    onSuccess: (saved) => {
      rememberName(editor.trim() || "web");
      reset(toFormValues(saved.data));
      toast("Correction saved and the invoice was checked again.", "success");
      queryClient.invalidateQueries({ queryKey: ["result", documentId] });
      queryClient.invalidateQueries({ queryKey: ["document", documentId] });
      queryClient.invalidateQueries({ queryKey: ["corrections", documentId] });
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
    onError: (error) => {
      // The API names the field it could not read; show its message there and keep what was typed.
      if (error instanceof ApiError && error.status === 422 && error.field && (error.field === "line_items" || SCALAR_FIELDS.includes(error.field as ScalarField))) {
        setError(error.field as ScalarField, { type: "server", message: error.message });
        return;
      }
      setFormError(errorMessage(error));
    },
  });

  const findingsFor = (field: string): Finding[] => invoice.validation_errors.filter((f) => f.field === field);
  const marks = (field: ScalarField) => {
    const own = errors[field]?.message;
    const found = findingsFor(field);
    const err = found.find((f) => f.severity === "error");
    const warn = found.find((f) => f.severity === "warning");
    return {
      error: own ?? err?.message,
      warning: own || err ? undefined : warn?.message,
      hint: provenance(invoice, field),
    };
  };

  const onSubmit = handleSubmit((values) => {
    setFormError(null);
    save.mutate(values);
  });

  return (
    <Card className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <h3 className="font-semibold">Invoice {invoice.invoice_index + 1}</h3>
        <span className="text-xs text-zinc-500">
          Version {invoice.version} · {invoice.model === "manual" ? "edited by hand" : invoice.model}
        </span>
      </div>

      <FindingsList findings={invoice.validation_errors} />

      <form onSubmit={onSubmit} aria-label={`Invoice ${invoice.invoice_index + 1}`} className="flex flex-col gap-4" noValidate>
        <fieldset disabled={busy} className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {SCALAR_FIELDS.map((field) => (
            <Input
              key={field}
              label={LABELS[field]}
              type={field === "invoice_date" ? "date" : "text"}
              inputMode={["subtotal", "tax", "total"].includes(field) ? "decimal" : undefined}
              {...marks(field)}
              {...register(field)}
            />
          ))}
        </fieldset>

        <fieldset disabled={busy} className="flex flex-col gap-2">
          <legend className="mb-1 text-xs font-medium text-zinc-600 dark:text-zinc-400">Line items</legend>
          {lines.fields.length === 0 && <p className="text-sm text-zinc-500">No line items.</p>}
          {lines.fields.map((row, i) => (
            <div key={row.id} className="grid grid-cols-2 items-end gap-2 sm:grid-cols-[2fr_1fr_1fr_1fr_auto]">
              <div className="col-span-2 sm:col-span-1">
                <Input label="Description" {...register(`line_items.${i}.description`)} />
              </div>
              <Input label="Qty" inputMode="decimal" error={errors.line_items?.[i]?.quantity?.message} {...register(`line_items.${i}.quantity`)} />
              <Input label="Unit price" inputMode="decimal" error={errors.line_items?.[i]?.unit_price?.message} {...register(`line_items.${i}.unit_price`)} />
              <Input label="Amount" inputMode="decimal" error={errors.line_items?.[i]?.amount?.message} {...register(`line_items.${i}.amount`)} />
              <Button variant="ghost" size="sm" aria-label={`Remove line ${i + 1}`} onClick={() => lines.remove(i)}>
                ×
              </Button>
            </div>
          ))}
          <div>
            <Button variant="secondary" size="sm" onClick={() => lines.append({ description: "", quantity: "", unit_price: "", amount: "" })}>
              Add line
            </Button>
          </div>
          {errors.line_items?.message && <p role="alert" className="text-xs text-red-600">{errors.line_items.message}</p>}
        </fieldset>

        {busy && <p className="text-sm text-zinc-500">This document is being processed. You can edit it once processing finishes.</p>}
        {formError && (
          <p role="alert" className="text-sm text-red-700 dark:text-red-400">
            {formError}
          </p>
        )}

        <div className="flex flex-wrap items-end justify-between gap-3 border-t border-zinc-100 pt-4 dark:border-zinc-800">
          <div className="w-48">
            <Input label="Edited by" value={editor} onChange={(e) => setEditor(e.target.value)} hint="Recorded in the history" />
          </div>
          <Button type="submit" disabled={!isDirty || busy} loading={save.isPending}>
            Save correction
          </Button>
        </div>
      </form>
    </Card>
  );
}
