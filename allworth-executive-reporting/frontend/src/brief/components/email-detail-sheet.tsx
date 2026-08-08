

import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { fallbackAnalysisNotice, getAnalysis } from "../analysis";
import { fetchLiveDetail } from "../briefApi";
import { formatDeadline, formatFullDate } from "../format";
import { MOCK_THREADS } from "../mockData";
import { useInbox } from "../store";
import type { EmailAnalysis, ExecutiveEmail, ThreadMessage } from "../types";
import { MissingContextPanel } from "./missing-context-panel";
import { MoreMenu } from "./more-menu";
import { PriorityBadge } from "./priority-badge";

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="border-b border-line pb-4">
      <h3 className="text-xs font-bold uppercase tracking-wide text-ink-faint">{title}</h3>
      <div className="mt-2 text-sm leading-relaxed text-ink">{children}</div>
    </section>
  );
}

export function EmailDetailSheet({
  email,
  onClose,
  onReply,
  onAction,
}: {
  email: ExecutiveEmail;
  onClose: () => void;
  onReply: () => void;
  onAction?: (label: string) => void;
}) {
  const inbox = useInbox();
  const mockThread = MOCK_THREADS[email.threadId];
  // Initial data is the bundled mock; in live mode the effect below replaces it
  // with the real thread + analysis fetched from the backend.
  const [analysis, setAnalysis] = useState<EmailAnalysis | null>(() => getAnalysis(email));
  const [threadMsgs, setThreadMsgs] = useState<ThreadMessage[]>(() => mockThread?.messages ?? []);
  const [loadingLive, setLoadingLive] = useState(inbox.mode === "live");
  const original = threadMsgs[threadMsgs.length - 1];
  const priorMessages = threadMsgs.slice(0, -1);

  useEffect(() => {
    inbox.markRead(email.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [email.id]);

  useEffect(() => {
    if (inbox.mode !== "live") return;
    let cancelled = false;
    setLoadingLive(true);
    fetchLiveDetail(email.id)
      .then((d) => {
        if (cancelled) return;
        if (d.thread.length) setThreadMsgs(d.thread);
        setAnalysis(d.analysis); // may be null → safe fallback, original still shown
      })
      .catch(() => {
        // Keep whatever we have; never hide the email on a fetch error.
      })
      .finally(() => {
        if (!cancelled) setLoadingLive(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [email.id, inbox.mode]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-40 flex flex-col overflow-hidden bg-paper animate-sheet-up lg:relative lg:inset-auto lg:z-auto lg:h-full lg:animate-none lg:rounded-lg lg:ring-1 lg:ring-line"
      role="dialog"
      aria-modal="true"
      aria-label={`Email from ${email.senderName}: ${email.subject}`}
    >
      {/* Header */}
      <header className="flex items-center gap-3 border-b border-line bg-card px-4 py-3 lg:rounded-t-lg">
        <button
          onClick={onClose}
          aria-label="Close"
          className="flex min-h-11 min-w-11 items-center justify-center rounded-lg text-xl text-ink-soft hover:bg-paper"
        >
          ←
        </button>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-bold">{email.senderName}</p>
          <p className="truncate text-xs text-ink-faint">
            {email.senderRole ? `${email.senderRole} · ` : ""}
            {email.senderEmail}
          </p>
        </div>
        <PriorityBadge priority={email.priority} />
      </header>

      {/* Scrollable body */}
      <div className="flex-1 space-y-3 overflow-y-auto px-4 pb-28 pt-4">
        <h2 className="text-lg font-bold leading-snug">{email.subject}</h2>
        <p className="text-xs text-ink-faint">Received {formatFullDate(email.receivedAt)}</p>

        {email.delegatedTo ? (
          <p className="border-b border-line bg-paper px-3 py-2 text-sm font-semibold text-accent">
            Delegated to {email.delegatedTo}
          </p>
        ) : null}

        {loadingLive && !analysis ? (
          <p className="border-b border-line bg-paper px-3 py-2 text-sm font-medium text-accent">
            Analyzing this email…
          </p>
        ) : null}

        {analysis ? (
          <>
            <Section title="Why this matters">{analysis.why_it_matters}</Section>
            <Section title="What they need">
              {analysis.request}
              {analysis.deadline ? (
                <p className="mt-2">
                  <span className="text-xs font-semibold text-critical">
                    ⏰ Due {formatDeadline(analysis.deadline)}
                  </span>
                </p>
              ) : null}
            </Section>
            <Section title="Recommended action">{analysis.recommended_action}</Section>

            <MissingContextPanel analysis={analysis} />

            {analysis.commitments.length > 0 ? (
              <Section title="Related commitments">
                <ul className="space-y-1">
                  {analysis.commitments.map((c) => (
                    <li key={c} className="flex gap-2">
                      <span className="shrink-0 text-accent">↩</span>
                      {c}
                    </li>
                  ))}
                </ul>
              </Section>
            ) : null}

            {analysis.key_people.length > 0 ? (
              <Section title="People">
                <ul className="space-y-1">
                  {analysis.key_people.map((p) => (
                    <li key={p.name}>
                      <span className="font-semibold">{p.name}</span>
                      {p.role ? <span className="text-ink-faint"> — {p.role}</span> : null}
                    </li>
                  ))}
                </ul>
              </Section>
            ) : null}

            {analysis.attachments.length > 0 ? (
              <Section title="Attachments">
                <ul className="space-y-2">
                  {analysis.attachments.map((a) => (
                    <li key={a.name} className="flex items-center gap-2 border-t border-line py-2.5">
                      <span aria-hidden>📎</span>
                      <span className="min-w-0 flex-1 truncate font-medium">{a.name}</span>
                      {a.needs_review ? (
                        <span className="shrink-0 text-[11px] font-semibold text-high">
                          Needs review
                        </span>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </Section>
            ) : null}

            <p className="px-1 text-xs text-ink-faint">
              AI analysis confidence: {Math.round(analysis.confidence * 100)}% · Summaries never replace the original —
              full email below.
            </p>
          </>
        ) : (
          <div className="border-y border-line bg-high-soft p-4 text-sm text-ink">
            {fallbackAnalysisNotice()}
          </div>
        )}

        {/* Full original email — always accessible */}
        {original ? (
          <Section title="Full original email">
            <p className="mb-2 text-xs text-ink-faint">
              {original.from} · {formatFullDate(original.sentAt)}
            </p>
            <p className="whitespace-pre-wrap">{original.body}</p>
          </Section>
        ) : null}

        {/* Thread history */}
        {priorMessages.length > 0 ? (
          <Section title={`Earlier in this thread (${priorMessages.length})`}>
            <ul className="space-y-4">
              {priorMessages.map((m) => (
                <li key={m.id} className="border-l-2 border-line pl-3">
                  <p className="text-xs font-semibold text-ink-soft">
                    {m.from} <span className="font-normal text-ink-faint">· {formatFullDate(m.sentAt)}</span>
                  </p>
                  <p className="mt-1 whitespace-pre-wrap text-sm">{m.body}</p>
                </li>
              ))}
            </ul>
          </Section>
        ) : null}
      </div>

      {/* Sticky bottom actions */}
      <div className="fixed inset-x-0 bottom-0 z-10 flex items-center gap-2 border-t border-line bg-card px-4 pb-[max(env(safe-area-inset-bottom),12px)] pt-3 lg:absolute lg:rounded-b-lg">
        <button
          onClick={onReply}
          className="min-h-12 flex-1 rounded-lg bg-accent text-[15px] font-semibold text-white active:opacity-80"
        >
          Draft Reply
        </button>
        <button
          onClick={() => {
            inbox.markDone(email.id);
            onAction?.("Marked done");
            onClose();
          }}
          className="min-h-12 rounded-lg bg-accent-soft px-5 text-sm font-semibold text-accent active:opacity-80"
        >
          Done
        </button>
        <MoreMenu email={email} onAction={onAction} />
      </div>
    </div>
  );
}
