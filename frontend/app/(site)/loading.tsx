/** Shown while the landing aggregates the corpus server-side. */
export default function Loading() {
  return (
    <div className="mx-auto max-w-6xl px-5 py-24 sm:px-8" role="status" aria-live="polite">
      <p className="font-mono text-[0.6875rem] uppercase tracking-[0.22em] text-tide-500">
        Ocean × artificial intelligence
      </p>
      <p className="mt-4 font-display text-3xl text-ink-900 sm:text-5xl">Ocean AI research, structured.</p>
      <p className="mt-6 text-[0.9375rem] text-ink-400">Counting the corpus…</p>
    </div>
  );
}
