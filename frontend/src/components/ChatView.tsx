"use client";

import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";

import { AnswerText } from "@/components/AnswerText";
import { FilterBar } from "@/components/FilterBar";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Input } from "@/components/ui/Input";
import { Spinner } from "@/components/ui/Spinner";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/cn";
import { chatSessions, turnsFromMessages, type ChatSessionSummary, type Turn } from "@/lib/chatSessions";
import { chatStream, type ChatSource } from "@/lib/chatStream";
import type { DocumentFilters } from "@/lib/types";

const MAX_QUESTION = 1000;

const EXAMPLES = ["Which supplier invoiced hosting?", "What are the payment terms?", "Which invoice mentions freight?"];

const FAILURES: Record<string, string> = {
  provider_limited: "The model provider's limit has been reached. Try again later.",
  model_failed: "The answer could not be written. Try again.",
};

const active = (turn: Turn) => turn.phase === "reading" || turn.phase === "streaming";

type Loading = "idle" | "loading" | "missing" | "failed";

interface Props {
  /** The saved chat shown, from the address; null for a new chat. */
  sessionId?: string | null;
  /** A chat was created (by the first question) or left (new chat, switching). */
  onSessionChange?: (id: string | null, created?: ChatSessionSummary) => void;
  /** An answer ended, so the list of chats can be refreshed. */
  onTurnEnd?: () => void;
}

export function ChatView({ sessionId = null, onSessionChange, onTurnEnd }: Props) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [filters, setFilters] = useState<DocumentFilters>({});
  const [attempt, setAttempt] = useState(0);
  const [loading, setLoading] = useState<Loading>(sessionId ? "loading" : "idle");
  const nextId = useRef(0); // never reused, so a late update of an old stream cannot touch a new turn
  const controller = useRef<AbortController | null>(null);
  // The chat the turns belong to. The first question creates it and puts its id in the address; that
  // change of `sessionId` must not reload what is already on screen.
  const own = useRef<string | null>(null);
  const busy = turns.some(active);

  useEffect(() => () => controller.current?.abort(), []);

  useEffect(() => {
    if (sessionId === own.current) return;
    // Another chat (or none) was chosen: end any stream first, so its text so far is saved as stopped.
    controller.current?.abort();
    own.current = sessionId;
    if (sessionId === null) {
      setTurns([]);
      setLoading("idle");
      return;
    }
    let current = true;
    setTurns([]);
    setLoading("loading");
    chatSessions
      .get(sessionId)
      .then((saved) => {
        if (!current) return;
        const loaded = turnsFromMessages(saved.messages, nextId.current);
        nextId.current += loaded.length;
        setTurns(loaded);
        setLoading("idle");
      })
      .catch((error) => {
        if (current) setLoading(error instanceof ApiError && error.status === 404 ? "missing" : "failed");
      });
    return () => {
      current = false;
    };
  }, [sessionId, attempt]);

  async function ask(raw: string) {
    const question = raw.trim();
    if (!question || busy || loading !== "idle") return;
    const id = nextId.current++;
    const abort = new AbortController();
    controller.current = abort;
    setDraft("");
    setTurns((all) => [
      ...all,
      { id, question, answer: "", sources: [], rewritten: null, suggestions: [], citations: null, phase: "reading", failure: null },
    ]);
    const update = (patch: (turn: Turn) => Partial<Turn>) =>
      setTurns((all) => all.map((t) => (t.id === id ? { ...t, ...patch(t) } : t)));

    try {
      if (own.current === null) {
        const created = await chatSessions.create();
        own.current = created.id;
        // The list shows the new chat at once, titled from the question.
        onSessionChange?.(created.id, { ...created, title: question.replace(/\s+/g, " ").slice(0, 60) });
      }
      for await (const event of chatStream({ question, sessionId: own.current, filters }, abort.signal)) {
        if (event.type === "sources") update(() => ({ sources: event.sources, rewritten: event.rewritten_question ?? null }));
        else if (event.type === "token") update((t) => ({ answer: t.answer + event.text, phase: "streaming" }));
        else if (event.type === "done") update(() => ({ suggestions: event.suggestions, citations: event.citations, phase: "done" }));
        else update(() => ({ phase: "failed", failure: { reason: event.reason } }));
      }
      // The stream ended without a done or an error: stopped by the person, or cut off.
      update((t) =>
        active(t) ? (abort.signal.aborted ? { phase: "stopped" } : { phase: "failed", failure: { reason: "model_failed" } }) : {},
      );
    } catch (error) {
      update(() => ({ phase: "failed", failure: error instanceof ApiError ? error : { reason: "model_failed" } }));
    } finally {
      if (controller.current === abort) controller.current = null;
      onTurnEnd?.();
    }
  }

  function retry(turn: Turn) {
    setTurns((all) => all.filter((t) => t.id !== turn.id));
    void ask(turn.question);
  }

  const last = turns.at(-1);

  return (
    <div className="flex flex-col gap-4">
      <details open={Object.keys(filters).length > 0}>
        <summary className="cursor-pointer text-sm font-medium text-zinc-600 dark:text-zinc-400">Filters</summary>
        <div className="mt-3">
          <FilterBar key={JSON.stringify(filters)} value={filters} onApply={setFilters} />
        </div>
      </details>

      {loading === "loading" ? (
        <Spinner label="Loading the chat" />
      ) : loading === "missing" ? (
        <EmptyState title="This chat was not found">
          <p>It may have been deleted.</p>
          <Link href="/chat" className="mt-2 inline-block font-medium text-indigo-600 hover:underline">
            Start a new chat
          </Link>
        </EmptyState>
      ) : loading === "failed" ? (
        <ErrorState
          error={new ApiError(0, "Network error")}
          onRetry={() => {
            own.current = null; // load it again
            setAttempt((n) => n + 1);
          }}
        />
      ) : turns.length === 0 ? (
        <EmptyState title="Ask about your documents">
          <div className="flex flex-col items-center gap-2">
            <p>Try one of these:</p>
            <div className="flex flex-wrap justify-center gap-2">
              {EXAMPLES.map((example) => (
                <Button key={example} variant="secondary" size="sm" onClick={() => void ask(example)}>
                  {example}
                </Button>
              ))}
            </div>
          </div>
        </EmptyState>
      ) : (
        <ol className="flex flex-col gap-6" aria-label="Conversation">
          {turns.map((turn) => (
            <li key={turn.id}>
              <TurnView
                turn={turn}
                onRetry={() => retry(turn)}
                suggestions={turn === last && turn.phase === "done" ? turn.suggestions : []}
                onAsk={(q) => void ask(q)}
              />
            </li>
          ))}
        </ol>
      )}

      <form
        onSubmit={(event) => {
          event.preventDefault();
          void ask(draft);
        }}
        className="flex flex-col gap-3 sm:flex-row sm:items-end"
      >
        <div className="flex-1">
          <Input
            label="Ask about your documents"
            value={draft}
            maxLength={MAX_QUESTION}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="e.g. Which supplier invoiced hosting?"
          />
        </div>
        {busy ? (
          <Button variant="secondary" onClick={() => controller.current?.abort()}>
            Stop
          </Button>
        ) : (
          <Button type="submit" disabled={draft.trim() === "" || loading !== "idle"}>
            Ask
          </Button>
        )}
      </form>
    </div>
  );
}

function TurnView({
  turn,
  suggestions,
  onRetry,
  onAsk,
}: {
  turn: Turn;
  suggestions: string[];
  onRetry: () => void;
  onAsk: (question: string) => void;
}) {
  const [active, setActive] = useState<number | null>(null);
  const failure = turn.failure;
  const unavailable = failure instanceof ApiError && failure.reason === "chat_unavailable";
  const shown = shownSources(turn);
  const hasSources = shown.length > 0;
  return (
    <div className="flex flex-col gap-3">
      <p className="max-w-3xl self-end rounded-2xl bg-indigo-600 px-4 py-2 text-sm text-white">{turn.question}</p>

      {unavailable ? (
        <EmptyState title="Chat is not available">It needs a configured Google API key.</EmptyState>
      ) : failure instanceof ApiError ? (
        <ErrorState error={failure} onRetry={onRetry} />
      ) : (
        // The answer on the left, its sources in a list on the right; stacked on a narrow screen.
        <div className={cn("grid items-start gap-4", hasSources && "lg:grid-cols-[minmax(0,1fr)_22rem]")}>
          <Card className="flex flex-col gap-3">
            {turn.rewritten && <p className="text-xs text-zinc-500">Searched for: {turn.rewritten}</p>}
            {turn.phase === "reading" || (turn.phase === "streaming" && turn.answer === "") ? (
              <div className="flex items-center gap-2 text-sm text-zinc-500">
                <Spinner label="Reading the documents" />
                <span>{hasSources ? "Writing the answer…" : "Reading the documents…"}</span>
              </div>
            ) : (
              <AnswerText text={turn.answer} sources={turn.sources} onActive={setActive} />
            )}
            {turn.phase === "stopped" && <p className="text-xs text-zinc-500">Stopped.</p>}
            {turn.phase === "done" && turn.sources.length === 0 && (
              <p className="text-sm text-zinc-500">Try another question, or remove a filter.</p>
            )}
            {failure && (
              <div role="alert" className="flex flex-wrap items-center gap-3 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
                <span>{FAILURES[failure.reason ?? ""] ?? FAILURES.model_failed}</span>
                <Button variant="secondary" size="sm" onClick={onRetry}>
                  Try again
                </Button>
              </div>
            )}
          </Card>
          {hasSources && <Sources sources={shown} active={active} />}
        </div>
      )}

      {suggestions.length > 0 && (
        <div className="flex flex-wrap gap-2" aria-label="Follow-up questions">
          {suggestions.map((question) => (
            <Button key={question} variant="secondary" size="sm" onClick={() => onAsk(question)}>
              {question}
            </Button>
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * The sources to list. While the answer is being written everything it is reading is shown; once it is
 * done, only the sources it cites, so a person sees the relevant references and not every chunk the model
 * was given. A stopped or failed answer shows what its text cites so far. Numbers stay as sent, so the chips match.
 */
function shownSources(turn: Turn): ChatSource[] {
  if (turn.phase === "reading" || turn.phase === "streaming") return turn.sources;
  const cited = turn.phase === "done" && turn.citations ? turn.citations : [...turn.answer.matchAll(/\[(\d+)\]/g)].map((m) => Number(m[1]));
  return turn.sources.filter((s) => cited.includes(s.n));
}

function Sources({ sources, active }: { sources: ChatSource[]; active: number | null }) {
  const titleId = useId();
  return (
    <section aria-labelledby={titleId} className="flex flex-col gap-2 lg:sticky lg:top-20">
      <h2 id={titleId} className="text-xs font-semibold tracking-wide text-zinc-500 uppercase">
        Sources · {sources.length}
      </h2>
      <ul aria-label="Sources" className="flex flex-col gap-2">
        {sources.map((s) => (
          <li
            key={s.n}
            data-active={active === s.n}
            className="rounded-xl border border-zinc-200 bg-white p-3 text-sm transition-colors data-[active=true]:border-indigo-500 data-[active=true]:bg-indigo-50 dark:border-zinc-800 dark:bg-zinc-900 dark:data-[active=true]:bg-indigo-950/40"
          >
            <div className="flex items-center gap-2">
              <span className="grid h-5 min-w-5 place-items-center rounded-full bg-indigo-100 px-1 text-xs font-semibold text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">
                {s.n}
              </span>
              <Link href={`/documents/${s.document_id}`} className="min-w-0 flex-1 truncate font-medium text-indigo-600 hover:underline">
                {s.filename}
              </Link>
              <span className="shrink-0 text-xs text-zinc-500">page {s.page_no}</span>
            </div>
            <p className="mt-1.5 line-clamp-4 text-xs text-zinc-600 dark:text-zinc-400">{s.quote}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}
