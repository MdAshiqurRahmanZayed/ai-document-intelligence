import { ReviewView } from "@/components/ReviewView";

export const metadata = { title: "Review · Document Intelligence" };

export default function Review() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Review</h1>
        <p className="mt-1 text-sm text-zinc-500">Documents that need a person: values to check, and files that failed to process.</p>
      </div>
      <ReviewView />
    </div>
  );
}
