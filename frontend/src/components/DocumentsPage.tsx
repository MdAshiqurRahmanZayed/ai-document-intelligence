"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { DocumentsView } from "@/components/DocumentsView";
import { filtersFromParams, filtersToParams } from "@/lib/filters";

/** Keeps the filters in the address, so a view can be shared and survives a reload. */
export function DocumentsPage() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  return (
    <DocumentsView
      filters={filtersFromParams(params)}
      onFiltersChange={(filters) => {
        const query = filtersToParams(filters).toString();
        router.replace(query ? `${pathname}?${query}` : pathname);
      }}
    />
  );
}
