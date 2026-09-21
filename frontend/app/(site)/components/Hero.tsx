import type { LandingData } from "@/app/lib/landing";
import { BathymetryField } from "./BathymetryField";
import { Cta, Kicker } from "./primitives";

function StatStrip({ totals }: { totals: LandingData["totals"] }) {
  const stats = [
    { value: totals.papers, label: "papers indexed" },
    { value: totals.domains, label: "research domains" },
    { value: totals.papersWithFields, label: "with fields extracted" },
    { value: totals.sourcedValues, label: "values with a source excerpt" },
  ];
  return (
    <dl className="mt-10 grid max-w-2xl grid-cols-2 gap-x-6 gap-y-5 border-t border-rule pt-6 sm:grid-cols-4 sm:gap-x-5">
      {stats.map((stat) => (
        <div key={stat.label}>
          <dt className="sr-only">{stat.label}</dt>
          <dd>
            <span className="block text-2xl font-semibold text-ink-900 sm:text-3xl">{stat.value}</span>
            <span className="mt-1 block text-sm leading-snug text-ink-400">{stat.label}</span>
          </dd>
        </div>
      ))}
    </dl>
  );
}

export function Hero({ data }: { data: LandingData }) {
  return (
    <section className="relative isolate overflow-hidden">
      <div aria-hidden className="sounding-grid absolute inset-0 -z-10" />

      <div className="mx-auto grid max-w-7xl grid-cols-[minmax(0,1fr)] gap-10 px-5 pb-14 pt-12 sm:gap-14 sm:px-8 sm:pb-20 sm:pt-20 lg:min-h-[calc(100vh-4rem)] lg:grid-cols-[minmax(0,0.9fr)_minmax(32rem,1.1fr)] lg:items-center lg:gap-16 lg:py-20">
        <div>
          <Kicker>Ocean Research Hub</Kicker>

          <h1 className="mt-5 font-display text-5xl font-semibold leading-[0.98] tracking-[-0.055em] text-ink-900 sm:text-6xl lg:text-7xl">
            Ocean AI research,
            <br />
            <span className="text-tide-600">structured.</span>
          </h1>

          <p className="mt-7 max-w-xl text-lg leading-relaxed text-ink-600 sm:text-xl">
            Explore how models, datasets and experiments shape the future of ocean science.
          </p>
          <p className="mt-4 max-w-xl text-base leading-relaxed text-ink-400 sm:text-lg">
            Literature becomes structured research knowledge, with extracted values kept separate
            from their stored source excerpts and audit status.
          </p>

          <div className="mt-9 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
            <Cta href="/explore">Enter the research workspace</Cta>
            <Cta href="#extraction" variant="ghost">
              See an extraction
            </Cta>
          </div>

          {data.status !== "unavailable" && data.status !== "empty" && <StatStrip totals={data.totals} />}
        </div>

        <figure className="relative overflow-hidden rounded-lg border border-rule bg-sheet-2">
          <p className="absolute right-4 top-4 z-10 text-sm font-medium text-ink-400">
            Scientific illustration
          </p>
          <BathymetryField className="mx-auto w-full max-w-[19rem] sm:max-w-[32rem] lg:max-w-none" />
          <figcaption className="grid border-t border-rule sm:grid-cols-3">
            {[
              ["Paper evidence", "Stored excerpt and locator"],
              ["Structured record", "Value, provenance and status"],
              ["Corpus signal", "Counts that open back to papers"],
            ].map(([title, copy], index) => (
              <div
                key={title}
                className={`px-4 py-3 sm:px-5 sm:py-4 ${index > 0 ? "border-t border-rule sm:border-l sm:border-t-0" : ""}`}
              >
                <p className="text-sm font-semibold text-ink-900">{title}</p>
                <p className="mt-1 text-sm leading-snug text-ink-400">{copy}</p>
              </div>
            ))}
          </figcaption>
        </figure>
      </div>
    </section>
  );
}
