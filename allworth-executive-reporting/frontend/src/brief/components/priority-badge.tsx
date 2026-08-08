import type { Priority } from "../types";

const STYLES: Record<Priority, { label: string; cls: string }> = {
  critical: { label: "Critical", cls: "bg-critical-soft text-critical" },
  high: { label: "High", cls: "bg-high-soft text-high" },
  medium: { label: "Medium", cls: "bg-medium-soft text-medium" },
  low: { label: "Low", cls: "bg-low-soft text-low" },
};

export function PriorityBadge({ priority }: { priority: Priority }) {
  const s = STYLES[priority];
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold tracking-wide ${s.cls}`}>
      {s.label}
    </span>
  );
}
