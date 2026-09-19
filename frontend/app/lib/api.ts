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

export type SourceEvidence = {
  section: string | null;
  page: number | null;
  evidence: string | null;
  origin: string | null;
  claimed_value: unknown;
};

export type EvidenceField = {
  value: unknown;
  conflict_values: unknown[];
  status: string;
  source: SourceEvidence;
  sources: SourceEvidence[];
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

async function request<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, { cache: "no-store" });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(body?.error?.message ?? `HTTP ${response.status}`, response.status);
  }
  return response.json();
}

export async function listPapers(options: { domain?: string; limit?: number } = {}): Promise<PaperSummary[]> {
  const query = new URLSearchParams({ limit: String(options.limit ?? 200) });
  if (options.domain) query.set("domain", options.domain);
  return (await request<{ papers: PaperSummary[] }>(`/api/papers?${query}`)).papers;
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
