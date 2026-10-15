import Link from "next/link";
import { getCorpusPaper, listCorpusPapers, type CorpusClaim, type CorpusPaper } from "@/app/lib/api";

function first(value: string | string[] | undefined) { return Array.isArray(value) ? value[0] : value; }

function claimsByOriginalPath(paper: CorpusPaper): Map<string, CorpusClaim[]> {
  const paths = new Map<string, CorpusClaim[]>();
  for (const field of paper.fields) {
    if (field.claims.length) paths.set(field.field_path, field.claims);
  }
  for (const claim of paper.uncontracted_claims) {
    paths.set(claim.field_path, [...(paths.get(claim.field_path) ?? []), claim]);
  }
  return paths;
}

function Cell({ claims }: { claims: CorpusClaim[] }) {
  if (!claims.length) return <span className="text-ink-400">NOT_EXTRACTED</span>;
  return <div className="space-y-3">{claims.map((claim) => <div key={claim.claim_id}>
    <Link href={`/claims/${claim.claim_id}`} className="font-mono text-xs text-tide-700">{claim.claim_id} ↗</Link>
    <p>{typeof claim.value === "string" ? claim.value : JSON.stringify(claim.value)} {claim.unit}</p>
    <p className="text-xs text-ink-500">{claim.verification_state} · {claim.experiment_id || "expérience non précisée"}</p>
  </div>)}</div>;
}

export default async function ComparePage({ searchParams }: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const leftId = first(params.left_id) || "";
  const rightId = first(params.right_id) || "";
  const catalog = await listCorpusPapers({ limit: 500 });
  const [left, right] = leftId && rightId && leftId !== rightId
    ? await Promise.all([getCorpusPaper(leftId), getCorpusPaper(rightId)])
    : [null, null];
  const leftPaths = left ? claimsByOriginalPath(left) : new Map<string, CorpusClaim[]>();
  const rightPaths = right ? claimsByOriginalPath(right) : new Map<string, CorpusClaim[]>();
  const paths = [...new Set([...leftPaths.keys(), ...rightPaths.keys()])].sort();
  return <div className="mx-auto max-w-7xl px-5 py-10">
    <Link href="/explore" className="text-sm text-tide-700">← Catalogue</Link>
    <h1 className="mt-4 font-display text-4xl">Comparer deux papiers</h1>
    <p className="mt-2 text-ink-600">Les lignes suivent les chemins originaux du corpus. Chaque valeur ouvre sa preuve et son historique.</p>
    <form className="mt-6 flex flex-wrap items-end gap-3 rounded-xl border border-rule bg-white p-4">
      {(["left_id", "right_id"] as const).map((name) => <label key={name} className="flex min-w-56 flex-1 flex-col gap-1 text-sm">
        {name === "left_id" ? "Premier papier" : "Second papier"}
        <select name={name} defaultValue={name === "left_id" ? leftId : rightId} className="rounded-lg border border-rule p-2">
          <option value="">Choisir un papier</option>
          {catalog.papers.map((paper) => <option value={paper.paper_id} key={paper.paper_id}>{paper.paper_id} · {paper.title}</option>)}
        </select>
      </label>)}
      <button className="rounded-lg bg-ink-900 px-5 py-2 text-white">Comparer</button>
    </form>
    {leftId && rightId && leftId === rightId && <p className="mt-4 text-amber-800">Choisissez deux papiers distincts.</p>}
    {left && right && <>
      <div className="mt-8 grid gap-4 md:grid-cols-2">{[left, right].map((paper) => <div key={paper.paper_id} className="rounded-xl border border-rule bg-white p-4">
        <Link href={`/papers/${paper.paper_id}`} className="font-semibold text-tide-700">{paper.title}</Link>
        <p className="mt-2 text-sm">Extraction : {paper.extraction_completeness.state} · Audit : {paper.verification_state} · Blocage : {paper.conflict_blocker_state}</p>
      </div>)}</div>
      <div className="mt-6 overflow-x-auto rounded-xl border border-rule bg-white"><table className="w-full table-fixed border-collapse text-left text-sm">
        <thead><tr className="bg-sheet-1"><th className="w-1/5 p-3">Champ d’origine</th><th className="w-2/5 p-3">{left.paper_id}</th><th className="w-2/5 p-3">{right.paper_id}</th></tr></thead>
        <tbody>{paths.map((path) => <tr key={path} className="border-t border-rule align-top"><th className="break-words p-3 font-mono font-normal">{path}</th><td className="p-3"><Cell claims={leftPaths.get(path) ?? []} /></td><td className="p-3"><Cell claims={rightPaths.get(path) ?? []} /></td></tr>)}</tbody>
      </table></div>
    </>}
  </div>;
}
