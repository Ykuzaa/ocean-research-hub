import Link from "next/link";
import { notFound } from "next/navigation";
import { ApiError } from "@/app/lib/api";
import {
  familyLabel, fieldLabel, getCorpusV2Paper, roleLabel, taskLabel, type ResultRow,
} from "@/app/lib/corpusV2";
import { Quote, ValueWithSource } from "../components/Quote";

const THEME_LABEL: Record<string, string> = {
  DATA: "données",
  COMPUTE: "calcul",
  GENERALIZATION: "généralisation",
  PHYSICS: "physique",
  UNCERTAINTY: "incertitude",
  REPRODUCIBILITY: "reproductibilité",
  EVALUATION: "évaluation",
  FUTURE_WORK: "suite annoncée",
  OTHER: "autre",
};

function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <section className="mt-10">
      <h2 className="font-display text-2xl font-medium text-ink-900">{title}</h2>
      {hint ? <p className="mt-1 text-sm text-ink-400">{hint}</p> : null}
      <div className="mt-4 grid min-w-0 gap-3 [&>*]:min-w-0">{children}</div>
    </section>
  );
}

function Results({ rows }: { rows: ResultRow[] }) {
  if (rows.length === 0) {
    return (
      <p className="text-sm text-ink-600">
        Aucun résultat chiffré lisible dans le texte. Ce que le papier mesure vit dans ses figures ;
        aucune valeur n’a été relevée sur une courbe.
      </p>
    );
  }
  return (
    <div className="overflow-x-auto rounded-xl border border-rule">
      <table className="w-full min-w-[42rem] border-collapse text-sm">
        <thead className="bg-sheet-1 text-left text-xs uppercase tracking-wide text-ink-400">
          <tr>
            <th className="px-3 py-2 font-medium">Mesure</th>
            <th className="px-3 py-2 font-medium">Valeur</th>
            <th className="px-3 py-2 font-medium">Référence comparée</th>
            <th className="px-3 py-2 font-medium">Configuration</th>
            <th className="px-3 py-2 font-medium">Phrase source</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-rule">
          {rows.map((row, index) => (
            <tr key={index} className="align-top">
              <td className="px-3 py-2">
                <span className="font-medium text-ink-900">{row.metric}</span>
                {row.metric_raw && row.metric_raw !== row.metric ? (
                  <span className="block text-xs text-ink-400">imprimé « {row.metric_raw} »</span>
                ) : null}
                {row.dataset ? <span className="block text-xs text-ink-400">{row.dataset}</span> : null}
              </td>
              <td className="px-3 py-2 font-mono text-ink-900">
                {row.value}
                {row.unit ? <span className="ml-1 text-ink-400">{row.unit}</span> : null}
                {row.is_best_in_table ? (
                  <span className="ml-2 rounded-full bg-tide-200/60 px-2 py-0.5 text-[11px]">meilleur du tableau</span>
                ) : null}
              </td>
              <td className="px-3 py-2 text-ink-600">
                {row.baseline_name ? (
                  <>
                    {row.baseline_name}
                    {row.baseline_value !== null ? (
                      <span className="block font-mono text-ink-900">{row.baseline_value}</span>
                    ) : null}
                  </>
                ) : (
                  <span className="text-ink-400">aucune</span>
                )}
              </td>
              <td className="px-3 py-2 text-ink-600">
                {[row.config, row.split].filter(Boolean).join(" · ") || <span className="text-ink-400">—</span>}
              </td>
              <td className="px-3 py-2">
                <details>
                  <summary className="cursor-pointer text-xs text-tide-500">
                    page {row.page}{row.quote ? "" : " · lue sur la page"}
                  </summary>
                  <div className="mt-2 w-[22rem]">
                    <Quote quote={row.quote} page={row.page} />
                  </div>
                </details>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default async function CorpusPaperPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  let paper;
  try {
    paper = await getCorpusV2Paper(slug);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    const message = error instanceof ApiError ? error.message : "erreur inconnue";
    return (
      <div className="mx-auto max-w-3xl px-5 py-16">
        <h1 className="font-display text-3xl font-medium text-ink-900">Fiche indisponible</h1>
        <p className="mt-3 text-ink-600">L’API ne répond pas ({message}).</p>
      </div>
    );
  }

  const reported = paper.experiments.reduce((count, e) => count + e.training.length, 0);

  return (
    <div className="mx-auto max-w-5xl px-5 py-10">
      <Link href="/corpus" className="text-sm text-tide-500">← Corpus</Link>
      <h1 className="mt-3 font-display text-3xl font-medium leading-tight text-ink-900">{paper.title}</h1>
      <p className="mt-2 text-sm text-ink-400">
        {[paper.year, paper.venue, paper.doi].filter(Boolean).join(" · ")}
      </p>
      <p className="mt-4 flex flex-wrap gap-2 text-xs text-ink-600">
        {paper.domains.map((domain) => (
          <span key={domain} className="rounded-full bg-sheet-3 px-2.5 py-1">{domain}</span>
        ))}
      </p>

      <div className="mt-6 grid gap-3 rounded-2xl border border-rule bg-sheet-2 p-4 text-sm sm:grid-cols-4">
        <p><span className="block text-xs uppercase tracking-wide text-ink-400">expériences</span>{paper.experiment_count}</p>
        <p><span className="block text-xs uppercase tracking-wide text-ink-400">résultats</span>{paper.result_count}</p>
        <p><span className="block text-xs uppercase tracking-wide text-ink-400">réglages donnés</span>{reported}</p>
        <p><span className="block text-xs uppercase tracking-wide text-ink-400">confirmés à la main</span>{paper.audit?.accepted ?? 0}/{paper.claim_count}</p>
      </div>
      <p className="mt-2 font-mono text-[11px] text-ink-400">
        PDF {paper.source.pdf_pages} pages · sha256 {paper.source.sha256_prefix}
        {paper.source.printed_page_offset ? ` · décalage pagination ${paper.source.printed_page_offset}` : ""}
      </p>

      {paper.excluded_evidence ? (
        <Section title="Papier écarté" hint="Ce papier n’entraîne aucun modèle : rien n’en a été extrait.">
          <p className="text-sm text-ink-600">{paper.excluded_evidence.reason}</p>
          <Quote quote={paper.excluded_evidence.quote ?? null} page={paper.excluded_evidence.page_pdf ?? null} />
        </Section>
      ) : null}

      {paper.methods.length > 0 && (
        <Section title="Méthodes" hint="La famille est une classification ; la phrase citée est ce que le papier dit.">
          {paper.methods.map((method) => (
            <article key={method.name} className="rounded-xl border border-rule bg-sheet-2 p-4">
              <header className="flex flex-wrap items-baseline gap-2">
                <h3 className="text-base font-semibold text-ink-900">{method.name}</h3>
                <span className="rounded-full bg-tide-200/50 px-2.5 py-1 text-xs">
                  {familyLabel(method.family)}
                </span>
                {method.role ? <span className="text-xs text-ink-400">{method.role === "PROPOSED" ? "proposée" : "référence"}</span> : null}
                {method.is_novel_in_paper ? <span className="text-xs text-ink-400">nouveauté du papier</span> : null}
              </header>
              {method.architecture_note ? (
                <p className="mt-2 text-sm text-ink-600">{method.architecture_note}</p>
              ) : null}
              <div className="mt-3 grid gap-2">
                {method.evidence.map((evidence, index) => (
                  <Quote key={index} quote={evidence.quote} page={evidence.page} label={evidence.field ? fieldLabel(evidence.field) : undefined} />
                ))}
              </div>
            </article>
          ))}
        </Section>
      )}

      {paper.dataset_records.length > 0 && (
        <Section title="Données">
          {paper.dataset_records.map((dataset) => (
            <article key={dataset.name} className="rounded-xl border border-rule bg-sheet-2 p-4">
              <header className="flex flex-wrap items-baseline gap-2">
                <h3 className="text-base font-semibold text-ink-900">{dataset.name}</h3>
                {dataset.role ? <span className="text-xs text-ink-400">{roleLabel(dataset.role)}</span> : null}
              </header>
              <dl className="mt-2 grid gap-x-6 gap-y-1 text-sm text-ink-600 sm:grid-cols-2">
                {dataset.variables.length > 0 && <p>variables : {dataset.variables.join(", ")}</p>}
                {dataset.spatial_resolution && <p>résolution spatiale : {dataset.spatial_resolution}</p>}
                {dataset.temporal_resolution && <p>résolution temporelle : {dataset.temporal_resolution}</p>}
                {dataset.region && <p>zone : {dataset.region}</p>}
                {(dataset.period[0] || dataset.period[1]) && <p>période : {dataset.period.filter(Boolean).join(" → ")}</p>}
              </dl>
              <div className="mt-3 grid gap-2">
                {dataset.evidence.map((evidence, index) => (
                  <Quote key={index} quote={evidence.quote} page={evidence.page} label={evidence.field ? fieldLabel(evidence.field) : undefined} />
                ))}
              </div>
            </article>
          ))}
        </Section>
      )}

      <Section title="Expériences" hint="Une expérience par objectif et par jeu de données : jamais fusionnées.">
        {paper.experiments.map((experiment) => (
          <article key={experiment.id} className="min-w-0 rounded-2xl border border-rule bg-sheet-2 p-4">
            <header>
              <p className="font-mono text-xs text-ink-400">{experiment.id}</p>
              <h3 className="mt-1 text-base font-semibold text-ink-900">
                {taskLabel(experiment.task)}
                {experiment.target ? <span className="text-ink-600"> · {experiment.target}</span> : null}
              </h3>
              <p className="mt-1 text-sm text-ink-400">
                {[experiment.method, experiment.datasets.join(", ")].filter(Boolean).join(" · ")}
              </p>
              {experiment.note ? <p className="mt-2 text-sm text-ink-600">{experiment.note}</p> : null}
            </header>

            <div className="mt-4 grid min-w-0 items-start gap-2 [&>*]:min-w-0 md:grid-cols-2">
              {experiment.training.map((value) => (
                <ValueWithSource
                  key={value.field}
                  label={fieldLabel(value.field)}
                  value={typeof value.value === "object" ? JSON.stringify(value.value) : String(value.value)}
                  unit={value.unit}
                  quote={value.quote}
                  page={value.page}
                  note={value.note}
                >
                  {value.extra_evidence.length > 0 && (
                    <div className="grid gap-2">
                      <p className="text-xs uppercase tracking-wide text-ink-400">preuves complémentaires</p>
                      {value.extra_evidence.map((extra, index) => (
                        <Quote key={index} quote={extra.quote} page={extra.page} label={extra.claim ?? undefined} />
                      ))}
                    </div>
                  )}
                </ValueWithSource>
              ))}
            </div>

            <div className="mt-4 min-w-0">
              <Results rows={experiment.results} />
            </div>
          </article>
        ))}
        {paper.orphan_results.length > 0 && (
          <div>
            <p className="text-sm text-ink-400">Résultats non rattachés à une expérience</p>
            <Results rows={paper.orphan_results} />
          </div>
        )}
      </Section>

      {paper.not_reported.length > 0 && (
        <Section title="Ce que le papier ne dit pas" hint="Cherché puis non trouvé, avec le périmètre de la recherche. L’absence est un constat, pas un trou.">
          <ul className="grid gap-2 text-sm">
            {paper.not_reported.map((item) => (
              <li key={item.field} className="rounded-lg border border-rule bg-sheet-1 px-3 py-2">
                <span className="font-mono text-xs text-ink-900">{item.field.split(".").pop()}</span>
                {item.searched.length > 0 && (
                  <span className="text-ink-400"> — cherché dans : {item.searched.join(", ")}</span>
                )}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {paper.conflicts.length > 0 && (
        <Section title="Valeurs contradictoires" hint="Le papier donne deux valeurs ; les deux sont conservées.">
          {paper.conflicts.map((conflict, index) => (
            <article key={index} className="rounded-xl border border-rule bg-sheet-2 p-4">
              <p className="font-mono text-xs text-ink-400">{conflict.field}</p>
              <p className="mt-1 text-sm text-ink-900">
                {conflict.values.map((value) => String(value)).join("  vs  ")} → retenu :{" "}
                <span className="font-mono">{String(conflict.chosen)}</span>
              </p>
              {conflict.reason ? <p className="mt-1 text-sm text-ink-600">{conflict.reason}</p> : null}
              <div className="mt-3 grid gap-2">
                {conflict.sources.map((source, position) => (
                  <Quote key={position} quote={source.quote} page={source.page} />
                ))}
              </div>
            </article>
          ))}
        </Section>
      )}

      {paper.limitations.length > 0 && (
        <Section title="Limites annoncées" hint="Les auteurs les écrivent eux-mêmes ; rien n’est déduit.">
          {paper.limitations.map((limitation, index) => (
            <Quote
              key={index}
              quote={limitation.quote}
              page={limitation.page}
              label={THEME_LABEL[limitation.theme] ?? limitation.theme}
            />
          ))}
        </Section>
      )}

      <p className="mt-10 rounded-xl border border-rule bg-sheet-1 p-4 text-sm text-ink-600">
        {paper.claim_count} informations sourcées, {paper.audit?.accepted ?? 0} confirmées à la main.{" "}
        <Link href={`/revue?slug=${paper.slug}`} className="text-tide-500 underline">
          Auditer ce papier
        </Link>
      </p>
    </div>
  );
}
