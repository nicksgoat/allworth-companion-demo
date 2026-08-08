export function LoadingState() {
  return (
    <div className="space-y-3 px-4 py-6" aria-busy="true" aria-label="Loading inbox">
      <div className="h-24 animate-pulse rounded-2xl bg-line" />
      <div className="h-10 animate-pulse rounded-full bg-line" />
      {[0, 1, 2].map((i) => (
        <div key={i} className="h-36 animate-pulse rounded-2xl bg-line" />
      ))}
    </div>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-line bg-card px-6 py-14 text-center">
      <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-accent-soft text-xl">✓</div>
      <p className="text-sm font-semibold text-ink">{title}</p>
      {hint ? <p className="mt-1 text-sm text-ink-faint">{hint}</p> : null}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="rounded-2xl border border-critical/20 bg-critical-soft px-5 py-6 text-center">
      <p className="text-sm font-semibold text-critical">Something went wrong</p>
      <p className="mt-1 text-sm text-ink-soft">{message}</p>
      {onRetry ? (
        <button
          onClick={onRetry}
          className="mt-4 min-h-11 rounded-full bg-critical px-5 text-sm font-semibold text-white"
        >
          Try again
        </button>
      ) : null}
    </div>
  );
}
