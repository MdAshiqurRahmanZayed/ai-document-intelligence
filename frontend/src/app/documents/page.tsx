import { Suspense } from "react";

import { DocumentsPage } from "@/components/DocumentsPage";
import { Spinner } from "@/components/ui/Spinner";

export const metadata = { title: "Documents · Document Intelligence" };

export default function Documents() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Documents</h1>
        <p className="mt-1 text-sm text-zinc-500">Everything you uploaded, newest first. Unfinished documents update by themselves.</p>
      </div>
      <Suspense fallback={<Spinner label="Loading" />}>
        <DocumentsPage />
      </Suspense>
    </div>
  );
}
