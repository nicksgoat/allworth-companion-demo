

import { useEffect, useMemo, useState } from "react";
import { formatDeadline } from "../format";
import { InboxProvider, useInbox } from "../store";
import { CATEGORY_LABELS, type ExecutiveEmail } from "../types";
import { CategoryTabs, VIEWS, viewMatches, type ViewKey } from "./category-tabs";
import { EmailCard } from "./email-card";
import { EmailDetailSheet } from "./email-detail-sheet";
import { ExecutiveBrief } from "./executive-brief";
import { ReplyComposer } from "./reply-composer";
import { EmptyState, LoadingState } from "./states";

const PRIORITY_ORDER = { critical: 0, high: 1, medium: 2, low: 3 } as const;

function sortEmails(list: ExecutiveEmail[]): ExecutiveEmail[] {
  return [...list].sort(
    (a, b) =>
      PRIORITY_ORDER[a.priority] - PRIORITY_ORDER[b.priority] ||
      new Date(b.receivedAt).getTime() - new Date(a.receivedAt).getTime()
  );
}

function Toast({ message }: { message: string }) {
  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-24 z-[60] flex justify-center px-4">
      <p className="rounded-lg bg-accent px-5 py-2.5 text-sm font-semibold text-white shadow-sm">{message}</p>
    </div>
  );
}

function DashboardInner() {
  const inbox = useInbox();
  const [view, setView] = useState<ViewKey>("needs_you");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [replyId, setReplyId] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [showSnoozed, setShowSnoozed] = useState(false);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 2400);
    return () => clearTimeout(t);
  }, [toast]);

  const now = Date.now();
  const active = useMemo(
    () =>
      inbox.emails.filter(
        (e) =>
          !inbox.overlays[e.id]?.archived &&
          !(e.snoozedUntil && new Date(e.snoozedUntil).getTime() > now)
      ),
    [inbox.emails, inbox.overlays, now]
  );
  const snoozed = inbox.emails.filter(
    (e) => e.snoozedUntil && new Date(e.snoozedUntil).getTime() > now && !inbox.overlays[e.id]?.archived
  );

  const counts = useMemo(() => {
    const c = {} as Record<ViewKey, number>;
    for (const v of VIEWS) c[v.key] = active.filter((e) => viewMatches(v.key, e)).length;
    return c;
  }, [active]);

  const visible = sortEmails(active.filter((e) => viewMatches(view, e)));
  const selected = inbox.emails.find((e) => e.id === selectedId) ?? null;
  const replying = inbox.emails.find((e) => e.id === replyId) ?? null;

  const notify = (label: string) => setToast(label);

  if (!inbox.ready) {
    return (
      <div className="mx-auto max-w-lg lg:max-w-6xl">
        <LoadingState />
      </div>
    );
  }

  // Live mail is enabled but this session has no usable Graph token (missing or
  // expired) or the mailbox fetch failed. Never show demo data here — prompt a
  // reconnect so the real inbox is never confused with sample data.
  if (inbox.reconnect) {
    const expired = inbox.reconnect === "load_failed";
    return (
      <div className="mx-auto flex min-h-dvh max-w-lg flex-col items-center justify-center px-6 text-center">
        <h1 className="text-xl font-bold">{expired ? "Reconnect your mailbox" : "Connect your mailbox"}</h1>
        <p className="mt-2 text-sm text-ink-soft">
          {expired
            ? "Your secure mail session expired. Sign in again to reload your live inbox."
            : "Sign in with Microsoft to load your live inbox. Your mail is read securely and never leaves the app."}
        </p>
        <button
          onClick={() => {
            window.location.href = "/.auth/login/aad?post_login_redirect_uri=/brief";
          }}
          className="mt-6 min-h-12 rounded-lg bg-accent px-6 text-[15px] font-semibold text-white active:opacity-80"
        >
          Sign in with Microsoft
        </button>
        <p className="mt-4 text-xs text-ink-faint">No sample data is shown — this is your real mailbox only.</p>
      </div>
    );
  }

  // Group the "Needs You" view into decision vs response sections.
  const groups =
    view === "needs_you"
      ? (["needs_decision", "needs_response"] as const).map((cat) => ({
          label: CATEGORY_LABELS[cat],
          emails: visible.filter((e) => e.category === cat),
        }))
      : [{ label: null as string | null, emails: visible }];

  const list = (
    <div className="space-y-3">
      <ExecutiveBrief emails={active} />
      <CategoryTabs active={view} counts={counts} onSelect={setView} />

      {visible.length === 0 ? (
        <EmptyState
          title={view === "done" ? "Nothing completed yet" : "All clear"}
          hint={view === "done" ? "Items you mark done will appear here." : "Nothing in this category right now."}
        />
      ) : (
        groups.map((g) =>
          g.emails.length === 0 ? null : (
            <div key={g.label ?? "all"} className="space-y-3">
              {g.label ? (
                <h2 className="px-1 pt-1 text-xs font-bold uppercase tracking-wide text-ink-faint">
                  {g.label} · {g.emails.length}
                </h2>
              ) : null}
              {g.emails.map((e) => (
                <EmailCard
                  key={e.id}
                  email={e}
                  onReview={() => setSelectedId(e.id)}
                  onReply={() => setReplyId(e.id)}
                  onAction={notify}
                />
              ))}
            </div>
          )
        )
      )}

      {snoozed.length > 0 ? (
        <div className="pt-1">
          <button
            onClick={() => setShowSnoozed((s) => !s)}
            className="min-h-11 w-full rounded-lg bg-card px-4 text-left text-sm font-semibold text-ink-soft ring-1 ring-line"
          >
            Snoozed · {snoozed.length} {showSnoozed ? "▾" : "▸"}
          </button>
          {showSnoozed ? (
            <ul className="mt-2 space-y-2">
              {snoozed.map((e) => (
                <li key={e.id} className="flex items-center gap-3 border-b border-line bg-card px-4 py-3">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold">{e.subject}</p>
                    <p className="text-xs text-ink-faint">
                      {e.senderName} · returns {e.snoozedUntil ? formatDeadline(e.snoozedUntil) : ""}
                    </p>
                  </div>
                  <button
                    onClick={() => {
                      inbox.unsnooze(e.id);
                      notify("Unsnoozed");
                    }}
                    className="min-h-11 shrink-0 rounded-lg bg-accent-soft px-4 text-sm font-semibold text-accent"
                  >
                    Unsnooze
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}

      <p className="px-1 pb-4 pt-2 text-center text-xs text-ink-faint">
        {inbox.mode === "live"
          ? "Live mailbox — drafts are saved for review; nothing is ever sent."
          : "Mock mode — sample data only. No mailbox is connected."}
      </p>
    </div>
  );

  return (
    <div className="mx-auto min-h-dvh max-w-lg px-4 pb-8 pt-[max(env(safe-area-inset-top),16px)] lg:grid lg:h-dvh lg:max-w-7xl lg:grid-cols-[minmax(380px,460px)_1fr] lg:gap-5 lg:overflow-hidden lg:px-6 lg:pt-6">
      {/* List column */}
      <div className="lg:overflow-y-auto lg:pb-8 lg:pr-1">{list}</div>

      {/* Desktop detail column */}
      <div className="hidden lg:block lg:h-full lg:overflow-hidden lg:pb-8">
        {selected ? (
          <EmailDetailSheet
            key={selected.id}
            email={selected}
            onClose={() => setSelectedId(null)}
            onReply={() => setReplyId(selected.id)}
            onAction={notify}
          />
        ) : (
          <div className="flex h-full items-center justify-center rounded-lg border border-dashed border-line text-sm text-ink-faint">
            Select an email to review it here
          </div>
        )}
      </div>

      {/* Mobile detail sheet */}
      {selected ? (
        <div className="lg:hidden">
          <EmailDetailSheet
            key={selected.id}
            email={selected}
            onClose={() => setSelectedId(null)}
            onReply={() => setReplyId(selected.id)}
            onAction={notify}
          />
        </div>
      ) : null}

      {replying ? (
        <ReplyComposer key={replying.id} email={replying} onClose={() => setReplyId(null)} onSaved={notify} />
      ) : null}

      {toast ? <Toast message={toast} /> : null}
    </div>
  );
}

export function Dashboard() {
  return (
    <InboxProvider>
      <DashboardInner />
    </InboxProvider>
  );
}
