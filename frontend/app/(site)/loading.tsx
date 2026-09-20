/** Shown while the landing aggregates the corpus server-side. */
export default function Loading() {
  return (
    <div className="mx-auto max-w-6xl px-5 py-24 sm:px-8" role="status" aria-live="polite">
      <p className="text-base font-medium text-tide-600">Ocean Research Hub</p>
      <p className="mt-4 font-display text-4xl font-semibold tracking-[-0.04em] text-ink-900 sm:text-5xl">
        Ocean AI research, structured.
      </p>
      <p className="mt-6 text-base text-ink-400">Counting the corpus…</p>
    </div>
  );
}
