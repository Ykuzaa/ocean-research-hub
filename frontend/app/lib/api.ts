const API_BASE_URL = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

export type WorkflowStatus =
  | "INGESTED"
  | "PARSED"
  | "EXTRACTED"
  | "SCIENTIFIC_AUDIT"
  | "VERIFIED"
  | "PARTIAL"
  | "REJECTED";

export type PaperSummary = {
  id: string;
  title: string | null;
  doi: string | null;
  workflow_status: WorkflowStatus;
  created_at: string;
  updated_at: string;
};

export type PaperListResponse = {
  papers: PaperSummary[];
  total: number;
};

/** Backend is the source of truth; this only shapes fetch/error handling for Server Components. */
export async function listPapers(params: {
  limit?: number;
  offset?: number;
} = {}): Promise<PaperListResponse> {
  const query = new URLSearchParams();
  if (params.limit !== undefined) query.set("limit", String(params.limit));
  if (params.offset !== undefined) query.set("offset", String(params.offset));

  const response = await fetch(`${API_BASE_URL}/api/papers?${query}`, {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`Ocean Research Hub API returned ${response.status} listing papers`);
  }
  return response.json();
}

/** The backend's own server-rendered detail page - the frontend links out to it directly. */
export function paperDetailUrl(paperId: string): string {
  return `${API_BASE_URL}/papers/${paperId}`;
}
