export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export type PaperSummary = {
  id: string;
  title: string | null;
  authors: string[];
  year: number | null;
  venue: string | null;
  doi: string | null;
  architecture: string[];
  headline: string | null;
  extracted_field_count: number;
  domains: string[];
  created_at: string;
  updated_at: string;
};

export type Domain = {
  id: string;
  name: string;
  description: string;
  paper_count: number;
};

/** Mirrors `VerificationStatus` in src/ocean_research_hub/schemas/paper_record.py. */
export type VerificationStatus =
  | "VERIFIED"
  | "PARTIALLY_VERIFIED"
  | "NOT_VERIFIED"
  | "NOT_REPORTED"
  | "CONFLICT"
  | "EXTRACTION_ERROR";

/** Mirrors `ProvenanceType` in the same module. */
export type ProvenanceType =
  | "AUTHOR_REPORTED_FACT"
  | "AUTHOR_REPORTED_LIMITATION"
  | "AI_INTERPRETATION"
  | "TEAM_NOTE";

export type SourceEvidence = {
  section: string | null;
  page: number | null;
  locator: string | null;
  /** The verbatim sentence in the paper. Never the normalised value. */
  evidence: string | null;
  origin: string | null;
  evidence_url?: string | null;
  claimed_value: unknown;
};

export type EvidenceField = {
  value: unknown;
  conflict_values: unknown[];
  status: VerificationStatus | string;
  provenance_type: ProvenanceType | string | null;
  confidence: number | null;
  source: SourceEvidence;
  sources: SourceEvidence[];
  verified_by: string | null;
  verified_at: string | null;
};

export type PaperRecord = Record<string, Record<string, unknown>>;

export type StoredPaper = {
  id: string;
  doi: string | null;
  record: PaperRecord;
  domains: string[];
  created_at: string;
  updated_at: string;
};

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

/** Backend cap on `limit`; a request for more is rejected. */
export const PAPER_PAGE_LIMIT = 200;

const DEFAULT_TIMEOUT_MS = 8_000;

async function request<T>(path: string, { timeoutMs = DEFAULT_TIMEOUT_MS } = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      cache: "no-store",
      signal: AbortSignal.timeout(timeoutMs),
    });
  } catch (error) {
    // A timeout or a refused connection must not look like an empty corpus.
    throw new ApiError(error instanceof Error ? error.message : "network error", 0);
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(body?.error?.message ?? `HTTP ${response.status}`, response.status);
  }
  return response.json();
}

export type PaperPage = {
  papers: PaperSummary[];
  /** How many papers the corpus holds, which may exceed `papers.length`. */
  total: number;
};

export async function listPaperPage(
  options: { domain?: string; limit?: number } = {},
): Promise<PaperPage> {
  const query = new URLSearchParams({ limit: String(options.limit ?? PAPER_PAGE_LIMIT) });
  if (options.domain) query.set("domain", options.domain);
  const page = await request<{ papers: PaperSummary[]; total: number }>(`/api/papers?${query}`);
  return { papers: page.papers, total: page.total ?? page.papers.length };
}

export async function listPapers(options: { domain?: string; limit?: number } = {}): Promise<PaperSummary[]> {
  return (await listPaperPage(options)).papers;
}

export function listDomains(): Promise<Domain[]> {
  return request("/api/domains");
}

export function getPaper(id: string): Promise<StoredPaper> {
  return request(`/api/papers/${encodeURIComponent(id)}`);
}

/** A paper whose technical details have been read from its PDF, not just its bibliography. */
export function isAnalyzed(paper: PaperSummary): boolean {
  return paper.extracted_field_count > 0;
}

export type LandingPaperReference = {
  id: string;
  title: string | null;
  year: number | null;
  workflow_status: string;
};

export type LandingField = EvidenceField & {
  path: string;
  label: string;
  absence_search_scope: string[];
  /** First locatable primary-author source; use this for an evidence quotation. */
  display_source: SourceEvidence | null;
};

export type LandingEvidenceItem = {
  paper: LandingPaperReference;
  field: LandingField;
  matched_value: string | null;
};

export type LandingNamedTally = {
  key: string;
  label: string;
  papers: number;
  items: LandingEvidenceItem[];
  drilldown_path: string;
};

export type LandingAggregate = {
  state: "ready" | "empty" | "partial";
  completeness: { missing_records: number; message: string | null };
  totals: {
    papers: number;
    readable_papers: number;
    domains: number;
    papers_with_extracted_fields: number;
    extracted_scientific_fields: number;
    scientific_record_fields: number;
    values_with_exact_evidence: number;
    audited_fields: number;
  };
  statuses: Array<{
    status: VerificationStatus;
    fields: number;
    description: string;
    items: LandingEvidenceItem[];
    drilldown_path: string;
  }>;
  workflows: Array<{
    status: string;
    papers: number;
    items: LandingPaperReference[];
    drilldown_path: string;
  }>;
  years: Array<{
    year: number;
    papers_with_extracted_fields: number;
    bibliography_only: number;
    extracted_papers: LandingPaperReference[];
    bibliographic_papers: LandingPaperReference[];
    extracted_drilldown_path: string;
    bibliographic_drilldown_path: string;
  }>;
  limitations: LandingNamedTally[];
  sections: Array<{
    key: string;
    label: string;
    fields: number;
    items: LandingEvidenceItem[];
    drilldown_path: string;
  }>;
  architecture_families: LandingNamedTally[];
  datasets: LandingNamedTally[];
  extraction_demo: { paper: LandingPaperReference; fields: LandingField[] } | null;
  conflict_demo: { paper: LandingPaperReference; field: LandingField } | null;
  gap_preview: {
    label: "Product Preview";
    analytics_state: "NOT_COMPUTED";
    is_live_analytic: false;
    description: string;
  };
};

/** One server-side aggregation over the full corpus; never a 200-row frontend sample. */
export function getLandingAggregate(): Promise<LandingAggregate> {
  return request("/api/landing", { timeoutMs: 15_000 });
}

export type LandingDrilldown = {
  state: "ready" | "empty" | "partial";
  completeness: { missing_records: number; message: string | null };
  total: number;
  offset: number;
  limit: number;
  evidence_items: LandingEvidenceItem[];
  paper_items: LandingPaperReference[];
};

export function getLandingDrilldown(path: string): Promise<LandingDrilldown> {
  if (!path.startsWith("/api/landing/drilldown?")) {
    throw new Error("invalid landing drill-down path");
  }
  return request(path);
}
