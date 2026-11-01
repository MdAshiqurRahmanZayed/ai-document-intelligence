import { ReadinessPanel } from "@/components/ReadinessPanel";

export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 px-6 py-24">
      <h1 className="text-3xl font-semibold tracking-tight">AI Document Intelligence</h1>
      <p className="text-zinc-600 dark:text-zinc-400">System status</p>
      <ReadinessPanel />
    </main>
  );
}
