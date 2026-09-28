import Link from "next/link";
import { notFound } from "next/navigation";
import { ApiError, getCorpusPaper, type CorpusClaim, type CorpusMarker } from "@/app/lib/api";

function shown(value: unknown) { return typeof value === "string" ? value : JSON.stringify(value); }
function Claim({ claim }: { claim: CorpusClaim }) {
  const source = claim.evidence;
  return <article className="rounded-xl border border-rule bg-white p-4">
    <div className="flex flex-wrap justify-between gap-2"><Link href={`/claims/${claim.claim_id}`} className="font-mono text-xs text-tide-700">{claim.claim_id}</Link><span className="font-mono text-xs">{claim.verification_state}</span></div>
    <p className="mt-2 leading-relaxed">{shown(claim.value)} {claim.unit && <strong>{claim.unit}</strong>}</p>
    <p className="mt-2 text-xs text-ink-500">{[claim.experiment_id, claim.claim_type, source.source_edition].filter(Boolean).join(" · ")}</p>
    <details className="mt-3"><summary className="cursor-pointer text-sm font-medium text-tide-700">Voir la preuve et le locator</summary><div className="mt-2 border-l-2 border-tide-200 pl-3 text-sm text-ink-600"><p>{[source.pdf_page ? `p. ${source.pdf_page}` : null, source.section, source.locator].filter(Boolean).join(" · ") || "Locator non fourni"}</p><p className="mt-1">{source.verbatim_evidence || "Aucun extrait verbatim fourni par le classeur."}</p>{source.source_url && <a href={source.source_url} className="mt-2 inline-block text-tide-700">Ouvrir la source déclarée</a>}</div></details>
  </article>;
}

export default async function CorpusPaperPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let paper;
  try { paper = await getCorpusPaper(id); } catch (error) { if (error instanceof ApiError && error.status === 404) notFound(); throw error; }
  type Entry = { field_path: string; status: string; claims: CorpusClaim[]; markers: CorpusMarker[]; outsideContract: boolean };
  const entries = new Map<string, Entry>();
  for (const field of paper.fields) if (field.claims.length || field.markers.length) {
    entries.set(field.field_path, { field_path: field.field_path, status: field.status,
      claims: field.claims, markers: field.markers, outsideContract: false });
  }
  for (const claim of paper.uncontracted_claims) {
    const entry = entries.get(claim.field_path) ?? { field_path: claim.field_path, status: "NOT_VERIFIED",
      claims: [], markers: [], outsideContract: true };
    entry.claims.push(claim);
    entries.set(claim.field_path, entry);
  }
  for (const marker of paper.uncontracted_markers) {
    const entry = entries.get(marker.field_path) ?? { field_path: marker.field_path, status: marker.extraction_status,
      claims: [], markers: [], outsideContract: true };
    entry.markers.push(marker);
    entries.set(marker.field_path, entry);
  }
  const groups = new Map<string, Entry[]>();
  for (const entry of [...entries.values()].sort((a, b) => a.field_path.localeCompare(b.field_path))) {
    const group = entry.field_path.split(".", 1)[0];
    groups.set(group, [...(groups.get(group) ?? []), entry]);
  }
  return <div className="mx-auto max-w-7xl px-5 py-10">
    <Link href="/explore" className="text-sm text-tide-700">← Catalogue</Link>
    <h1 className="mt-4 max-w-5xl font-display text-4xl font-medium">{paper.title}</h1>
    <p className="mt-2 text-ink-500">{[paper.paper_id, paper.year, paper.doi].filter(Boolean).join(" · ")}</p>
    <div className="mt-5 flex flex-wrap gap-2 text-xs"><span className="rounded-full bg-sky-50 px-3 py-1">Extraction {paper.extraction_completeness.state}</span><span className="rounded-full bg-amber-50 px-3 py-1">Audit {paper.verification_state}</span><span className="rounded-full bg-sheet-2 px-3 py-1">Blocage {paper.conflict_blocker_state}</span></div>
    {paper.extraction_completeness.follow_up && <p className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm">Travail restant déclaré : {paper.extraction_completeness.follow_up}</p>}
    <div className="mt-10 space-y-10">
      {[...groups.entries()].map(([group, fields]) => <section key={group}><h2 className="font-display text-2xl capitalize">{group}</h2><div className="mt-4 space-y-5">{fields.map((field) => <div key={field.field_path}><div className="mb-2 flex flex-wrap items-baseline gap-3"><h3 className="font-mono text-sm">{field.field_path}</h3><span className="text-xs text-ink-400">{field.status}</span>{field.outsideContract && <span className="text-xs text-ink-400">Chemin original hors contrat, mapping en attente</span>}</div><div className="grid gap-3 lg:grid-cols-2">{field.claims.map((claim) => <Claim key={claim.claim_id} claim={claim} />)}</div>{field.markers.map((marker) => <p key={marker.marker_id} className="mt-2 rounded-lg border border-dashed border-rule p-3 text-sm">{marker.extraction_status} — périmètre déclaré : {marker.section_or_scope || "non documenté"}</p>)}</div>)}</div></section>)}
    </div>
    <details className="mt-10 rounded-xl border border-rule bg-white p-4"><summary className="cursor-pointer font-medium">Complétude : {paper.not_extracted_field_count} champs du contrat non extraits</summary><div className="mt-3 flex flex-wrap gap-2">{paper.fields.filter((field) => !field.claims.length && !field.markers.length).map((field) => <code key={field.field_path} className="rounded bg-sheet-2 px-2 py-1 text-xs">{field.field_path}</code>)}</div></details>
  </div>;
}
