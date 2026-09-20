import type { LandingData, NamedTally, StatusTally, YearBar } from "@/app/lib/landing";
import { Drilldown } from "./Drilldown";
import { Panel, PanelPlaceholder } from "./primitives";

function YearColumns({ years }: { years: YearBar[] }) {
  const max = Math.max(1, ...years.map((bar) => bar.extracted + bar.bibliographic));
  const peak = years.reduce((best, bar) =>
    bar.extracted + bar.bibliographic > best.extracted + best.bibliographic ? bar : best,
  );

  return (
    <figure className="m-0 min-w-0" aria-describedby="year-data">
      <div aria-hidden className="flex h-44 items-end gap-1.5 border-b border-rule sm:h-60 sm:gap-2">
        {years.map((bar) => {
          const total = bar.extracted + bar.bibliographic;
          return (
            <div key={bar.year} className="flex h-full min-w-0 flex-1 flex-col justify-end">
              <span className="mb-1 h-5 text-center font-mono text-sm leading-5 tabular-nums text-ink-900">
                {bar.year === peak.year ? total : ""}
              </span>
              <span
                className="mx-auto flex w-full max-w-7 flex-col justify-end"
                style={{ height: `${(total / max) * 100}%` }}
              >
                {bar.bibliographic > 0 && (
                  <span
                    className="mb-0.5 block bg-mute"
                    style={{ height: `${(bar.bibliographic / total) * 100}%` }}
                  />
                )}
                {bar.extracted > 0 && (
                  <span
                    className="block bg-tide-400"
                    style={{ height: `${(bar.extracted / total) * 100}%` }}
                  />
                )}
              </span>
            </div>
          );
        })}
      </div>
      <div aria-hidden className="mt-2 flex gap-1.5 sm:gap-2">
        {years.map((bar) => (
          <span key={bar.year} className="min-w-0 flex-1 text-center font-mono text-sm tabular-nums text-ink-400">
            <span className="sm:hidden">’{String(bar.year).slice(2)}</span>
            <span className="hidden sm:inline">{bar.year}</span>
          </span>
        ))}
      </div>
      <figcaption className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-sm text-ink-600">
        <span className="flex items-center gap-2"><span aria-hidden className="h-2.5 w-2.5 bg-tide-400" />With extracted fields</span>
        <span className="flex items-center gap-2"><span aria-hidden className="h-2.5 w-2.5 bg-mute" />Bibliography only</span>
      </figcaption>

      <details id="year-data" className="group mt-5 border-t border-rule pt-4">
        <summary className="cursor-pointer list-none text-sm font-medium text-tide-600 hover:underline [&::-webkit-details-marker]:hidden">
          <span className="group-open:hidden">Explore papers by year</span>
          <span className="hidden group-open:inline">Hide papers by year</span>
        </summary>
        <div className="mt-4 space-y-5">
          {years.map((bar) => (
            <div key={bar.year} className="border-l-2 border-rule pl-4">
              <h4 className="text-base font-semibold text-ink-900">{bar.year}</h4>
              {bar.extracted > 0 && (
                <Drilldown path={bar.extractedDrilldownPath} total={bar.extracted} initialPapers={bar.extractedPapers} label={`${bar.extracted} with extracted fields`} />
              )}
              {bar.bibliographic > 0 && (
                <Drilldown path={bar.bibliographicDrilldownPath} total={bar.bibliographic} initialPapers={bar.bibliographicPapers} label={`${bar.bibliographic} bibliography only`} />
              )}
            </div>
          ))}
        </div>
      </details>
    </figure>
  );
}

function StatusLedger({ statuses, total }: { statuses: StatusTally[]; total: number }) {
  return (
    <ul className="divide-y divide-rule">
      {statuses.map((entry) => {
        const exact = total > 0 ? (entry.fields / total) * 100 : 0;
        const share = Math.round(exact);
        const shareLabel = share === 0 && entry.fields > 0 ? "<1%" : `${share}%`;
        return (
          <li key={entry.status} className="py-4 first:pt-0 last:pb-0">
            <div className="flex items-baseline justify-between gap-4">
              <span className="font-mono text-[0.8125rem] text-ink-900">{entry.status}</span>
              <span className="shrink-0 font-mono text-sm tabular-nums text-ink-600">{entry.fields.toLocaleString("en")} · {shareLabel}</span>
            </div>
            <span aria-hidden className="mt-2 block h-1.5 bg-sheet-3">
              <span className="block h-full bg-tide-400" style={{ width: `${entry.fields === 0 ? 0 : Math.max(share, 1)}%` }} />
            </span>
            {entry.fields === 0 ? (
              <p className="mt-2 text-base leading-relaxed text-ink-400">No field carries this status yet.</p>
            ) : (
              <>
                <p className="mt-2 text-base leading-relaxed text-ink-400">{entry.blurb}</p>
                <Drilldown path={entry.drilldownPath} total={entry.fields} initialEvidence={entry.items} label={`Inspect ${entry.fields.toLocaleString("en")} field${entry.fields === 1 ? "" : "s"}`} />
              </>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function NamedList({ title, items, total }: { title: string; items: NamedTally[]; total: number }) {
  return (
    <div>
      <h4 className="text-lg font-semibold text-ink-900">{title}</h4>
      {items.length > 0 ? (
        <ul className="mt-3 divide-y divide-rule">
          {items.map((item) => (
            <li key={item.key} className="py-3 first:pt-0 last:pb-0">
              <div className="flex min-w-0 flex-wrap items-baseline justify-between gap-x-4 gap-y-1 text-base">
                <span className="min-w-0 truncate text-ink-600" title={item.name}>{item.name}</span>
                <span className="shrink-0 font-mono text-sm tabular-nums text-ink-400">{item.papers}/{total} papers</span>
              </div>
              <Drilldown path={item.drilldownPath} total={item.papers} initialEvidence={item.items} label="View papers and exact evidence" />
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-base leading-relaxed text-ink-400">No entry is named in more than one processed paper yet.</p>
      )}
    </div>
  );
}

export function IntelligencePanel({ data }: { data: LandingData }) {
  const { statuses, totals, families, datasets, status, gapPreview } = data;
  const trendFamilies = families.filter((item) => item.papers >= 2);
  const trendDatasets = datasets.filter((item) => item.papers >= 2);
  const hasRepeatedNames = trendFamilies.length > 0 || trendDatasets.length > 0;

  return (
    <section id="intelligence" className="scroll-mt-28 border-t border-rule/60 bg-sheet-1 md:scroll-mt-20">
      <div className="mx-auto max-w-7xl px-5 py-14 sm:px-8 sm:py-20">
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(18rem,0.65fr)] lg:items-end lg:gap-12">
          <div className="min-w-0">
            <p className="text-base font-medium text-tide-600">Research intelligence</p>
            <h2 className="mt-3 max-w-3xl font-display text-4xl font-medium leading-[1.08] tracking-[-0.035em] text-ink-900 sm:text-5xl">See what the corpus knows—and what it does not.</h2>
          </div>
          <p className="max-w-[72ch] text-base leading-relaxed text-ink-600 lg:justify-self-end">Every displayed count opens back to its papers or evidence. Insufficient repetition is shown as a result, not disguised as a trend.</p>
        </div>

        <Panel className="mt-8 overflow-hidden sm:mt-10">
          <div className="grid min-w-0 xl:grid-cols-[1.1fr_0.9fr]">
            <div className="min-w-0 p-5 sm:p-7 xl:border-r xl:border-rule">
              <h3 className="text-xl font-semibold text-ink-900">Corpus over time</h3>
              <p className="mb-7 mt-2 max-w-[72ch] text-base leading-relaxed text-ink-400">
                {status === "ready"
                  ? `${totals.papers} papers indexed; ${totals.processedPapers} have reached a scientific-extraction workflow.`
                  : "Indexed papers by publication year."}
              </p>
              {data.years.length > 0 ? <YearColumns years={data.years} /> : <PanelPlaceholder what="This chart" status={status} />}
              {totals.futureDatedPapers > 0 && (
                <p className="mt-4 max-w-[72ch] text-sm leading-relaxed text-ink-400">{totals.futureDatedPapers} future-dated record{totals.futureDatedPapers === 1 ? " is" : "s are"} excluded from the year chart pending metadata correction.</p>
              )}
            </div>

            <div className="min-w-0 border-t border-rule p-5 sm:p-7 xl:border-t-0">
              <h3 className="text-xl font-semibold text-ink-900">Methods and datasets named</h3>
              <p className="mt-2 max-w-[72ch] text-base leading-relaxed text-ink-400">
                Source-linked candidate extractions marked as author-reported facts qualify. Audit status stays visible in each drill-down; counts say what is named, not what performs best. Multi-value fields are excluded unless evidence can be bound safely.
              </p>
              <p className="mt-4 text-base font-medium text-ink-900">{totals.processedPapers} of {totals.papers} papers processed.</p>
              {hasRepeatedNames ? (
                <div className="mt-7 space-y-8">
                  <NamedList title="Model families" items={trendFamilies} total={totals.processedPapers} />
                  <NamedList title="Datasets" items={trendDatasets} total={totals.processedPapers} />
                </div>
              ) : (
                <p className="mt-7 border-y border-rule py-5 text-base leading-relaxed text-ink-600">No method or dataset is named in more than one processed paper yet.</p>
              )}
            </div>
          </div>

          <div className="grid min-w-0 border-t border-rule xl:grid-cols-[0.9fr_1.1fr]">
            <div className="min-w-0 p-5 sm:p-7 xl:border-r xl:border-rule">
              <h3 className="text-xl font-semibold text-ink-900">Evidence ledger</h3>
              <p className="mb-6 mt-2 max-w-[72ch] text-base leading-relaxed text-ink-400">
                Verification states across the {totals.processedPapers} papers processed so far. {totals.indexedNotProcessed} additional papers are indexed but not yet processed. {totals.recordFields.toLocaleString("en")} scientific fields are represented; {totals.humanAudited.toLocaleString("en")} carry a VERIFIED or PARTIALLY_VERIFIED status.
              </p>
              {statuses.length > 0 ? <StatusLedger statuses={statuses} total={totals.recordFields} /> : <PanelPlaceholder what="These figures" status={status} />}
            </div>

            <div className="min-w-0 border-t border-rule p-5 sm:p-7 xl:border-t-0">
              <p className="text-base font-medium text-tide-600">Research-gap candidates · {gapPreview.label}</p>
              <h3 className="mt-3 max-w-xl text-2xl font-semibold leading-tight text-ink-900">Connect task, dataset and architecture coverage.</h3>
              <p className="mt-4 max-w-2xl text-base leading-relaxed text-ink-600">{gapPreview.description}</p>
              <div className="mt-7 flex flex-wrap items-center justify-center gap-3 border-y border-rule py-5 text-center text-base font-medium text-ink-600">
                <span>Task</span><span aria-hidden className="font-mono text-tide-500">×</span><span>Dataset</span><span aria-hidden className="font-mono text-tide-500">×</span><span>Architecture</span>
              </div>
              <p className="mt-5 font-mono text-[0.8125rem] text-ink-400">Analytics state: {gapPreview.analyticsState}</p>
              <p className="mt-2 max-w-[72ch] text-base leading-relaxed text-ink-400">
                This is a product preview, not a live analytic. It makes no claim that any combination is scientifically valuable or underexplored.
              </p>
            </div>
          </div>
        </Panel>
      </div>
    </section>
  );
}
