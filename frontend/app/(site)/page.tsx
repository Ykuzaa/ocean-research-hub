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
        <div className="mx-auto max-w-6xl px-5 py-16 text-center sm:px-8 sm:py-24">
          <Kicker>Start reading</Kicker>
          <h2 className="mx-auto mt-4 max-w-2xl font-display text-3xl font-normal leading-[1.15] tracking-[-0.01em] text-ink-900 sm:text-[2.75rem]">
            The workspace holds the whole corpus — every field, every source sentence.
          </h2>
          <div className="mt-9 flex flex-wrap justify-center gap-3">
            <Cta href="/explore">Enter the research workspace</Cta>
          </div>
        </div>
      </section>
    </>
  );
}
