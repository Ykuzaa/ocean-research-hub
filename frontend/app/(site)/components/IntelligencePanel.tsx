import type { LandingData, NamedTally, StatusTally, YearBar } from "@/app/lib/landing";
import { MagnitudeRow, Panel, PanelPlaceholder, SectionHeader } from "./primitives";

/**
 * Corpus by publication year. Two series (with extracted fields / bibliography
 * only) are two steps of the one accent ramp, stacked from a shared baseline
 * with a 2px surface gap, legend present, only the peak column direct-labelled.
 *
 * The bars are decorative: the same numbers are in a visually hidden table
 * that the figure points at, so the chart is fully readable without sight.
 */
function YearColumns({ years }: { years: YearBar[] }) {
  const max = Math.max(1, ...years.map((bar) => bar.extracted + bar.bibliographic));
  const peak = years.reduce((best, bar) =>
    bar.extracted + bar.bibliographic > best.extracted + best.bibliographic ? bar : best,
  );

  return (
    <figure className="m-0" aria-describedby="year-table">
      <div aria-hidden className="flex h-40 items-end gap-1.5 border-b border-rule sm:h-56 sm:gap-2">
        {years.map((bar) => {
          const total = bar.extracted + bar.bibliographic;
          return (
            <div key={bar.year} className="flex h-full min-w-0 flex-1 flex-col justify-end">
              {/* Reserved on every column so the labelled one is not shortened. */}
              <span className="mb-1 h-4 text-center font-mono text-[0.6875rem] leading-4 tabular-nums text-ink-900">
                {bar.year === peak.year ? total : ""}
              </span>
              <span
                className="mx-auto flex w-full max-w-6 flex-col justify-end"
                style={{ height: `${(total / max) * 100}%` }}
              >
                {bar.bibliographic > 0 && (
                  <span
                    className="mb-0.5 block rounded-t-[4px] bg-mute"
                    style={{ height: `${(bar.bibliographic / total) * 100}%` }}
                  />
                )}
                {bar.extracted > 0 && (
                  <span
                    className={`block bg-tide-400 ${bar.bibliographic > 0 ? "" : "rounded-t-[4px]"}`}
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
          <span
            key={bar.year}
            className="min-w-0 flex-1 text-center font-mono text-[0.625rem] tabular-nums text-ink-400"
          >
            {`'${String(bar.year).slice(2)}`}
          </span>
        ))}
      </div>

      <div id="year-table" className="sr-only">
        <table>
          <caption>Papers by publication year</caption>
          <thead>
            <tr>
              <th scope="col">Year</th>
              <th scope="col">With extracted fields</th>
              <th scope="col">Bibliography only</th>
            </tr>
          </thead>
          <tbody>
            {years.map((bar) => (
              <tr key={bar.year}>
                <th scope="row">{bar.year}</th>
                <td>{bar.extracted}</td>
                <td>{bar.bibliographic}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <figcaption className="mt-4 flex flex-wrap gap-x-5 gap-y-1.5 text-xs text-ink-600">
        <span className="flex items-center gap-2">
          <span aria-hidden className="h-2.5 w-2.5 rounded-[2px] bg-tide-400" />
          With extracted fields
        </span>
        <span className="flex items-center gap-2">
          <span aria-hidden className="h-2.5 w-2.5 rounded-[2px] bg-mute" />
          Bibliography only
        </span>
      </figcaption>
    </figure>
  );
}

/** Verification states over every field of every record read — failures included. */
function StatusLedger({ statuses, total }: { statuses: StatusTally[]; total: number }) {
  return (
    <ul className="space-y-3.5">
      {statuses.map((entry) => {
        const exact = total > 0 ? (entry.fields / total) * 100 : 0;
        const share = Math.round(exact);
        // A non-zero count must never print as "0%".
        const shareLabel = share === 0 && entry.fields > 0 ? "<1%" : `${share}%`;
        return (
          <li key={entry.status}>
            <p className="flex items-baseline justify-between gap-3">
              <span className="font-mono text-xs text-ink-900">{entry.status}</span>
              <span className="shrink-0 font-mono text-xs tabular-nums text-ink-600">
                {entry.fields.toLocaleString("en")}
                <span className="text-ink-400"> · {shareLabel}</span>
              </span>
            </p>
            <span aria-hidden className="mt-1.5 block h-1.5 bg-sheet-3">
              <span
                className="block h-full rounded-r-[3px] bg-tide-400"
                style={{ width: `${Math.max(share, 1)}%` }}
              />
            </span>
            {entry.blurb && <p className="mt-1.5 text-xs leading-relaxed text-ink-400">{entry.blurb}</p>}
          </li>
        );
      })}
    </ul>
  );
}

/** Entries shown before the list folds into a disclosure. */
const NAMED_VISIBLE = 4;

function NamedRow({ item, of, unit }: { item: NamedTally; of: number; unit: string }) {
  return (
    <li className="flex items-baseline justify-between gap-3">
      <span className="min-w-0 flex-1 truncate text-[0.8125rem] text-ink-600" title={item.name}>
        {item.name}
      </span>
      <span className="shrink-0 font-mono text-xs tabular-nums text-ink-400">
        {item.papers}/{of} {unit}
      </span>
    </li>
  );
}

/**
 * Long tails fold away rather than stacking down a phone screen. Nothing is
 * dropped — `<details>` keeps the rest one keyboard-reachable step away.
 */
function NamedList({
  title,
  items,
  of,
  unit,
}: {
  title: string;
  items: NamedTally[];
  of: number;
  unit: string;
}) {
  const head = items.slice(0, NAMED_VISIBLE);
  const tail = items.slice(NAMED_VISIBLE);
  return (
    <div>
      <p className="mb-2.5 font-mono text-[0.6875rem] uppercase tracking-[0.18em] text-ink-400">
        {title}
      </p>
      <ul className="space-y-2.5">
        {head.map((item) => (
          <NamedRow key={item.name} item={item} of={of} unit={unit} />
        ))}
      </ul>
      {tail.length > 0 && (
        <details className="group mt-2.5">
          <summary className="cursor-pointer list-none text-xs text-tide-600 hover:underline [&::-webkit-details-marker]:hidden">
            <span className="group-open:hidden">Show {tail.length} more</span>
            <span className="hidden group-open:inline">Show fewer</span>
          </summary>
          <ul className="mt-2.5 space-y-2.5">
            {tail.map((item) => (
              <NamedRow key={item.name} item={item} of={of} unit={unit} />
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

export function IntelligencePanel({ data }: { data: LandingData }) {
  const { sections, statuses, totals, families, datasets, status } = data;
  const maxFields = Math.max(1, ...sections.map((item) => item.fields));
  const repeatedFamilies = families.filter((item) => item.papers > 1).length;
  const repeatedDatasets = datasets.filter((item) => item.papers > 1).length;

  return (
    <section id="intelligence" className="scroll-mt-20 border-t border-rule/60 bg-sheet-1">
      <div className="mx-auto max-w-6xl px-5 py-14 sm:px-8 sm:py-20 lg:py-24">
        <SectionHeader
          kicker="Research intelligence"
          title="What the corpus currently knows about itself."
          lede="Once papers are structured, the corpus becomes queryable as data: how it is growing, which methods and datasets it names, what has been captured, and how much of it is actually trustworthy."
        />

        <div className="mt-8 grid grid-cols-[minmax(0,1fr)] gap-4 sm:mt-10 lg:grid-cols-3">
          <Panel className="p-5 sm:p-6">
            <h3 className="text-sm font-medium text-ink-900">Corpus by publication year</h3>
            <p className="mt-1 mb-6 text-xs leading-relaxed text-ink-400">
              {status === "ready"
                ? `${totals.papers} papers indexed, ${totals.papersWithFields} with fields extracted from their PDF.`
                : "Indexed papers by publication year."}
            </p>
            {data.years.length > 0 ? (
              <YearColumns years={data.years} />
            ) : (
              <PanelPlaceholder what="This chart" status={status} />
            )}
          </Panel>

          <Panel className="p-5 sm:p-6">
            <h3 className="text-sm font-medium text-ink-900">Methods and datasets named</h3>
            <p className="mt-1 mb-5 text-xs leading-relaxed text-ink-400">
              Model families and datasets the extracted papers name, with how many papers name each.
            </p>
            {families.length > 0 || datasets.length > 0 ? (
              <div className="space-y-6">
                <NamedList
                  title="Model families"
                  items={families}
                  of={totals.papersWithFields}
                  unit="papers"
                />
                <NamedList
                  title="Datasets"
                  items={datasets}
                  of={totals.papersWithFields}
                  unit="papers"
                />
                <p className="text-xs leading-relaxed text-ink-400">
                  {repeatedFamilies === 0 && repeatedDatasets === 0
                    ? "No family or dataset is yet named by more than one paper, so this corpus supports no trend claim and no ranking of underexplored combinations."
                    : `${repeatedFamilies} famil${repeatedFamilies === 1 ? "y" : "ies"} and ${repeatedDatasets} dataset${repeatedDatasets === 1 ? "" : "s"} are named by more than one paper — still far too few for a trend claim.`}
                </p>
              </div>
            ) : (
              <PanelPlaceholder what="This list" status={status} />
            )}
          </Panel>

          <Panel className="p-5 sm:p-6">
            <h3 className="text-sm font-medium text-ink-900">Evidence ledger</h3>
            <p className="mt-1 mb-5 text-xs leading-relaxed text-ink-400">
              Every field of every record read, by verification state —{" "}
              {totals.recordFields.toLocaleString("en")} in total, of which{" "}
              {totals.humanAudited.toLocaleString("en")} have been audited by a human.
            </p>
            {statuses.length > 0 ? (
              <StatusLedger statuses={statuses} total={totals.recordFields} />
            ) : (
              <PanelPlaceholder what="These figures" status={status} />
            )}
          </Panel>
        </div>

        <Panel className="mt-4 p-5 sm:p-6">
          <h3 className="text-sm font-medium text-ink-900">Extracted fields by record section</h3>
          <p className="mt-1 mb-6 text-xs leading-relaxed text-ink-400">
            Where the structured detail sits today. Thin sections are where extraction still has work
            to do.
          </p>
          {sections.length > 0 ? (
            <div className="grid grid-cols-[minmax(0,1fr)] gap-x-10 gap-y-3 sm:grid-cols-2">
              {sections.map((item) => (
                <MagnitudeRow key={item.key} label={item.label} value={item.fields} max={maxFields} />
              ))}
            </div>
          ) : (
            <PanelPlaceholder what="This chart" status={status} />
          )}
        </Panel>

        <p className="mt-6 max-w-3xl text-[0.8125rem] leading-relaxed text-ink-400">
          Candidate research gaps — combinations of task, dataset and architecture this corpus barely
          covers — are built on these same counts and are not implemented yet. Ranking them needs a
          corpus where combinations actually repeat. When they ship they will be presented as
          underexplored candidates, never as proof that a gap is scientifically valuable.
        </p>
      </div>
    </section>
  );
}
