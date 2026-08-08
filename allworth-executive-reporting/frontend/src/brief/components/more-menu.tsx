

import { useEffect, useRef, useState } from "react";
import { DELEGATE_OPTIONS } from "../mockData";
import { useInbox } from "../store";
import type { ExecutiveEmail } from "../types";

function snoozeUntil(kind: "later" | "tomorrow" | "next_week"): string {
  const t = new Date();
  if (kind === "later") t.setHours(t.getHours() + 3);
  if (kind === "tomorrow") {
    t.setDate(t.getDate() + 1);
    t.setHours(8, 0, 0, 0);
  }
  if (kind === "next_week") {
    t.setDate(t.getDate() + 7);
    t.setHours(8, 0, 0, 0);
  }
  return t.toISOString();
}

export function MoreMenu({
  email,
  align = "right",
  onAction,
}: {
  email: ExecutiveEmail;
  align?: "left" | "right";
  onAction?: (label: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [submenu, setSubmenu] = useState<"snooze" | "delegate" | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  const inbox = useInbox();
  const important = Boolean(inbox.overlays[email.id]?.important);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
        setSubmenu(null);
      }
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const act = (label: string, fn: () => void) => {
    fn();
    setOpen(false);
    setSubmenu(null);
    onAction?.(label);
  };

  const itemCls =
    "flex w-full min-h-11 items-center px-4 text-left text-sm font-medium text-ink hover:bg-paper active:bg-line";

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={(e) => {
          e.stopPropagation();
          setOpen((o) => !o);
          setSubmenu(null);
        }}
        aria-haspopup="menu"
        aria-expanded={open}
        className="flex min-h-11 min-w-11 items-center justify-center rounded-full text-lg font-bold text-ink-faint hover:bg-paper"
      >
        ⋯
      </button>
      {open ? (
        <div
          role="menu"
          className={`absolute z-30 mt-1 w-56 overflow-hidden rounded-xl bg-card py-1 shadow-lg ring-1 ring-line ${
            align === "right" ? "right-0" : "left-0"
          } bottom-full mb-1`}
          onClick={(e) => e.stopPropagation()}
        >
          {submenu === null ? (
            <>
              <button className={itemCls} onClick={() => act("Marked done", () => inbox.markDone(email.id))}>
                ✓&nbsp; Mark done
              </button>
              <button className={itemCls} onClick={() => setSubmenu("snooze")}>
                🕐&nbsp; Snooze…
              </button>
              <button className={itemCls} onClick={() => setSubmenu("delegate")}>
                👥&nbsp; Delegate…
              </button>
              <button
                className={itemCls}
                onClick={() => act(important ? "Removed important flag" : "Marked important", () => inbox.toggleImportant(email.id))}
              >
                {important ? "★" : "☆"}&nbsp; {important ? "Unmark important" : "Mark important"}
              </button>
              <button className={itemCls} onClick={() => act("Archived", () => inbox.archive(email.id))}>
                🗄&nbsp; Archive
              </button>
              <button className={itemCls} onClick={() => act("No action needed", () => inbox.markDone(email.id))}>
                ∅&nbsp; No action needed
              </button>
            </>
          ) : submenu === "snooze" ? (
            <>
              <p className="px-4 py-2 text-xs font-semibold uppercase tracking-wide text-ink-faint">Snooze until</p>
              <button className={itemCls} onClick={() => act("Snoozed until later today", () => inbox.snooze(email.id, snoozeUntil("later")))}>
                Later today
              </button>
              <button className={itemCls} onClick={() => act("Snoozed until tomorrow", () => inbox.snooze(email.id, snoozeUntil("tomorrow")))}>
                Tomorrow 8 AM
              </button>
              <button className={itemCls} onClick={() => act("Snoozed until next week", () => inbox.snooze(email.id, snoozeUntil("next_week")))}>
                Next week
              </button>
            </>
          ) : (
            <>
              <p className="px-4 py-2 text-xs font-semibold uppercase tracking-wide text-ink-faint">Delegate to</p>
              {DELEGATE_OPTIONS.map((p) => (
                <button key={p.name} className={itemCls} onClick={() => act(`Delegated to ${p.name}`, () => inbox.delegate(email.id, p.name))}>
                  <span>
                    {p.name}
                    <span className="block text-xs font-normal text-ink-faint">{p.role}</span>
                  </span>
                </button>
              ))}
            </>
          )}
        </div>
      ) : null}
    </div>
  );
}
