"use client";

import Link from "next/link";
import { useState } from "react";
import {
  getLandingDrilldown,
  type LandingEvidenceItem,
  type LandingPaperReference,
} from "@/app/lib/api";
import { formatValue } from "@/app/lib/landing";

function withOffset(path: string, offset: number): string {
  const url = new URL(path, "http://landing.local");
  url.searchParams.set("offset", String(offset));
  url.searchParams.set("limit", "50");
  return `${url.pathname}?${url.searchParams.toString()}`;
}

function EvidenceResult({ item }: { item: LandingEvidenceItem }) {
  const source = item.field.display_source;
  const hasClaim = item.field.value !== null || item.field.conflict_values.length > 0;
  return (
    <li className="border-l-2 border-tide-400 pl-4">
      {source?.evidence ? (
        <>
          <p className="text-sm font-medium text-ink-400">Stored source evidence</p>
          <blockquote className="mt-2 font-mono text-[0.9375rem] leading-relaxed text-ink-900">
            “{source.evidence}”
          </blockquote>
        </>
      ) : (
        <p className="text-sm leading-relaxed text-ink-400">
          No source quotation is attached to this field state.
        </p>
      )}

      {hasClaim && (
        <p className="mt-2 text-sm leading-relaxed text-ink-600">
          <span className="font-medium">Stored value:</span>{" "}
          {item.field.status === "CONFLICT"
            ? item.field.conflict_values.map(formatValue).join(" / ")
            : formatValue(item.field.value)}
        </p>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-[0.8125rem] text-ink-400">
        <Link
          href={`/papers/${item.paper.id}`}
          className="max-w-full truncate font-medium text-ink-600 underline decoration-rule underline-offset-4 hover:text-tide-600"
        >
          {item.paper.title || "Untitled paper"}
        </Link>
        {source?.page !== null && source?.page !== undefined && <span>p.{source.page}</span>}
        {source?.section && <span>§ {source.section}</span>}
        {source?.locator && <span>{source.locator}</span>}
        {source?.origin && <span>{source.origin}</span>}
        <span>{item.field.provenance_type}</span>
        <span className="font-mono text-ink-600">{item.field.status}</span>
        {item.field.confidence !== null && <span>Confidence {Math.round(item.field.confidence * 100)}%</span>}
        {item.field.verified_by && <span>Verified by {item.field.verified_by}</span>}
        {item.field.verified_at && <span>{new Date(item.field.verified_at).toLocaleDateString("en")}</span>}
      </div>
      {item.field.status === "NOT_REPORTED" && item.field.absence_search_scope.length > 0 && (
        <p className="mt-2 text-[0.8125rem] leading-relaxed text-ink-400">
          Absence search scope: {item.field.absence_search_scope.join(" · ")}
        </p>
      )}
    </li>
  );
}

function PaperResult({ paper }: { paper: LandingPaperReference }) {
  return (
    <li>
      <Link
        href={`/papers/${paper.id}`}
        className="text-[0.9375rem] font-medium text-ink-900 underline decoration-rule underline-offset-4 hover:text-tide-600"
      >
        {paper.title || "Untitled paper"}
      </Link>
      <p className="mt-1 text-[0.8125rem] text-ink-400">
        {[paper.year, paper.workflow_status].filter(Boolean).join(" · ")}
      </p>
    </li>
  );
}

export function Drilldown({
  path,
  total,
  initialEvidence = [],
  initialPapers = [],
  label,
}: {
  path: string;
  total: number;
  initialEvidence?: LandingEvidenceItem[];
  initialPapers?: LandingPaperReference[];
  label: string;
}) {
  const [evidence, setEvidence] = useState(initialEvidence);
  const [papers, setPapers] = useState(initialPapers);
  const [loaded, setLoaded] = useState(initialEvidence.length + initialPapers.length >= total);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [partialMessage, setPartialMessage] = useState<string | null>(null);

  const count = evidence.length + papers.length;

  async function load(offset: number) {
    setLoading(true);
    setError(null);
    try {
      const result = await getLandingDrilldown(withOffset(path, offset));
      setEvidence((current) => (offset === 0 ? result.evidence_items : [...current, ...result.evidence_items]));
      setPapers((current) => (offset === 0 ? result.paper_items : [...current, ...result.paper_items]));
      const received = result.evidence_items.length + result.paper_items.length;
      setLoaded(offset + received >= result.total);
      if (result.state === "partial") {
        setPartialMessage(result.completeness.message ?? "Some corpus records could not be read.");
      }
    } catch {
      setError("The supporting records could not be loaded. Try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <details
      className="group/drill mt-3"
      onToggle={(event) => {
        if (event.currentTarget.open && !loaded && count < total && !loading) void load(0);
      }}
    >
      <summary className="cursor-pointer list-none text-sm font-medium text-tide-600 hover:underline [&::-webkit-details-marker]:hidden">
        <span className="group-open/drill:hidden">{label}</span>
        <span className="hidden group-open/drill:inline">Hide supporting records</span>
      </summary>
      <div className="mt-4 border-t border-rule pt-4">
        {partialMessage && (
          <p role="status" className="mb-4 text-sm leading-relaxed text-ink-400">
            Partial drill-down: {partialMessage}
          </p>
        )}
        {evidence.length > 0 && (
          <ul className="space-y-5">
            {evidence.map((item, index) => (
              <EvidenceResult key={`${item.paper.id}-${item.field.path}-${index}`} item={item} />
            ))}
          </ul>
        )}
        {papers.length > 0 && (
          <ul className="space-y-4">
            {papers.map((paper) => (
              <PaperResult key={paper.id} paper={paper} />
            ))}
          </ul>
        )}
        {loading && <p role="status" className="mt-4 text-sm text-ink-400">Loading records…</p>}
        {error && <p role="alert" className="mt-4 text-sm text-ink-600">{error}</p>}
        {!loading && !loaded && !error && count > 0 && (
          <button
            type="button"
            onClick={() => void load(count)}
            className="mt-5 rounded border border-rule px-3 py-2 text-sm font-medium text-ink-900 hover:border-tide-500 hover:text-tide-600"
          >
            Load more
          </button>
        )}
      </div>
    </details>
  );
}
