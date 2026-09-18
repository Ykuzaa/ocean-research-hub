import { listPapers, paperDetailUrl, type PaperSummary } from "@/app/lib/api";
import { StatusBadge } from "@/app/components/StatusBadge";

export const metadata = {
  title: "Ocean Research Hub",
  description: "Evidence-backed scientific paper records.",
};

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export default async function PapersPage() {
  let papers: PaperSummary[] = [];
  let total = 0;
  let loadError: string | null = null;
  try {
    const response = await listPapers({ limit: 50 });
    papers = response.papers;
    total = response.total;
  } catch (error) {
    loadError = error instanceof Error ? error.message : "Could not reach the Ocean Research Hub API.";
  }

  return (
    <main className="mx-auto max-w-5xl px-6 py-10">
      <header className="mb-8">
        <h1 className="text-2xl font-semibold text-slate-900">Ocean Research Hub</h1>
        <p className="mt-1 text-sm text-slate-600">
          Evidence-backed scientific paper records. Every field carries its verification
          status, source, and provenance.
        </p>
      </header>

      {loadError && (
        <div className="mb-6 rounded-md border border-rose-300 bg-rose-50 px-4 py-3 text-sm text-rose-800">
          Could not load papers from the API: {loadError}. Is the FastAPI server running
          (<code className="font-mono">uv run ocean-research-hub</code>) and reachable at the
          configured <code className="font-mono">API_BASE_URL</code>?
        </div>
      )}

      {!loadError && papers.length === 0 && (
        <div className="rounded-md border border-slate-200 bg-slate-50 px-4 py-6 text-center text-sm text-slate-600">
          No papers ingested yet. Ingest one via{" "}
          <code className="font-mono">POST /api/papers/ingest</code> on the backend.
        </div>
      )}

      {papers.length > 0 && (
        <>
          <p className="mb-3 text-xs uppercase tracking-wide text-slate-500">
            {total} paper{total === 1 ? "" : "s"}
          </p>
          <ul className="divide-y divide-slate-200 overflow-hidden rounded-lg border border-slate-200 bg-white">
            {papers.map((paper) => (
              <li key={paper.id} className="px-4 py-4 hover:bg-slate-50">
                <a
                  href={paperDetailUrl(paper.id)}
                  className="flex flex-col gap-1.5 sm:flex-row sm:items-center sm:justify-between"
                >
                  <span className="min-w-0">
                    <span className="block truncate font-medium text-slate-900">
                      {paper.title ?? (
                        <span className="italic text-slate-400">Untitled paper</span>
                      )}
                    </span>
                    <span className="mt-0.5 block text-xs text-slate-500">
                      {paper.doi ? `DOI ${paper.doi} · ` : ""}
                      Updated {formatDate(paper.updated_at)}
                    </span>
                  </span>
                  <span className="shrink-0">
                    <StatusBadge status={paper.workflow_status} />
                  </span>
                </a>
              </li>
            ))}
          </ul>
        </>
      )}
    </main>
  );
}
