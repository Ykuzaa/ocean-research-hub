import Link from "next/link";
import { listCorpusPapers } from "@/app/lib/api";

function one(value: string | string[] | undefined) { return Array.isArray(value) ? value[0] : value; }

export default async function ExplorePage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams;
  const q = one(params.q);
  const extractionState = one(params.extraction_state);
  const auditState = one(params.audit_state);
  const { papers, total } = await listCorpusPapers({ q, extractionState, auditState });
  return (
    <div className="mx-auto max-w-7xl px-5 py-10">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-tide-700">Collection structurée</p>
      <h1 className="mt-2 font-display text-4xl font-medium">Catalogue des papiers</h1>
      <p className="mt-3 max-w-3xl text-ink-600">Les états d’extraction, de vérification et de blocage sont indépendants. DETAILED ne signifie jamais vérifié.</p>
      <form className="mt-7 grid gap-3 rounded-2xl border border-rule bg-white p-4 md:grid-cols-[1fr_14rem_14rem_auto]">
        <input name="q" defaultValue={q} placeholder="Titre ou DOI" className="rounded-lg border border-rule px-3 py-2" />
        <select name="extraction_state" defaultValue={extractionState ?? ""} className="rounded-lg border border-rule px-3 py-2">
          <option value="">Toute extraction</option><option>READY_FOR_AUDIT</option><option>PARTIAL</option><option>NOT_EXTRACTED</option>
        </select>
        <select name="audit_state" defaultValue={auditState ?? ""} className="rounded-lg border border-rule px-3 py-2">
          <option value="">Tout audit</option><option>NOT_VERIFIED</option><option>PARTIALLY_VERIFIED</option><option>FULLY_VERIFIED</option>
        </select>
        <button className="rounded-lg bg-ink-900 px-5 py-2 text-white">Filtrer</button>
      </form>
      <p className="mt-5 text-sm text-ink-500">{papers.length} affichés sur {total}</p>
      <div className="mt-4 divide-y divide-rule rounded-2xl border border-rule bg-white">
        {papers.map((paper) => (
          <Link key={paper.paper_id} href={`/papers/${paper.paper_id}`} className="grid gap-3 p-5 transition hover:bg-sheet-1 md:grid-cols-[1fr_auto]">
            <div><p className="font-mono text-xs text-ink-400">{paper.paper_id}</p><h2 className="mt-1 text-lg font-semibold">{paper.title}</h2><p className="mt-1 text-sm text-ink-500">{[paper.year, paper.domain, paper.doi].filter(Boolean).join(" · ")}</p></div>
            <div className="flex flex-wrap items-start gap-2 text-xs md:max-w-md md:justify-end">
              <span className="rounded-full bg-sky-50 px-3 py-1 text-sky-800">{paper.extraction_completeness.state}</span>
              <span className="rounded-full bg-amber-50 px-3 py-1 text-amber-800">{paper.verification_state}</span>
              {paper.conflict_blocker_state !== "CLEAR" && <span className="rounded-full bg-red-50 px-3 py-1 text-red-800">{paper.conflict_blocker_state}</span>}
              <span className="rounded-full bg-sheet-2 px-3 py-1">{paper.claim_count} informations</span>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
