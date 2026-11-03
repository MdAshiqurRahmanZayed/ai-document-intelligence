import { Spinner } from "@/components/ui/Spinner";

// The boundary that lets the page await its route params while the shell is already shown.
export default function Loading() {
  return (
    <div className="flex justify-center py-20 text-zinc-500">
      <Spinner label="Loading the document" />
    </div>
  );
}
