

import type { Category, ExecutiveEmail } from "../types";

export type ViewKey = "needs_you" | "important" | "waiting" | "delegatable" | "low_priority" | "done";

export const VIEWS: { key: ViewKey; label: string }[] = [
  { key: "needs_you", label: "Needs You" },
  { key: "important", label: "Important" },
  { key: "waiting", label: "Waiting" },
  { key: "delegatable", label: "Delegatable" },
  { key: "low_priority", label: "Low Priority" },
  { key: "done", label: "Done" },
];

export function viewMatches(view: ViewKey, email: ExecutiveEmail): boolean {
  if (view === "done") return email.completed;
  if (email.completed) return false;
  const byCategory: Record<Exclude<ViewKey, "done" | "needs_you">, Category> = {
    important: "important",
    waiting: "waiting",
    delegatable: "delegatable",
    low_priority: "low_priority",
  };
  if (view === "needs_you") return email.category === "needs_decision" || email.category === "needs_response";
  return email.category === byCategory[view];
}

export function CategoryTabs({
  active,
  counts,
  onSelect,
}: {
  active: ViewKey;
  counts: Record<ViewKey, number>;
  onSelect: (v: ViewKey) => void;
}) {
  return (
    <nav aria-label="Email categories" className="no-scrollbar -mx-4 flex gap-5 overflow-x-auto border-b border-line px-4 lg:mx-0 lg:px-0">
      {VIEWS.map((v) => {
        const isActive = v.key === active;
        return (
          <button
            key={v.key}
            onClick={() => onSelect(v.key)}
            aria-pressed={isActive}
            className={`flex min-h-11 shrink-0 items-center gap-1.5 border-b-2 px-1 text-sm font-semibold transition-colors ${
              isActive ? "border-accent text-accent" : "border-transparent text-ink-soft hover:text-ink"
            }`}
          >
            {v.label}
            <span className="tabular-nums text-ink-faint">{counts[v.key]}</span>
          </button>
        );
      })}
    </nav>
  );
}
