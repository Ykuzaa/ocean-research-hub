import type { LandingData } from "@/app/lib/landing";
import { BathymetryField } from "./BathymetryField";
import { Cta, Kicker } from "./primitives";

function StatStrip({ totals }: { totals: LandingData["totals"] }) {
  const stats = [
    { value: totals.papers, label: "papers indexed" },
    { value: totals.domains, label: "research domains" },
    { value: totals.papersWithFields, label: "with fields extracted" },
    { value: totals.sourcedValues, label: "values with a source sentence" },
  ];
  return (
    <dl className="mt-12 grid max-w-xl grid-cols-2 gap-x-6 gap-y-6 border-t border-rule pt-6 sm:grid-cols-4 sm:gap-x-4">
      {stats.map((stat) => (
        <div key={stat.label}>
          <dt className="sr-only">{stat.label}</dt>
          <dd>
            <span className="block text-2xl font-semibold text-ink-900">{stat.value}</span>
            <span className="mt-1 block text-xs leading-snug text-ink-400">{stat.label}</span>
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

      <div className="mx-auto grid max-w-6xl grid-cols-[minmax(0,1fr)] gap-10 px-5 pb-14 pt-12 sm:gap-12 sm:px-8 sm:pb-20 sm:pt-20 lg:pb-24 lg:pt-24 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)] lg:items-center lg:gap-16">
        <div>
          <Kicker>Ocean × artificial intelligence</Kicker>

          <h1 className="mt-5 font-display text-[2.5rem] font-normal leading-[1.05] tracking-[-0.02em] text-ink-900 sm:text-6xl">
            Ocean AI research,
            <br />
            <span className="italic text-tide-600">structured.</span>
          </h1>

          <p className="mt-6 max-w-xl text-base leading-relaxed text-ink-600 sm:text-lg">
            Ocean Research Hub turns Ocean × AI scientific literature into structured,
            evidence-grounded records — models, datasets, experiments and the limitations authors
            report — each value traceable to the sentence and page it was read from. Research-gap
            candidates are the next layer, not a claim we make today.
          </p>

          <div className="mt-9 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
            <Cta href="/explore">Enter the research workspace</Cta>
            <Cta href="#extraction" variant="ghost">
              See an extraction
            </Cta>
          </div>

          {data.status === "ready" && <StatStrip totals={data.totals} />}
        </div>

        <div className="relative lg:pl-4">
          <BathymetryField className="w-full max-w-[16rem] sm:max-w-sm lg:max-w-none" />
          <p className="mt-4 hidden max-w-sm font-mono text-[0.6875rem] sm:block text-[0.6875rem] leading-relaxed text-ink-400 lg:max-w-none">
            Isobaths, two ground tracks, the stations sampled along them.
          </p>
        </div>
      </div>
    </section>
  );
}
