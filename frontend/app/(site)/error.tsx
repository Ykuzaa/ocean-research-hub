"use client";

/** Landing-level boundary: the page must still say something useful if it throws. */
export default function LandingError({ reset }: { error: Error; reset: () => void }) {
  return (
    <div className="mx-auto max-w-2xl px-5 py-24 sm:px-8">
      <p className="text-base font-medium text-tide-600">Ocean Research Hub</p>
      <h1 className="mt-4 font-display text-4xl font-semibold tracking-[-0.035em] text-ink-900 sm:text-5xl">
        This page could not be built.
      </h1>
      <p className="mt-4 text-base leading-relaxed text-ink-600 sm:text-lg">
        Every figure on the landing is counted from the live corpus, so the page does not render
        placeholder numbers when that fails. Check that the API is running, then try again.
      </p>
      <div className="mt-8 flex flex-wrap gap-3">
        <button
          type="button"
          onClick={reset}
          className="inline-flex w-full items-center justify-center rounded bg-tide-600 px-5 py-3 text-[0.9375rem] font-medium text-white transition hover:bg-tide-500 sm:w-auto"
        >
          Try again
        </button>
        <a
          href="/explore"
          className="inline-flex w-full items-center justify-center rounded border border-rule bg-sheet-2 px-5 py-3 text-[0.9375rem] font-medium text-ink-900 transition hover:border-tide-500 sm:w-auto"
        >
          Go to the workspace
        </a>
      </div>
    </div>
  );
}
