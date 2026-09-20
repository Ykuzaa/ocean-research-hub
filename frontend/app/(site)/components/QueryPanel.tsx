import Link from "next/link";
import type { EvidenceItem, LandingData, LimitationTally } from "@/app/lib/landing";
import { MetaChip, Panel, PanelPlaceholder, SectionHeader } from "./primitives";

/**
 * Product preview for evidence-grounded querying.
 *
 * The aggregate is real: it is counted from the structured corpus on every
 * request, and every count opens into the complete set of papers behind it.
 * What is *not* built is the natural-language layer, which the panel says.
 */

function Evidence({ item }: { item: EvidenceItem }) {
  return (
    <li className="border-l-2 border-tide-400 pl-4">
      <p className="font-mono text-[0.8125rem] leading-relaxed text-ink-900">“{item.evidence}”</p>
      <p className="mt-2 text-xs leading-relaxed text-ink-400">
        <span className="text-ink-600">Extracted as:</span> {item.claim}
      </p>
      <div className="mt-2">
        <Link
          href={`/papers/${item.paperId}`}
          className="block truncate text-xs text-ink-600 underline decoration-rule underline-offset-4 transition hover:text-tide-600"
        >
          {item.paperTitle}
        </Link>
        <p className="mt-1.5 flex flex-wrap items-center gap-1.5">
          {item.page !== null && <MetaChip>p.{item.page}</MetaChip>}
          {item.section && (
            <MetaChip>
              <span className="max-w-[11rem] truncate">§ {item.section}</span>
            </MetaChip>
          )}
          {item.provenance && <MetaChip>{item.provenance}</MetaChip>}
          <MetaChip tone="accent">{item.status}</MetaChip>
        </p>
      </div>
    </li>
  );
}

/**
 * One tally row. `<details>` gives the disclosure keyboard focus and screen
 * reader semantics for free, and keeps the mobile page short by default.
 */
function TallyRow({ tally, max, of }: { tally: LimitationTally; max: number; of: number }) {
  const share = max > 0 ? Math.max(tally.papers / max, 0.02) : 0;
  return (
    <details className="group border-b border-rule/70 last:border-b-0">
      <summary className="grid cursor-pointer list-none grid-cols-[minmax(4.5rem,9rem)_minmax(0,1fr)_auto] items-center gap-3 py-2.5 sm:gap-4 [&::-webkit-details-marker]:hidden">
        <span className="truncate text-[0.8125rem] text-ink-600 group-hover:text-ink-900">
          {tally.label}
        </span>
        <span className="h-2.5 min-w-0 bg-sheet-3">
          <span className="block h-full rounded-r-[4px] bg-tide-400" style={{ width: `${share * 100}%` }} />
        </span>
        <span className="flex w-20 items-center justify-end gap-1.5 font-mono text-xs tabular-nums text-ink-900">
          {tally.papers}
          <span className="text-ink-400">/ {of}</span>
          <svg
            aria-hidden
            viewBox="0 0 16 16"
            className="h-3.5 w-3.5 text-ink-400 transition group-open:rotate-90"
            fill="none"
          >
            <path d="M6 3.5 10.5 8 6 12.5" stroke="currentColor" strokeWidth="1.5" />
          </svg>
        </span>
      </summary>
      <ul className="space-y-5 pb-5 pt-1 sm:pl-[10.5rem]">
        {tally.items.map((item) => (
          <Evidence key={`${item.paperId}-${item.page}`} item={item} />
        ))}
      </ul>
    </details>
  );
}

export function QueryPanel({ data }: { data: LandingData }) {
  const { limitations, totals, status } = data;
  const max = Math.max(1, ...limitations.map((item) => item.papers));

  return (
    <section id="query" className="scroll-mt-20 border-t border-rule/60 bg-sheet-1">
      <div className="mx-auto max-w-6xl px-5 py-14 sm:px-8 sm:py-20 lg:py-24">
        <SectionHeader
          kicker="Query the corpus"
          title="Ask a question. Get an aggregate you can audit."
          lede="Answers are counted over structured records, never generated prose. Open any count to see every paper behind it, and the sentence in each paper the value was read from."
        />

        <Panel className="mt-8 overflow-hidden sm:mt-10">
          <div className="flex items-center gap-3 border-b border-rule px-4 py-3.5 sm:px-6">
            <span className="font-mono text-tide-500" aria-hidden>
              ›
            </span>
            <p className="min-w-0 flex-1 font-mono text-[0.8125rem] leading-relaxed text-ink-900">
              What limitations do these papers report most often?
            </p>
            <MetaChip>example</MetaChip>
          </div>

          <div className="p-5 sm:p-6">
            <p className="mb-3 text-[0.8125rem] text-ink-600">
              Limitation families the authors state themselves, across the {totals.papersWithFields}{" "}
              papers with extracted fields. Only fields carrying an{" "}
              <span className="font-mono text-xs">AUTHOR_REPORTED_LIMITATION</span> provenance and a
              source sentence are counted.
            </p>
            {limitations.length > 0 ? (
              <div>
                {limitations.map((tally) => (
                  <TallyRow key={tally.key} tally={tally} max={max} of={totals.papersWithFields} />
                ))}
              </div>
            ) : (
              <PanelPlaceholder what="This ranking" status={status} />
            )}
          </div>

          <p className="border-t border-rule px-5 py-3.5 text-xs leading-relaxed text-ink-400 sm:px-6">
            Product preview. The counts and the evidence are live; the natural-language layer that
            will accept arbitrary questions is not built yet, so this panel runs one fixed query.
          </p>
        </Panel>

        <p className="mt-6 max-w-3xl text-[0.8125rem] leading-relaxed text-ink-400">
          Counts describe what this corpus reports, not which method is better. A limitation
          appearing often means many authors chose to state it — nothing more.
        </p>
      </div>
    </section>
  );
}
