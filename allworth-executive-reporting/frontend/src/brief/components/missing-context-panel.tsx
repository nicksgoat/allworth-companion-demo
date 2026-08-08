import type { EmailAnalysis } from "../types";

/**
 * "What you might miss" — deliberately styled apart from the summary so
 * compression never quietly hides information.
 */
export function MissingContextPanel({ analysis }: { analysis: EmailAnalysis }) {
  if (analysis.missing_context.length === 0 && analysis.risks.length === 0) return null;

  return (
    <section className="rounded-2xl border-l-4 border-miss bg-miss-soft p-4" aria-label="What you might miss">
      <h3 className="flex items-center gap-2 text-sm font-bold text-miss">
        <span aria-hidden>👁</span> What you might miss
      </h3>
      {analysis.missing_context.length > 0 ? (
        <ul className="mt-2 space-y-1.5">
          {analysis.missing_context.map((item) => (
            <li key={item} className="flex gap-2 text-sm leading-snug text-ink">
              <span className="mt-0.5 shrink-0 text-miss">•</span>
              {item}
            </li>
          ))}
        </ul>
      ) : null}
      {analysis.risks.length > 0 ? (
        <div className="mt-3 border-t border-miss/20 pt-3">
          <h4 className="text-xs font-bold uppercase tracking-wide text-critical">Risks</h4>
          <ul className="mt-1.5 space-y-1.5">
            {analysis.risks.map((r) => (
              <li key={r} className="flex gap-2 text-sm leading-snug text-ink">
                <span className="mt-0.5 shrink-0 text-critical">⚠</span>
                {r}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
