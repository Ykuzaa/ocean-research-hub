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
  created_at: string;
  updated_at: string;
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
  created_at: string;
  updated_at: string;
};

export class ApiError extends Error {
  constructor(message: string, readonly status: number, readonly code?: string) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, { cache: "no-store", ...init });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const code: string | undefined = body?.error?.code;
    const message: string = body?.error?.message ?? `HTTP ${response.status}`;
    throw new ApiError(message, response.status, code);
  }
  return response.json();
}

export function listPapers(limit = 100): Promise<{ papers: PaperSummary[]; total: number }> {
  return request(`/api/papers?limit=${limit}`);
}

export function getPaper(id: string): Promise<StoredPaper> {
  return request(`/api/papers/${encodeURIComponent(id)}`);
}

export function ingestPaper(body: { pdf_url: string; doi?: string }): Promise<{
  created: boolean;
  paper: StoredPaper;
}> {
  return request("/api/papers/ingest", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}
