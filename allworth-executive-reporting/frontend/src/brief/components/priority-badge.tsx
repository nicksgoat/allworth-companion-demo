import type { Priority } from "../types";

const STYLES: Record<Priority, { label: string; cls: string }> = {
  critical: { label: "Critical", cls: "text-critical" },
  high: { label: "High", cls: "text-high" },
  medium: { label: "Medium", cls: "text-medium" },
  low: { label: "Low", cls: "text-ink-faint" },
};

export function PriorityBadge({ priority }: { priority: Priority }) {
  const s = STYLES[priority];
  return (
    <span className={`inline-flex items-center text-[11px] font-bold uppercase tracking-wide ${s.cls}`}>
      {s.label}
    </span>
  );
}
