import Link from "next/link";
import type { ExtractionRow, LandingData } from "@/app/lib/landing";
import { MetaChip, Panel, PanelPlaceholder, SectionHeader } from "./primitives";

/** A short arrow that turns into a vertical tick when the row stacks on phones. */
function Connector() {
  return (
    <span aria-hidden className="flex items-center justify-center text-tide-600">
      <svg viewBox="0 0 24 24" className="h-5 w-5 rotate-90 sm:rotate-0" fill="none">
        <path d="M3 12h16m0 0-5-5m5 5-5 5" stroke="currentColor" strokeWidth="1.25" />
      </svg>
    </span>
  );
}

/** One sentence can fill several fields; show it once with both fields beside it. */
function groupByEvidence(rows: ExtractionRow[]): { evidence: string; fields: ExtractionRow[] }[] {
  const groups: { evidence: string; fields: ExtractionRow[] }[] = [];
  for (const row of rows) {
    const last = groups.at(-1);
    if (last?.evidence === row.evidence) last.fields.push(row);
    else groups.push({ evidence: row.evidence, fields: [row] });
  }
  return groups;
}

export function ExtractionPanel({ data }: { data: LandingData }) {
  const demo = data.extraction;
  const conflict = data.conflict;
  const groups = demo ? groupByEvidence(demo.rows) : [];

  return (
    <section id="extraction" className="scroll-mt-20 border-t border-rule/60">
      <div className="mx-auto max-w-7xl px-5 py-14 sm:px-8 sm:py-20">
        <SectionHeader
          kicker="Structured extraction"
          title="One excerpt from the PDF. One field you can check."
          lede="Each technical value keeps its stored evidence excerpt, page and section — so a reader can disagree with the extraction, not just with the summary."
        />

        {demo ? (
          <Panel className="mt-8 overflow-hidden sm:mt-10">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-rule px-5 py-3.5 sm:px-6">
              <MetaChip>source</MetaChip>
              <Link
                href={`/papers/${demo.paperId}`}
                className="min-w-0 flex-1 truncate text-sm text-ink-900 underline decoration-mute underline-offset-4 transition hover:text-tide-600"
              >
                {demo.paperTitle}
              </Link>
            </div>

            <div className="divide-y divide-rule">
              <div className="hidden grid-cols-[minmax(0,1fr)_2rem_minmax(0,0.9fr)] gap-4 px-6 py-2.5 sm:grid">
                <span className="text-sm font-medium text-ink-400">
                  Evidence in the paper
                </span>
                <span />
                <span className="text-sm font-medium text-ink-400">
                  Structured field
                </span>
              </div>

              {groups.map((group) => (
                <div
                  key={group.evidence}
                  className="grid gap-3 px-5 py-4 sm:grid-cols-[minmax(0,1fr)_2rem_minmax(0,0.9fr)] sm:items-center sm:gap-4 sm:px-6"
                >
                  <p className="font-mono text-[0.9375rem] leading-relaxed text-ink-600">
                    <span className="bg-tide-200/60 decoration-tide-500 underline-offset-4 [text-decoration-line:underline]">
                      {group.evidence}
                    </span>
                  </p>
                  <Connector />
                  <div className="min-w-0 space-y-3">
                    {group.fields.map((row) => (
                      <div key={row.label}>
                        <p className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                          <span className="text-sm text-ink-400">{row.label}</span>
                          <span className="font-mono text-[0.9375rem] text-ink-900">{row.value}</span>
                        </p>
                        <p className="mt-1.5 flex flex-wrap items-center gap-1.5">
                          {row.page !== null && <MetaChip>p.{row.page}</MetaChip>}
                          {row.section && (
                            <MetaChip>
                              <span className="max-w-[12rem] truncate">§ {row.section}</span>
                            </MetaChip>
                          )}
                          {row.provenance && <MetaChip>{row.provenance}</MetaChip>}
                          <MetaChip tone="accent">{row.status}</MetaChip>
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>

            <p className="border-t border-rule px-5 py-4 text-sm leading-relaxed text-ink-400 sm:px-6">
              Read live from the stored record. <span className="font-mono">NOT_VERIFIED</span> means
              extracted with evidence and not yet confirmed by a human auditor — the status is shown
              rather than rounded up to fact.
            </p>
          </Panel>
        ) : (
          <div className="mt-8 sm:mt-10">
            <PanelPlaceholder
              what="This walkthrough"
              status={data.status}
              empty="No paper in the corpus yet has three source-linked training fields that qualify for this walkthrough."
            />
          </div>
        )}

        <div className="mt-8 grid border-y border-rule sm:grid-cols-2">
          <div className="py-5 sm:pr-8">
            <p className="text-lg font-semibold text-ink-900">Never guessed</p>
            <p className="mt-2 text-[0.9375rem] leading-relaxed text-ink-600">
              A value the paper does not state is stored as{" "}
              <span className="font-mono text-ink-900">NOT_REPORTED</span>. A Transformer paper that
              never names its activation does not acquire one.
            </p>
          </div>
          <div className="border-t border-rule py-5 sm:border-l sm:border-t-0 sm:pl-8">
            <p className="text-lg font-semibold text-ink-900">Conflicts stay visible</p>
            {conflict ? (
              <div className="mt-2 text-[0.9375rem] leading-relaxed text-ink-600">
                <p>
                  Two places in one paper give a different {conflict.label} —{" "}
                  {conflict.values.map((value, index) => (
                    <span key={value}>{index > 0 && " and "}<span className="font-mono text-ink-900">{value}</span></span>
                  ))}. Both are kept, flagged <span className="font-mono text-ink-900">CONFLICT</span>.
                </p>
                {conflict.sources.length > 0 && (
                  <details className="group mt-3">
                    <summary className="cursor-pointer list-none text-sm font-medium text-tide-600 hover:underline [&::-webkit-details-marker]:hidden">
                      <span className="group-open:hidden">Inspect conflicting source bindings</span>
                      <span className="hidden group-open:inline">Hide source bindings</span>
                    </summary>
                    <ul className="mt-3 space-y-3">
                      {conflict.sources.map((source, index) => (
                        <li key={`${source.claimedValue}-${index}`} className="border-l-2 border-tide-400 pl-3">
                          <p className="font-mono text-[0.8125rem] text-ink-900">{source.claimedValue}</p>
                          <blockquote className="mt-1 text-sm leading-relaxed text-ink-600">“{source.evidence}”</blockquote>
                          <p className="mt-1 text-[0.8125rem] text-ink-400">{[source.page !== null ? `p.${source.page}` : null, source.section, source.locator].filter(Boolean).join(" · ")}</p>
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
              </div>
            ) : (
              <p className="mt-2 text-[0.9375rem] leading-relaxed text-ink-600">
                When two places in a paper disagree, both values are kept and the field is flagged{" "}
                <span className="font-mono text-ink-900">CONFLICT</span> instead of one being picked
                silently.
              </p>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
