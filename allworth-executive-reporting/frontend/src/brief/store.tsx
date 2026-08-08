

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import type { ExecutiveEmail } from "./types";
import { MOCK_EMAILS } from "./mockData";
import { fetchLiveEmails, getStatus } from "./briefApi";

/**
 * Prototype state layer. All per-email actions (done, snooze, delegate, read,
 * important, saved drafts) are overlays persisted to localStorage, keyed by
 * email id. This abstraction is intentionally narrow so it can later be
 * replaced by API routes backed by a database + Microsoft Graph without
 * touching the components.
 */

export type EmailOverlay = {
  completed?: boolean;
  snoozedUntil?: string;
  delegatedTo?: string;
  important?: boolean;
  read?: boolean;
  archived?: boolean;
  savedDraft?: string;
};

type OverlayMap = Record<string, EmailOverlay>;

const STORAGE_KEY = "exec-inbox-state-v1";

// When live mail is enabled we must NEVER silently show bundled demo data as if
// it were the real inbox. If the Graph token is missing/expired or a live fetch
// fails, we surface a reconnect state instead.
export type ReconnectReason = "no_token" | "load_failed";

type InboxContextValue = {
  ready: boolean;
  mode: "live" | "mock";
  reconnect: ReconnectReason | null;
  emails: ExecutiveEmail[];
  overlays: OverlayMap;
  markDone: (id: string, done?: boolean) => void;
  snooze: (id: string, untilIso: string) => void;
  unsnooze: (id: string) => void;
  delegate: (id: string, to: string) => void;
  markRead: (id: string) => void;
  toggleImportant: (id: string) => void;
  archive: (id: string) => void;
  saveDraft: (id: string, draft: string) => void;
};

const InboxContext = createContext<InboxContextValue | null>(null);

function applyOverlay(email: ExecutiveEmail, o: EmailOverlay | undefined): ExecutiveEmail {
  if (!o) return email;
  return {
    ...email,
    completed: o.completed ?? email.completed,
    snoozedUntil: o.snoozedUntil ?? email.snoozedUntil,
    delegatedTo: o.delegatedTo ?? email.delegatedTo,
    unread: o.read ? false : email.unread,
  };
}

export function InboxProvider({ children }: { children: ReactNode }) {
  const [overlays, setOverlays] = useState<OverlayMap>({});
  // Start empty, not with MOCK_EMAILS — bundled demo data is only ever shown
  // when live mail is genuinely disabled (local/demo), decided below.
  const [baseEmails, setBaseEmails] = useState<ExecutiveEmail[]>([]);
  const [mode, setMode] = useState<"live" | "mock">("mock");
  const [reconnect, setReconnect] = useState<ReconnectReason | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) setOverlays(JSON.parse(raw) as OverlayMap);
    } catch {
      // Corrupt state: start clean rather than crash.
    }

    (async () => {
      try {
        const status = await getStatus();
        if (status.use_live_mail) {
          // Live is enabled → show ONLY the real mailbox. Never fall back to
          // demo data, which would masquerade as the user's inbox.
          if (status.mode === "live") {
            try {
              setBaseEmails(await fetchLiveEmails());
              setMode("live");
            } catch {
              setMode("live");
              setReconnect("load_failed");
            }
          } else {
            // Backend has live enabled but returned mock → no/expired Graph
            // token for this session. Prompt reconnect rather than show demo.
            setMode("live");
            setReconnect(status.graph_token_available ? "load_failed" : "no_token");
          }
        } else {
          // Live mail not enabled (local dev / demo) → bundled sample data.
          setBaseEmails(MOCK_EMAILS);
          setMode("mock");
        }
      } catch {
        setBaseEmails(MOCK_EMAILS);
        setMode("mock");
      } finally {
        setReady(true);
      }
    })();
  }, []);

  useEffect(() => {
    if (!ready) return;
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(overlays));
    } catch {
      // Storage full/unavailable — state stays in memory for the session.
    }
  }, [overlays, ready]);

  const patch = useCallback((id: string, p: EmailOverlay) => {
    setOverlays((prev) => ({ ...prev, [id]: { ...prev[id], ...p } }));
  }, []);

  const value = useMemo<InboxContextValue>(
    () => ({
      ready,
      mode,
      reconnect,
      emails: baseEmails.map((e) => applyOverlay(e, overlays[e.id])),
      overlays,
      markDone: (id, done = true) => patch(id, { completed: done }),
      snooze: (id, untilIso) => patch(id, { snoozedUntil: untilIso }),
      unsnooze: (id) => patch(id, { snoozedUntil: undefined }),
      delegate: (id, to) => patch(id, { delegatedTo: to }),
      markRead: (id) => patch(id, { read: true }),
      toggleImportant: (id) =>
        setOverlays((prev) => ({ ...prev, [id]: { ...prev[id], important: !prev[id]?.important } })),
      archive: (id) => patch(id, { archived: true }),
      saveDraft: (id, draft) => patch(id, { savedDraft: draft }),
    }),
    [ready, mode, reconnect, baseEmails, overlays, patch]
  );

  return <InboxContext.Provider value={value}>{children}</InboxContext.Provider>;
}

export function useInbox(): InboxContextValue {
  const ctx = useContext(InboxContext);
  if (!ctx) throw new Error("useInbox must be used within InboxProvider");
  return ctx;
}
