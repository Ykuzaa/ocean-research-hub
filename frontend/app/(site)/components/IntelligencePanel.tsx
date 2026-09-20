import type { LandingData, NamedTally, StatusTally, YearBar } from "@/app/lib/landing";
import { Drilldown } from "./Drilldown";
import { Panel, PanelPlaceholder, SectionHeader } from "./primitives";

function YearColumns({ years }: { years: YearBar[] }) {
  const max = Math.max(1, ...years.map((bar) => bar.extracted + bar.bibliographic));
  const peak = years.reduce((best, bar) =>
    bar.extracted + bar.bibliographic > best.extracted + best.bibliographic ? bar : best,
  );

  return (
    <figure className="m-0" aria-describedby="year-data">
      <div aria-hidden className="flex h-44 items-end gap-1.5 border-b border-rule sm:h-60 sm:gap-2">
        {years.map((bar) => {
          const total = bar.extracted + bar.bibliographic;
          return (
            <div key={bar.year} className="flex h-full min-w-0 flex-1 flex-col justify-end">
              <span className="mb-1 h-5 text-center font-mono text-[0.8125rem] leading-5 tabular-nums text-ink-900">
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
          <span key={bar.year} className="min-w-0 flex-1 text-center font-mono text-[0.8125rem] tabular-nums text-ink-400">
            {String(bar.year).slice(2)}
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
              <span className="font-mono text-[0.8125rem] tabular-nums text-ink-600">{entry.fields.toLocaleString("en")} · {shareLabel}</span>
            </div>
            <span aria-hidden className="mt-2 block h-1.5 bg-sheet-3">
              <span className="block h-full bg-tide-400" style={{ width: `${Math.max(share, 1)}%` }} />
            </span>
            <p className="mt-2 text-sm leading-relaxed text-ink-400">{entry.blurb}</p>
            <Drilldown path={entry.drilldownPath} total={entry.fields} initialEvidence={entry.items} label={`Inspect ${entry.fields.toLocaleString("en")} field${entry.fields === 1 ? "" : "s"}`} />
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
              <div className="flex items-baseline justify-between gap-4 text-[0.9375rem]">
                <span className="min-w-0 truncate text-ink-600" title={item.name}>{item.name}</span>
                <span className="shrink-0 font-mono text-[0.8125rem] tabular-nums text-ink-400">{item.papers}/{total} papers</span>
              </div>
              <Drilldown path={item.drilldownPath} total={item.papers} initialEvidence={item.items} label="View papers and exact evidence" />
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-sm leading-relaxed text-ink-400">No source-linked candidate extractions qualify yet.</p>
      )}
    </div>
  );
}

export function IntelligencePanel({ data }: { data: LandingData }) {
  const { statuses, totals, families, datasets, status, gapPreview } = data;
  const repeatedFamilies = families.filter((item) => item.papers > 1).length;
  const repeatedDatasets = datasets.filter((item) => item.papers > 1).length;

  return (
    <section id="intelligence" className="scroll-mt-20 border-t border-rule/60 bg-sheet-1">
      <div className="mx-auto max-w-7xl px-5 py-14 sm:px-8 sm:py-20">
        <SectionHeader
          kicker="Research intelligence"
          title="See what the corpus knows—and what it does not."
          lede="The same evidence-grounded records can reveal corpus coverage, named methods and datasets, and the audit state of every field. Every displayed count opens back to its papers or evidence."
        />

        <Panel className="mt-8 overflow-hidden sm:mt-10">
          <div className="grid lg:grid-cols-[1.1fr_0.9fr]">
            <div className="p-5 sm:p-7 lg:border-r lg:border-rule">
              <h3 className="text-xl font-semibold text-ink-900">Corpus over time</h3>
              <p className="mb-7 mt-2 text-[0.9375rem] leading-relaxed text-ink-400">
                {status === "ready"
                  ? `${totals.papers} papers across the full corpus; ${totals.papersWithFields} contain extracted scientific fields.`
                  : "Indexed papers by publication year."}
              </p>
              {data.years.length > 0 ? <YearColumns years={data.years} /> : <PanelPlaceholder what="This chart" status={status} />}
            </div>

            <div className="border-t border-rule p-5 sm:p-7 lg:border-t-0">
              <h3 className="text-xl font-semibold text-ink-900">Methods and datasets named</h3>
              <p className="mt-2 text-[0.9375rem] leading-relaxed text-ink-400">
                Source-linked candidate extractions marked as author-reported facts qualify. Audit status stays visible in each drill-down; counts say what is named, not what performs best. Multi-value fields are excluded unless evidence can be bound safely.
              </p>
              <div className="mt-7 space-y-8">
                <NamedList title="Model families" items={families} total={totals.papersWithFields} />
                <NamedList title="Datasets" items={datasets} total={totals.papersWithFields} />
              </div>
              {(families.length > 0 || datasets.length > 0) && (
                <p className="mt-7 border-t border-rule pt-4 text-sm leading-relaxed text-ink-400">
                  {repeatedFamilies === 0 && repeatedDatasets === 0
                    ? "Nothing repeats across enough papers to support a trend claim."
                    : `${repeatedFamilies} model families and ${repeatedDatasets} datasets appear in more than one paper; that alone does not establish a trend.`}
                </p>
              )}
            </div>
          </div>

          <div className="grid border-t border-rule lg:grid-cols-[0.9fr_1.1fr]">
            <div className="p-5 sm:p-7 lg:border-r lg:border-rule">
              <h3 className="text-xl font-semibold text-ink-900">Evidence ledger</h3>
              <p className="mb-6 mt-2 text-[0.9375rem] leading-relaxed text-ink-400">
                {totals.recordFields.toLocaleString("en")} scientific fields by verification state. {totals.humanAudited.toLocaleString("en")} carry a VERIFIED or PARTIALLY_VERIFIED status.
              </p>
              {statuses.length > 0 ? <StatusLedger statuses={statuses} total={totals.recordFields} /> : <PanelPlaceholder what="These figures" status={status} />}
            </div>

            <div className="border-t border-rule p-5 sm:p-7 lg:border-t-0">
              <p className="text-base font-medium text-tide-600">Research-gap candidates · {gapPreview.label}</p>
              <h3 className="mt-3 max-w-xl text-2xl font-semibold leading-tight text-ink-900">Connect task, dataset and architecture coverage.</h3>
              <p className="mt-4 max-w-2xl text-base leading-relaxed text-ink-600">{gapPreview.description}</p>
              <div className="mt-7 grid grid-cols-[1fr_auto_1fr] items-center gap-3 border-y border-rule py-5 text-center text-sm font-medium text-ink-600 sm:grid-cols-[1fr_auto_1fr_auto_1fr]">
                <span>Task</span><span aria-hidden className="font-mono text-tide-500">×</span><span>Dataset</span><span aria-hidden className="hidden font-mono text-tide-500 sm:block">×</span><span className="col-span-3 sm:col-span-1">Architecture</span>
              </div>
              <p className="mt-5 font-mono text-[0.8125rem] text-ink-400">Analytics state: {gapPreview.analyticsState}</p>
              <p className="mt-2 text-sm leading-relaxed text-ink-400">
                This is a product preview, not a live analytic. It makes no claim that any combination is scientifically valuable or underexplored.
              </p>
            </div>
          </div>
        </Panel>
      </div>
    </section>
  );
}
