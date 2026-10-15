import Link from "next/link";
import { ApiError } from "@/app/lib/api";
import {
  DECISION_LABEL, familyLabel, fieldLabel, getReviewQueue, KIND_LABEL, RECHECK_LABEL,
  taskLabel, type Claim,
} from "@/app/lib/corpusV2";
import { Quote } from "../corpus/components/Quote";
import { getAuditor, recordVerdict } from "./actions";

function one(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] : value;
}

function show(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

/** What the auditor has to check, in the words of the claim's own kind. */
function contextLines(claim: Claim): string[] {
  const context = claim.context as Record<string, unknown>;
  const lines: string[] = [];
  if (context.task) lines.push(`objectif : ${taskLabel(String(context.task))}`);
  if (context.method) lines.push(`méthode : ${context.method}`);
  if (context.dataset) lines.push(`jeu de données : ${context.dataset}`);
  if (context.target) lines.push(`variable : ${context.target}`);
  if (context.split) lines.push(`découpe : ${context.split}`);
  if (context.config) lines.push(`configuration : ${context.config}`);
  if (context.baseline_name) lines.push(`référence comparée : ${context.baseline_name} = ${show(context.baseline_value)}`);
  if (context.family) lines.push(`famille retenue : ${familyLabel(String(context.family))}`);
  if (context.region) lines.push(`zone : ${context.region}`);
  if (context.reason) lines.push(`raison enregistrée : ${context.reason}`);
  if (context.claim) lines.push(`complète : ${context.claim}`);
  return lines;
}

export default async function RevuePage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const slug = one(params.slug);
  const error = one(params.error);
  const done = one(params.done);
  const auditor = await getAuditor();

  let queue;
  try {
    queue = await getReviewQueue({ slug, limit: 8 });
  } catch (failure) {
    const message = failure instanceof ApiError ? failure.message : "erreur inconnue";
    return (
      <div className="mx-auto max-w-3xl px-5 py-16">
        <h1 className="font-display text-3xl font-medium text-ink-900">File de revue indisponible</h1>
        <p className="mt-3 text-ink-600">
          L’API ne répond pas ({message}). Lance le serveur&nbsp;:{" "}
          <code className="font-mono text-sm">uv run uvicorn ocean_research_hub.api:app</code>
        </p>
      </div>
    );
  }

  const [claim, ...upcoming] = queue.claims;
  const progress = queue.progress;
  const checked = progress.audited;

  return (
    <div className="mx-auto max-w-4xl px-5 py-10">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-tide-500">Audit scientifique</p>
      <h1 className="mt-2 font-display text-4xl font-medium text-ink-900">Une information, sa phrase, ta décision</h1>
      <p className="mt-3 text-ink-600">
        L’extraction garantit que la citation existe bien sur la page citée. Elle ne garantit pas que la
        lecture est juste&nbsp;: ça, personne ne peut le dire à ta place.
      </p>

      <div className="mt-6 grid gap-3 rounded-2xl border border-rule bg-sheet-2 p-4 text-sm sm:grid-cols-4">
        <p><span className="block text-xs uppercase tracking-wide text-ink-400">vérifiées</span>{checked} / {progress.claims}</p>
        <p><span className="block text-xs uppercase tracking-wide text-ink-400">confirmées</span>{progress.accepted}</p>
        <p><span className="block text-xs uppercase tracking-wide text-ink-400">à corriger</span>{progress.needs_fix + progress.rejected}</p>
        <p><span className="block text-xs uppercase tracking-wide text-ink-400">en attente</span>{queue.pending}</p>
        <p className="sm:col-span-4 text-ink-600">
          Chaque information a déjà été relue une seconde fois par une machine indépendante,
          qui vérifie que la valeur est la bonne lecture du bon contexte. Ce n’est pas un audit :
          c’est ce qui te reste à faire.
        </p>
      </div>

      {slug ? (
        <p className="mt-3 text-sm text-ink-600">
          Filtré sur <span className="font-mono">{slug}</span> ·{" "}
          <Link href="/revue" className="text-tide-500 underline">tout le corpus</Link>
        </p>
      ) : null}

      {error ? (
        <p className="mt-4 rounded-xl border border-rule bg-sheet-1 p-3 text-sm text-ink-900">{error}</p>
      ) : null}
      {done ? (
        <p className="mt-4 rounded-xl border border-tide-300 bg-tide-200/40 p-3 text-sm text-ink-900">
          Enregistré : {DECISION_LABEL[done] ?? done}.
        </p>
      ) : null}

      {!claim ? (
        <section className="mt-8 rounded-2xl border border-rule bg-sheet-2 p-6">
          <h2 className="font-display text-2xl font-medium text-ink-900">Rien en attente ici</h2>
          <p className="mt-2 text-ink-600">
            {slug
              ? "Toutes les informations de ce papier ont un verdict."
              : "Tout le corpus a été audité. Une nouvelle extraction remettra en file les informations dont la valeur ou la citation change."}
          </p>
          <Link href="/corpus" className="mt-4 inline-block text-sm text-tide-500 underline">Retour au corpus</Link>
        </section>
      ) : (
        <section className="mt-8 rounded-2xl border border-rule bg-sheet-2 p-5">
          <header className="flex flex-wrap items-baseline justify-between gap-2">
            <div className="min-w-0">
              <p className="text-xs uppercase tracking-wide text-ink-400">{KIND_LABEL[claim.kind]}</p>
              <h2 className="mt-1 text-lg font-semibold text-ink-900">
                {fieldLabel(claim.field)}
              </h2>
            </div>
            {claim.audit_state === "STALE" ? (
              <span className="rounded-full bg-sheet-3 px-3 py-1 text-xs">
                verdict précédent périmé : la valeur ou la citation a changé
              </span>
            ) : null}
          </header>

          <p className="mt-3 text-sm text-ink-600">
            <Link href={`/corpus/${claim.slug}`} className="text-tide-500 underline">{claim.paper_title}</Link>
          </p>

          <p className="mt-4 font-mono text-2xl text-ink-900">
            {show(claim.value)}
            {claim.unit ? <span className="ml-2 text-base text-ink-400">{claim.unit}</span> : null}
          </p>

          <ul className="mt-3 grid gap-1 text-sm text-ink-600">
            {contextLines(claim).map((line) => <li key={line}>{line}</li>)}
          </ul>

          <div className="mt-4">
            <Quote quote={claim.quote} page={claim.page_printed ?? claim.page_pdf} />
            <p className="mt-2 font-mono text-[11px] text-ink-400">
              PDF page {claim.page_pdf}
              {claim.page_printed && claim.page_printed !== claim.page_pdf ? ` · page imprimée ${claim.page_printed}` : ""}
              {claim.pdf ? ` · ${claim.pdf}` : ""}
            </p>
            {claim.note ? <p className="mt-2 text-sm text-ink-600">Note d’extraction : {claim.note}</p> : null}
            <p className="mt-2 text-sm text-ink-600">
              Seconde lecture machine : {RECHECK_LABEL[claim.recheck_state]}
              {claim.recheck?.reason ? ` — ${claim.recheck.reason}` : ""}
            </p>
            {claim.recheck?.triage ? (
              <p className="mt-1 text-sm text-ink-600">Décision prise : {claim.recheck.triage.reason}</p>
            ) : null}
            {claim.evidence_status !== "QUOTED" && claim.quote ? (
              <p className="mt-2 text-sm text-ink-600">
                Statut : {claim.evidence_status} — la valeur a été lue, mais aucune phrase ne la porte seule.
              </p>
            ) : null}
          </div>

          <form action={recordVerdict} className="mt-6 grid gap-3 border-t border-rule pt-5">
            <input type="hidden" name="claim_id" value={claim.claim_id} />
            {slug ? <input type="hidden" name="slug" value={slug} /> : null}
            <label className="grid gap-1 text-sm">
              <span className="text-ink-400">Ton nom (il signe le verdict)</span>
              <input
                name="auditor"
                defaultValue={auditor}
                required
                className="rounded-lg border border-rule px-3 py-2"
              />
            </label>
            <label className="grid gap-1 text-sm">
              <span className="text-ink-400">Ce que tu as constaté (obligatoire si tu corriges ou rejettes)</span>
              <textarea name="note" rows={2} className="rounded-lg border border-rule px-3 py-2" />
            </label>
            <div className="flex flex-wrap gap-3">
              <button
                name="decision"
                value="ACCEPTED"
                className="rounded-lg bg-ink-900 px-5 py-2 text-sm text-white"
              >
                La phrase dit bien ça
              </button>
              <button
                name="decision"
                value="NEEDS_FIX"
                className="rounded-lg border border-rule px-5 py-2 text-sm text-ink-900"
              >
                À corriger
              </button>
              <button
                name="decision"
                value="REJECTED"
                className="rounded-lg border border-rule px-5 py-2 text-sm text-ink-900"
              >
                Le papier ne dit pas ça
              </button>
            </div>
          </form>
        </section>
      )}

      {upcoming.length > 0 && (
        <section className="mt-8">
          <h2 className="text-xs uppercase tracking-wide text-ink-400">Ensuite</h2>
          <ul className="mt-3 divide-y divide-rule overflow-hidden rounded-2xl border border-rule bg-sheet-2 text-sm">
            {upcoming.map((next) => (
              <li key={next.claim_id} className="flex min-w-0 flex-wrap items-baseline gap-x-3 gap-y-1 px-4 py-3">
                <span className="text-xs uppercase tracking-wide text-ink-400">{KIND_LABEL[next.kind]}</span>
                <span className="font-mono text-ink-900">{show(next.value)}</span>
                <span className="text-ink-600">{fieldLabel(next.field)}</span>
                <Link href={`/corpus/${next.slug}`} className="ml-auto min-w-0 truncate text-xs text-tide-500">
                  {next.paper_title}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
