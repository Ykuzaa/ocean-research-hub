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
