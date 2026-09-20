import type { LandingData, LimitationTally } from "@/app/lib/landing";
import { Drilldown } from "./Drilldown";
import { MetaChip, Panel, PanelPlaceholder, SectionHeader } from "./primitives";

/**
 * Product preview for evidence-grounded querying.
 *
 * The aggregate is real: it is counted from the structured corpus on every
 * request, and every count opens into the complete set of papers behind it.
 * What is *not* built is the natural-language layer, which the panel says.
 */

/**
 * One tally row. Its count opens through the paginated backend drill-down,
 * rather than shipping every paper record with the landing response.
 */
function TallyRow({ tally, max, of }: { tally: LimitationTally; max: number; of: number }) {
  const share = max > 0 ? Math.max(tally.papers / max, 0.02) : 0;
  return (
    <div className="border-b border-rule/70 py-3 last:border-b-0">
      <div className="grid grid-cols-[minmax(4.5rem,9rem)_minmax(0,1fr)_auto] items-center gap-3 sm:gap-4">
        <span className="truncate text-sm text-ink-600">
          {tally.label}
        </span>
        <span className="h-2.5 min-w-0 bg-sheet-3">
          <span className="block h-full rounded-r-[4px] bg-tide-400" style={{ width: `${share * 100}%` }} />
        </span>
        <span className="flex w-16 items-center justify-end gap-1.5 font-mono text-[0.8125rem] tabular-nums text-ink-900">
          {tally.papers}
          <span className="text-ink-400">/ {of}</span>
        </span>
      </div>
      <div className="sm:pl-[10.5rem]">
        <Drilldown
          path={tally.drilldownPath}
          total={tally.papers}
          initialEvidence={tally.items}
          label={`View ${tally.papers} supporting paper${tally.papers === 1 ? "" : "s"} and exact evidence`}
        />
      </div>
    </div>
  );
}

export function QueryPanel({ data }: { data: LandingData }) {
  const { limitations, totals, status } = data;
  const max = Math.max(1, ...limitations.map((item) => item.papers));
  const visible = limitations.slice(0, 4);
  const remaining = limitations.slice(4);

  return (
    <section id="query" className="scroll-mt-20 border-t border-rule/60 bg-sheet-1">
      <div className="mx-auto max-w-7xl px-5 py-14 sm:px-8 sm:py-20">
        <SectionHeader
          kicker="Ask the literature · Product Preview"
          title="Ask a question. Get an aggregate you can audit."
          lede="Answers are counted over structured records, never generated prose. Open any count to see every paper behind it, and the sentence in each paper the value was read from."
        />

        <Panel className="mt-8 overflow-hidden sm:mt-10">
          <div className="flex items-center gap-3 border-b border-rule px-4 py-4 sm:px-6">
            <span className="font-mono text-tide-500" aria-hidden>
              ›
            </span>
            <p className="min-w-0 flex-1 text-base font-medium leading-relaxed text-ink-900 sm:text-lg">
              What limitation and future-work themes were extracted most often?
            </p>
            <MetaChip>Fixed query</MetaChip>
          </div>

          <div className="p-5 sm:p-6">
            <p className="mb-4 text-[0.9375rem] leading-relaxed text-ink-600">
              Source-linked candidate extractions across the {totals.papersWithFields}{" "}
              papers with extracted fields. Only fields carrying an{" "}
              <span className="font-mono text-[0.8125rem]">AUTHOR_REPORTED_LIMITATION</span> provenance and a
              source excerpt are counted. Their audit status remains visible in every drill-down;
              <span className="font-mono text-[0.8125rem]"> NOT_VERIFIED</span> is not audited evidence.
            </p>
            {limitations.length > 0 ? (
              <div>
                {visible.map((tally) => (
                  <TallyRow key={tally.key} tally={tally} max={max} of={totals.papersWithFields} />
                ))}
                {remaining.length > 0 && (
                  <>
                    <details className="group/more border-b border-rule/70 md:hidden">
                      <summary className="cursor-pointer list-none py-3 text-sm font-medium text-tide-600 [&::-webkit-details-marker]:hidden">
                        <span className="group-open/more:hidden">Show {remaining.length} more families</span>
                        <span className="hidden group-open/more:inline">Show fewer families</span>
                      </summary>
                      {remaining.map((tally) => (
                        <TallyRow key={tally.key} tally={tally} max={max} of={totals.papersWithFields} />
                      ))}
                    </details>
                    <div className="hidden md:block">
                      {remaining.map((tally) => (
                        <TallyRow key={tally.key} tally={tally} max={max} of={totals.papersWithFields} />
                      ))}
                    </div>
                  </>
                )}
              </div>
            ) : (
              <PanelPlaceholder what="This ranking" status={status} />
            )}
          </div>

          <p className="border-t border-rule px-5 py-4 text-sm leading-relaxed text-ink-400 sm:px-6">
            Product Preview. The counts and stored evidence excerpts are live; the natural-language layer that
            will accept arbitrary questions is not built yet, so this panel runs one fixed query.
          </p>
        </Panel>

        <p className="mt-6 max-w-3xl text-sm leading-relaxed text-ink-400">
          Counts describe what this corpus reports, not which method is better. A limitation
          appearing often means many authors chose to state it — nothing more.
        </p>
      </div>
    </section>
  );
}
