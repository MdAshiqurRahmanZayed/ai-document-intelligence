import { UploadForm } from "@/components/UploadForm";

export const metadata = { title: "Upload · Document Intelligence" };

export default function UploadPage() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Upload documents</h1>
        <p className="mt-1 text-sm text-zinc-500">Add several files at once. Each is checked, sent and then processed in the background.</p>
      </div>
      <UploadForm />
    </div>
  );
}
