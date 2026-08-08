

import { formatDeadline, formatRelativeTime, isDeadlineToday } from "../format";
import { useInbox } from "../store";
import type { ExecutiveEmail } from "../types";
import { PriorityBadge } from "./priority-badge";
import { MoreMenu } from "./more-menu";

export function EmailCard({
  email,
  onReview,
  onReply,
  onAction,
}: {
  email: ExecutiveEmail;
  onReview: () => void;
  onReply: () => void;
  onAction?: (label: string) => void;
}) {
  const inbox = useInbox();
  const important = Boolean(inbox.overlays[email.id]?.important);
  const hasDraft = Boolean(inbox.overlays[email.id]?.savedDraft);

  return (
    <article
      className={`rounded-2xl bg-card p-4 shadow-sm ring-1 ring-line transition-shadow hover:shadow-md ${
        email.unread ? "" : "opacity-80"
      }`}
    >
      <button onClick={onReview} className="block w-full text-left">
        <div className="flex items-center gap-2">
          <PriorityBadge priority={email.priority} />
          {important ? <span className="text-sm text-high">★</span> : null}
          {email.unread ? <span className="h-2 w-2 rounded-full bg-accent" aria-label="Unread" /> : null}
          <span className="ml-auto shrink-0 text-xs text-ink-faint">{formatRelativeTime(email.receivedAt)}</span>
        </div>
        <div className="mt-2 flex items-baseline justify-between gap-2">
          <p className="truncate text-[15px] font-bold">{email.senderName}</p>
          {email.attachmentCount > 0 ? (
            <span className="shrink-0 text-xs text-ink-faint" aria-label={`${email.attachmentCount} attachments`}>
              📎 {email.attachmentCount}
            </span>
          ) : null}
        </div>
        {email.senderRole ? <p className="text-xs text-ink-faint">{email.senderRole}</p> : null}
        <p className="mt-1 truncate text-sm font-semibold text-ink-soft">{email.subject}</p>
        <p className="mt-1.5 line-clamp-2 text-sm leading-snug text-ink-soft">{email.summary}</p>
        <p className="mt-2 text-sm">
          <span className="font-semibold text-accent">Asks:</span>{" "}
          <span className="text-ink-soft">{email.request}</span>
        </p>
        <div className="mt-1.5 flex flex-wrap items-center gap-2">
          {email.deadline ? (
            <span
              className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                isDeadlineToday(email.deadline) ? "bg-critical-soft text-critical" : "bg-low-soft text-ink-soft"
              }`}
            >
              ⏰ {formatDeadline(email.deadline)}
            </span>
          ) : null}
          {email.delegatedTo ? (
            <span className="rounded-full bg-accent-soft px-2 py-0.5 text-xs font-semibold text-accent">
              → {email.delegatedTo}
            </span>
          ) : null}
          {hasDraft ? (
            <span className="rounded-full bg-medium-soft px-2 py-0.5 text-xs font-semibold text-medium">Draft saved</span>
          ) : null}
        </div>
      </button>

      <div className="mt-3 flex items-center gap-2 border-t border-line pt-3">
        <button
          onClick={onReview}
          className="min-h-11 flex-1 rounded-full bg-ink text-sm font-semibold text-white active:opacity-80"
        >
          Review
        </button>
        <button
          onClick={onReply}
          className="min-h-11 flex-1 rounded-full bg-accent-soft text-sm font-semibold text-accent active:opacity-80"
        >
          Reply
        </button>
        <MoreMenu email={email} onAction={onAction} />
      </div>
    </article>
  );
}
