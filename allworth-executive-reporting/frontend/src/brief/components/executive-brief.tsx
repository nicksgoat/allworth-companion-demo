

import { greeting, isDeadlineToday } from "../format";
import { getAnalysis } from "../analysis";
import type { ExecutiveEmail } from "../types";

function plural(n: number, singular: string, pluralWord: string): string {
  return n === 1 ? singular : pluralWord;
}

export function ExecutiveBrief({ emails }: { emails: ExecutiveEmail[] }) {
  const decisions = emails.filter((e) => e.category === "needs_decision").length;
  const responses = emails.filter((e) => e.category === "needs_response").length;
  const deadlinesToday = emails.filter((e) => isDeadlineToday(e.deadline)).length;
  const risks = emails.filter((e) => {
    const a = getAnalysis(e);
    return a !== null && a.risks.length > 0 && e.priority === "critical";
  }).length;

  const lines: { count: number; label: string; tone: string }[] = [
    { count: decisions, label: plural(decisions, "needs your decision", "need your decision"), tone: "text-ink" },
    { count: responses, label: plural(responses, "needs your response", "need your response"), tone: "text-ink" },
    { count: deadlinesToday, label: plural(deadlinesToday, "deadline today", "deadlines today"), tone: "text-high" },
    { count: risks, label: plural(risks, "potential risk", "potential risks"), tone: "text-critical" },
  ];

  return (
    <section className="rounded-2xl bg-card p-5 shadow-sm ring-1 ring-line">
      <h1 className="text-xl font-bold tracking-tight">{greeting()}</h1>
      <ul className="mt-3 space-y-1.5">
        {lines
          .filter((l) => l.count > 0)
          .map((l) => (
            <li key={l.label} className={`flex items-baseline gap-2 text-[15px] ${l.tone}`}>
              <span className="min-w-5 font-bold tabular-nums">{l.count}</span>
              <span className="font-medium">{l.label}</span>
            </li>
          ))}
        {lines.every((l) => l.count === 0) ? (
          <li className="text-[15px] text-ink-faint">Nothing needs your attention right now.</li>
        ) : null}
      </ul>
    </section>
  );
}
