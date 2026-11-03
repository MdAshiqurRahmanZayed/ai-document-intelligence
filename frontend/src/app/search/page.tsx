import { Suspense } from "react";

import { SearchPage } from "@/components/SearchPage";
import { Spinner } from "@/components/ui/Spinner";

export const metadata = { title: "Search · Document Intelligence" };

export default function Search() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Search</h1>
        <p className="mt-1 text-sm text-zinc-500">Find a processed document by what its text says.</p>
      </div>
      <Suspense fallback={<Spinner label="Loading" />}>
        <SearchPage />
      </Suspense>
    </div>
  );
}
