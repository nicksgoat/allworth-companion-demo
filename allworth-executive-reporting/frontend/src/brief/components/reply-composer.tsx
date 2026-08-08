

import { useEffect, useState } from "react";
import { getAnalysis } from "../analysis";
import { fetchLiveDraft, saveLiveDraft, sendLiveReply } from "../briefApi";
import { generateReply, refineReply, type Refinement } from "../replyGenerator";
import { useInbox } from "../store";
import { REPLY_INTENT_LABELS, TONE_LABELS, type ReplyIntent, type Tone } from "../types";
import type { ExecutiveEmail } from "../types";

const ALL_INTENTS = Object.keys(REPLY_INTENT_LABELS) as ReplyIntent[];
const ALL_TONES = Object.keys(TONE_LABELS) as Tone[];

export function ReplyComposer({
  email,
  onClose,
  onSaved,
}: {
  email: ExecutiveEmail;
  onClose: () => void;
  onSaved: (label: string) => void;
}) {
  const inbox = useInbox();
  const analysis = getAnalysis(email);
  const suggested = new Set(analysis?.suggested_reply_intents ?? []);

  const [intent, setIntent] = useState<ReplyIntent | null>(null);
  const [tone, setTone] = useState<Tone>("executive");
  const [draft, setDraft] = useState<string>(inbox.overlays[email.id]?.savedDraft ?? "");
  const [generating, setGenerating] = useState(false);
  // Send is a two-step, explicit action: the first click arms confirmation,
  // the second actually sends. Never auto-sends; resets if the draft changes.
  const [confirmingSend, setConfirmingSend] = useState(false);
  const [sending, setSending] = useState(false);
  const hasDraft = draft.trim().length > 0;
  const canSend = inbox.mode === "live";

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Live mode calls Claude via /brief/api/draft-reply; mock mode (or any live
  // failure) uses the local deterministic generator so the flow never stalls.
  const generate = (nextIntent: ReplyIntent, nextTone: Tone = tone) => {
    setGenerating(true);
    if (inbox.mode === "live") {
      fetchLiveDraft(email.id, nextIntent, nextTone)
        .then((live) => {
          setDraft(live ?? generateReply(email, analysis, nextIntent, nextTone));
        })
        .finally(() => setGenerating(false));
      return;
    }
    setTimeout(() => {
      setDraft(generateReply(email, analysis, nextIntent, nextTone));
      setGenerating(false);
    }, 350);
  };

  const refine = (r: Refinement) => {
    if (!hasDraft) return;
    setConfirmingSend(false);
    setDraft(refineReply(draft, r, email, analysis));
  };

  // Two-step guarded send. First press arms confirmation; second actually
  // sends via Graph. Only reachable in live mode, only from this explicit
  // control — never automatically.
  const send = () => {
    if (!hasDraft || sending) return;
    if (!confirmingSend) {
      setConfirmingSend(true);
      return;
    }
    setSending(true);
    void sendLiveReply(email.id, draft).then((err) => {
      setSending(false);
      setConfirmingSend(false);
      if (err) {
        onSaved(`Not sent — ${err}`);
        return;
      }
      inbox.markDone(email.id);
      onSaved(`Reply sent to ${email.senderName}`);
      onClose();
    });
  };

  const save = () => {
    // Always keep a local copy; in live mode also try to persist as an Outlook
    // draft (falls back to local-only when Mail.ReadWrite isn't granted).
    inbox.saveDraft(email.id, draft);
    if (inbox.mode === "live") {
      void saveLiveDraft(email.id, draft).then((where) => {
        onSaved(
          where === "outlook"
            ? "Draft saved to Outlook — nothing sent"
            : "Draft saved for review — nothing sent",
        );
      });
    } else {
      onSaved("Draft saved — nothing has been sent");
    }
    onClose();
  };

  const pill = (active: boolean) =>
    `min-h-11 rounded-lg px-4 text-sm font-semibold transition-colors ${
      active ? "bg-accent text-white" : "bg-card text-ink-soft ring-1 ring-line active:bg-line"
    }`;

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-ink/40 sm:items-center sm:p-4" role="dialog" aria-modal="true" aria-label="Reply composer">
      <div className="flex max-h-full w-full flex-col overflow-hidden bg-paper animate-sheet-up sm:max-h-[90vh] sm:max-w-2xl sm:rounded-lg sm:shadow-md">
        <header className="flex items-center gap-3 border-b border-line bg-card px-4 py-3">
          <button
            onClick={onClose}
            aria-label="Close composer"
            className="flex min-h-11 min-w-11 items-center justify-center rounded-lg text-xl text-ink-soft hover:bg-paper"
          >
            ✕
          </button>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-bold">Reply to {email.senderName}</p>
            <p className="truncate text-xs text-ink-faint">{email.subject}</p>
          </div>
        </header>

        <div className="flex-1 space-y-5 overflow-y-auto px-4 py-4">
          <section>
            <h3 className="text-sm font-bold">What do you want to do?</h3>
            <div className="mt-2 grid grid-cols-2 gap-2">
              {ALL_INTENTS.map((i) => (
                <button
                  key={i}
                  onClick={() => {
                    setIntent(i);
                    generate(i);
                  }}
                  className={`${pill(intent === i)} relative text-left px-4`}
                >
                  {REPLY_INTENT_LABELS[i]}
                  {suggested.has(i) && intent !== i ? (
                    <span className="absolute right-2 top-1/2 -translate-y-1/2 text-[10px] font-bold uppercase text-accent">
                      AI
                    </span>
                  ) : null}
                </button>
              ))}
            </div>
            {suggested.size > 0 ? (
              <p className="mt-1.5 text-xs text-ink-faint">Options marked AI are suggested for this email.</p>
            ) : null}
          </section>

          <section>
            <h3 className="text-sm font-bold">Tone</h3>
            <div className="no-scrollbar -mx-4 mt-2 flex gap-2 overflow-x-auto px-4">
              {ALL_TONES.map((t) => (
                <button
                  key={t}
                  onClick={() => {
                    setTone(t);
                    if (intent) generate(intent, t);
                  }}
                  className={`${pill(tone === t)} shrink-0`}
                >
                  {TONE_LABELS[t]}
                </button>
              ))}
            </div>
          </section>

          <section>
            <h3 className="text-sm font-bold">Your reply</h3>
            <textarea
              value={generating ? "Generating…" : draft}
              onChange={(e) => {
                setConfirmingSend(false);
                setDraft(e.target.value);
              }}
              disabled={generating}
              rows={8}
              placeholder="Choose an intent above to generate a draft, or write your own."
              className="mt-2 w-full rounded-lg border border-line bg-card p-4 text-[15px] leading-relaxed text-ink outline-none placeholder:text-ink-faint focus:border-accent disabled:text-ink-faint"
            />
            <div className="no-scrollbar -mx-4 mt-2 flex gap-2 overflow-x-auto px-4">
              {(
                [
                  ["shorter", "Make shorter"],
                  ["warmer", "Make warmer"],
                  ["more_direct", "More direct"],
                  ["add_context", "Add context"],
                ] as [Refinement, string][]
              ).map(([r, label]) => (
                <button
                  key={r}
                  onClick={() => refine(r)}
                  disabled={!hasDraft || generating}
                  className="min-h-11 shrink-0 rounded-lg bg-card px-4 text-sm font-semibold text-ink-soft ring-1 ring-line active:bg-line disabled:opacity-40"
                >
                  {label}
                </button>
              ))}
              <button
                onClick={() => intent && generate(intent)}
                disabled={!intent || generating}
                className="min-h-11 shrink-0 rounded-lg bg-card px-4 text-sm font-semibold text-ink-soft ring-1 ring-line active:bg-line disabled:opacity-40"
              >
                ↻ Regenerate
              </button>
            </div>
          </section>

          <p className="text-xs text-ink-faint">
            {canSend
              ? "Nothing is sent until you press Send and confirm. This app never sends automatically."
              : "Drafts are saved for your review — this app never sends email automatically."}
          </p>
        </div>

        <div className="border-t border-line bg-card px-4 pb-[max(env(safe-area-inset-bottom),12px)] pt-3">
          {confirmingSend ? (
            <p className="mb-2 text-center text-xs font-semibold text-critical">
              Send this reply to {email.senderName} &lt;{email.senderEmail}&gt;? Press Confirm send.
            </p>
          ) : null}
          <div className="flex items-center gap-2">
            <button
              onClick={save}
              disabled={!hasDraft || generating || sending}
              className="min-h-12 flex-1 rounded-lg bg-card text-[15px] font-semibold text-ink ring-1 ring-line active:bg-line disabled:opacity-40"
            >
              Save draft
            </button>
            {canSend ? (
              <button
                onClick={send}
                disabled={!hasDraft || generating || sending}
                className={`min-h-12 flex-1 rounded-lg text-[15px] font-semibold text-white active:opacity-80 disabled:opacity-40 ${
                  confirmingSend ? "bg-critical" : "bg-accent"
                }`}
              >
                {sending ? "Sending…" : confirmingSend ? "Confirm send" : "Send"}
              </button>
            ) : null}
            <button
              onClick={confirmingSend ? () => setConfirmingSend(false) : onClose}
              disabled={sending}
              className="min-h-12 rounded-lg px-4 text-sm font-semibold text-ink-soft disabled:opacity-40"
            >
              {confirmingSend ? "Cancel" : "Discard"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
