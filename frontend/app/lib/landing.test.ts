import { afterEach, describe, expect, it, vi } from "vitest";
import { loadLandingData } from "@/app/lib/landing";

function aggregate(state: "ready" | "empty" | "partial" = "ready") {
  const source = {
    section: "3 Training", page: 7, locator: "paragraph 2",
    evidence: "  We train with AdamW at 5e-5.  ", evidence_url: null,
    origin: "PRIMARY_PAPER", claimed_value: null,
  };
  const field = {
    path: "training.optimizer", label: "Optimizer", value: "AdamW", conflict_values: [],
    status: "NOT_VERIFIED", provenance_type: "AUTHOR_REPORTED_FACT", confidence: 0.9,
    source, sources: [], display_source: source, absence_search_scope: null,
    verified_by: null, verified_at: null,
  };
  const paper = { id: "paper-1", title: "Ocean model", year: 2024, workflow_status: "EXTRACTED" };
  const evidence = { paper, field, matched_value: "AdamW" };
  return {
    state,
    completeness: { missing_records: state === "partial" ? 2 : 0, message: state === "partial" ? "Two records could not be decoded." : null },
    totals: {
      papers: state === "empty" ? 0 : 312,
      readable_papers: state === "partial" ? 310 : state === "empty" ? 0 : 312,
      domains: state === "empty" ? 0 : 8,
      papers_with_extracted_fields: state === "empty" ? 0 : 250,
      processed_papers: state === "empty" ? 0 : 250,
      indexed_not_processed: state === "empty" ? 0 : 62,
      future_dated_papers: 0,
      extracted_scientific_fields: state === "empty" ? 0 : 900,
      scientific_record_fields: state === "empty" ? 0 : 1100,
      values_with_exact_evidence: state === "empty" ? 0 : 700,
      audited_fields: state === "empty" ? 0 : 20,
    },
    statuses: state === "empty" ? [] : [{ status: "NOT_VERIFIED", fields: 1, description: "Not independently audited.", items: [evidence], drilldown_path: "/api/landing/drilldown?kind=status&key=NOT_VERIFIED" }],
    workflows: [],
    years: state === "empty" ? [] : [{ year: 2024, papers_with_extracted_fields: 1, bibliography_only: 0, extracted_papers: [paper], bibliographic_papers: [], extracted_drilldown_path: "/api/landing/drilldown?kind=year_extracted&key=2024", bibliographic_drilldown_path: "/api/landing/drilldown?kind=year_bibliographic&key=2024" }],
    limitations: [], sections: [],
    architecture_families: state === "empty" ? [] : [{ key: "adamw", label: "AdamW", papers: 1, items: [evidence], drilldown_path: "/api/landing/drilldown?kind=architecture&key=adamw" }],
    datasets: [],
    extraction_demo: state === "empty" ? null : { paper, fields: [field] }, conflict_demo: null,
    gap_preview: { label: "Product Preview", analytics_state: "NOT_COMPUTED", is_live_analytic: false, description: "Candidate gap analytics are not computed." },
  };
}

function respond(body: unknown, ok = true) {
  return vi.fn().mockResolvedValue({ ok, status: ok ? 200 : 503, json: () => Promise.resolve(body) });
}

afterEach(() => vi.unstubAllGlobals());

describe("loadLandingData", () => {
  it("uses one aggregate request and preserves exact evidence separately from the value", async () => {
    const fetch = respond(aggregate());
    vi.stubGlobal("fetch", fetch);
    const result = await loadLandingData();
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(String(fetch.mock.calls[0][0])).toContain("/api/landing");
    expect(String(fetch.mock.calls[0][0])).not.toContain("/api/papers");
    expect(result.totals.papers).toBe(312);
    expect(result.totals.processedPapers).toBe(250);
    expect(result.totals.indexedNotProcessed).toBe(62);
    expect(result.extraction?.rows[0]).toMatchObject({ value: "AdamW", evidence: "  We train with AdamW at 5e-5.  ", provenance: "AUTHOR_REPORTED_FACT", status: "NOT_VERIFIED" });
    expect(result.families[0].items[0].field.display_source?.evidence).toBe("  We train with AdamW at 5e-5.  ");
  });

  it.each(["ready", "empty", "partial"] as const)("maps the backend %s state", async (state) => {
    vi.stubGlobal("fetch", respond(aggregate(state)));
    const result = await loadLandingData();
    expect(result.status).toBe(state);
    expect(result.partial?.missingRecords ?? 0).toBe(state === "partial" ? 2 : 0);
  });

  it("maps transport failures to UNAVAILABLE without invented totals", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    const result = await loadLandingData();
    expect(result.status).toBe("unavailable");
    expect(result.totals.papers).toBe(0);
    expect(result.gapPreview.isLiveAnalytic).toBe(false);
  });

  it("keeps candidate gap analytics explicitly non-live", async () => {
    vi.stubGlobal("fetch", respond(aggregate()));
    const result = await loadLandingData();
    expect(result.gapPreview).toMatchObject({ label: "Product Preview", analyticsState: "NOT_COMPUTED", isLiveAnalytic: false });
  });
});
