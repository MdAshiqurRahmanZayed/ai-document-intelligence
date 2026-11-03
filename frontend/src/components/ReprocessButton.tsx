"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/Toast";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/messages";
import { isInProgress } from "@/lib/progress";
import type { DocumentStatus, FromStage } from "@/lib/types";

/** Reprocess a document: offered for failed, needs-review and completed documents, never while one is running. */
export function ReprocessButton({ id, status }: { id: string; status: DocumentStatus }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [stage, setStage] = useState<FromStage>("ingest");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () => api.reprocess(id, stage),
    onSuccess: () => {
      setOpen(false);
      toast("Queued for processing again.", "success");
      queryClient.invalidateQueries({ queryKey: ["document", id] });
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
    onError: (e) => setError(errorMessage(e)),
  });

  if (isInProgress(status)) return null;

  function close() {
    setOpen(false);
    setError(null);
  }

  return (
    <>
      <Button variant="secondary" onClick={() => setOpen(true)}>
        Reprocess
      </Button>
      <Modal open={open} title="Reprocess this document?" onClose={close}>
        <fieldset className="flex flex-col gap-2 text-sm">
          <legend className="sr-only">Where to start</legend>
          <label className="flex items-start gap-2">
            <input type="radio" name="stage" checked={stage === "ingest"} onChange={() => setStage("ingest")} className="mt-1" />
            <span>
              <strong>From the start</strong>
              <br />
              <span className="text-zinc-500">Read the file, recognise text, extract and validate again.</span>
            </span>
          </label>
          <label className="flex items-start gap-2">
            <input type="radio" name="stage" checked={stage === "extract"} onChange={() => setStage("extract")} className="mt-1" />
            <span>
              <strong>Extraction only</strong>
              <br />
              <span className="text-zinc-500">Use the text already stored; extract and validate again.</span>
            </span>
          </label>
        </fieldset>
        <p className="mt-4 rounded-lg bg-amber-50 p-3 text-xs text-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
          Extracting again makes the model&apos;s values the current version. Your manual corrections stay in the history but stop being current.
        </p>
        {error && (
          <p role="alert" className="mt-3 text-sm text-red-700 dark:text-red-400">
            {error}
          </p>
        )}
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={close}>
            Cancel
          </Button>
          <Button loading={mutation.isPending} onClick={() => mutation.mutate()}>
            Reprocess
          </Button>
        </div>
      </Modal>
    </>
  );
}
