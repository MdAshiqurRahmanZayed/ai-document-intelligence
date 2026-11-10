"use client";

import { useRef, useState, type ReactNode } from "react";

import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { cn } from "@/lib/cn";
import type { ChatSessionSummary } from "@/lib/chatSessions";

const MAX_TITLE = 100;

interface Props {
  sessions: ChatSessionSummary[] | undefined;
  loading: boolean;
  failed: boolean;
  onRetry: () => void;
  activeId: string | null;
  onOpen: (id: string) => void;
  onNew: () => void;
  /** Rejects when the title could not be saved. */
  onRename: (id: string, title: string) => Promise<unknown>;
  /** Rejects when the session could not be deleted. */
  onDelete: (id: string) => Promise<unknown>;
}

/** The saved chats: open one, start a new one, rename in place, delete after a confirmation. */
export function SessionList({ sessions, loading, failed, onRetry, activeId, onOpen, onNew, onRename, onDelete }: Props) {
  const [shown, setShown] = useState(false); // on a narrow screen the list is behind a button
  const [editing, setEditing] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [confirming, setConfirming] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const cancelled = useRef(false); // Escape ends the edit, and the input losing focus must not save it

  function startRename(session: ChatSessionSummary) {
    setConfirming(null);
    setProblem(null);
    setTitle(session.title);
    cancelled.current = false;
    setEditing(session.id);
  }

  async function saveRename(session: ChatSessionSummary) {
    const next = title.trim();
    setEditing(null);
    if (cancelled.current || next === "" || next === session.title) return;
    try {
      await onRename(session.id, next);
    } catch {
      setProblem("The name could not be saved. Try again.");
    }
  }

  async function confirmDelete(id: string) {
    setConfirming(null);
    try {
      await onDelete(id);
    } catch {
      setProblem("The chat could not be deleted. Try again.");
    }
  }

  return (
    <nav aria-label="Saved chats" className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <Button className="flex-1" onClick={onNew}>
          New chat
        </Button>
        <Button variant="secondary" className="lg:hidden" aria-expanded={shown} onClick={() => setShown((v) => !v)}>
          Chats
        </Button>
      </div>

      <div className={cn("flex-col gap-2", shown ? "flex" : "hidden", "lg:flex")}>
        {problem && (
          <p role="alert" className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
            {problem}
          </p>
        )}
        {loading ? (
          <Spinner label="Loading chats" />
        ) : failed ? (
          <div role="alert" className="flex flex-col items-start gap-2 text-sm text-zinc-600 dark:text-zinc-400">
            <p>The saved chats could not be loaded.</p>
            <Button variant="secondary" size="sm" onClick={onRetry}>
              Try again
            </Button>
          </div>
        ) : !sessions || sessions.length === 0 ? (
          <p className="text-sm text-zinc-500">No saved chats yet.</p>
        ) : (
          <ul className="flex flex-col gap-1">
            {sessions.map((session) => (
              <li
                key={session.id}
                data-active={session.id === activeId}
                className="rounded-lg border border-transparent p-1 data-[active=true]:border-indigo-500 data-[active=true]:bg-indigo-50 dark:data-[active=true]:bg-indigo-950/40"
              >
                {editing === session.id ? (
                  <input
                    autoFocus
                    aria-label="Chat name"
                    value={title}
                    maxLength={MAX_TITLE}
                    onChange={(e) => setTitle(e.target.value)}
                    onBlur={() => void saveRename(session)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") void saveRename(session);
                      else if (e.key === "Escape") {
                        e.preventDefault();
                        cancelled.current = true;
                        setEditing(null);
                      }
                    }}
                    className="block w-full rounded-md border border-zinc-300 bg-white px-2 py-1 text-sm dark:border-zinc-700 dark:bg-zinc-900"
                  />
                ) : confirming === session.id ? (
                  <div className="flex flex-col gap-2 px-1 py-1 text-sm">
                    <p>Delete “{session.title}”?</p>
                    <div className="flex gap-2">
                      <Button variant="danger" size="sm" onClick={() => void confirmDelete(session.id)}>
                        Delete
                      </Button>
                      <Button variant="secondary" size="sm" onClick={() => setConfirming(null)}>
                        Cancel
                      </Button>
                    </div>
                  </div>
                ) : (
                  <div className="flex items-start gap-1">
                    <button
                      type="button"
                      title={session.title}
                      onClick={() => onOpen(session.id)}
                      aria-current={session.id === activeId ? "true" : undefined}
                      className="line-clamp-2 min-w-0 flex-1 rounded-md px-2 py-1 text-left text-sm break-words hover:bg-zinc-100 dark:hover:bg-zinc-800"
                    >
                      {session.title}
                    </button>
                    <IconButton label={`Rename ${session.title}`} onClick={() => startRename(session)}>
                      <path d="M12 20h9" />
                      <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" />
                    </IconButton>
                    <IconButton
                      label={`Delete ${session.title}`}
                      danger
                      onClick={() => {
                        setProblem(null);
                        setConfirming(session.id);
                      }}
                    >
                      <path d="M3 6h18" />
                      <path d="M8 6V4h8v2" />
                      <path d="M19 6l-1 14H6L5 6" />
                      <path d="M10 11v6M14 11v6" />
                    </IconButton>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </nav>
  );
}

function IconButton({ label, danger = false, onClick, children }: { label: string; danger?: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      className={cn(
        "grid h-7 w-7 shrink-0 place-items-center rounded-md text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800",
        danger ? "hover:text-red-600" : "hover:text-indigo-600",
      )}
    >
      <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        {children}
      </svg>
    </button>
  );
}
