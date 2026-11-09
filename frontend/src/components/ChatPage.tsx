"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { ChatView } from "@/components/ChatView";
import { SessionList } from "@/components/SessionList";
import { chatSessions, type ChatSessionSummary } from "@/lib/chatSessions";

const KEY = ["chat-sessions"];

/** The saved chats beside the open conversation. The open chat is in the address (`?session=`), so a reload or a link returns to it. */
export function ChatPage() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const client = useQueryClient();
  const sessionId = params.get("session");

  const list = useQuery({ queryKey: KEY, queryFn: () => chatSessions.list().then((r) => r.items) });

  const show = (id: string | null) => router.push(id ? `${pathname}?session=${id}` : pathname);

  const rename = useMutation({
    mutationFn: ({ id, title }: { id: string; title: string }) => chatSessions.rename(id, title),
    onSuccess: (saved) =>
      client.setQueryData<ChatSessionSummary[]>(KEY, (all) => all?.map((s) => (s.id === saved.id ? { ...s, title: saved.title } : s))),
  });

  const remove = useMutation({
    mutationFn: (id: string) => chatSessions.remove(id),
    onSuccess: (_, id) => {
      client.setQueryData<ChatSessionSummary[]>(KEY, (all) => all?.filter((s) => s.id !== id));
      if (id === sessionId) show(null);
    },
  });

  return (
    <div className="grid items-start gap-6 lg:grid-cols-[20rem_minmax(0,1fr)]">
      <SessionList
        sessions={list.data}
        loading={list.isPending}
        failed={list.isError}
        onRetry={() => void list.refetch()}
        activeId={sessionId}
        onOpen={show}
        onNew={() => show(null)}
        onRename={(id, title) => rename.mutateAsync({ id, title })}
        onDelete={(id) => remove.mutateAsync(id)}
      />
      <ChatView
        sessionId={sessionId}
        onSessionChange={(id, created) => {
          if (created) client.setQueryData<ChatSessionSummary[]>(KEY, (all) => [created, ...(all ?? [])]);
          // replace, not push: the first question should not add a history entry for the same chat
          if (id) router.replace(`${pathname}?session=${id}`);
        }}
        onTurnEnd={() => void client.invalidateQueries({ queryKey: KEY })}
      />
    </div>
  );
}
