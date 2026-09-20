import { loadLandingData } from "@/app/lib/landing";
import { Hero } from "./components/Hero";
import { QueryPanel } from "./components/QueryPanel";
import { ExtractionPanel } from "./components/ExtractionPanel";
import { IntelligencePanel } from "./components/IntelligencePanel";
import { Cta, Kicker, PartialNotice } from "./components/primitives";

export default async function LandingPage() {
  const data = await loadLandingData();

  return (
    <>
      <Hero data={data} />
      {data.partial && (
        <div className="mx-auto max-w-6xl px-5 pb-6 sm:px-8">
          <PartialNotice partial={data.partial} />
        </div>
      )}
      <QueryPanel data={data} />
      <ExtractionPanel data={data} />
      <IntelligencePanel data={data} />

      <section className="relative isolate overflow-hidden border-t border-rule/60">
        <div aria-hidden className="sounding-grid absolute inset-0 -z-10" />
        <div className="mx-auto max-w-7xl px-5 py-16 text-center sm:px-8 sm:py-20">
          <Kicker>Continue with the evidence</Kicker>
          <h2 className="mx-auto mt-4 max-w-3xl font-display text-4xl font-medium leading-[1.08] tracking-[-0.035em] text-ink-900 sm:text-5xl">
            Move from the public story into the working research corpus.
          </h2>
          <div className="mt-9 flex flex-wrap justify-center gap-3">
            <Cta href="/explore">Browse papers and evidence</Cta>
          </div>
        </div>
      </section>
    </>
  );
}
