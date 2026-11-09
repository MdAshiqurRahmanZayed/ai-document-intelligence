import { Suspense } from "react";

import { ChatPage } from "@/components/ChatPage";
import { Spinner } from "@/components/ui/Spinner";

export const metadata = { title: "Chat · Document Intelligence" };

export default function Chat() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Chat</h1>
        <p className="mt-1 text-sm text-zinc-500">Ask a question and get an answer read from your documents, with its sources. Chats are saved.</p>
      </div>
      <Suspense fallback={<Spinner label="Loading" />}>
        <ChatPage />
      </Suspense>
    </div>
  );
}
