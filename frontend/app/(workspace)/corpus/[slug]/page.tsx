import Link from "next/link";
import { notFound } from "next/navigation";
import { ApiError } from "@/app/lib/api";
import {
  EDITION_CAVEAT, EDITION_LABEL,
  familyLabel, fieldLabel, getCorpusV2Paper, roleLabel, taskLabel,
  type PaperDetailV2, type ResultRow, type TrainingValue,
} from "@/app/lib/corpusV2";
import { Quote, ValueWithSource } from "../components/Quote";

/**
 * La fiche d'un papier : une phrase qui répond, quatre questions, puis tout en tableau.
 *
 * La forme vient d'un choix de l'utilisateur entre deux maquettes. En haut, la réponse
 * tout de suite et les citations repliées ; en bas, le même contenu visible d'un coup
 * pour qui veut balayer sans cliquer.
 *
 * Ce que cette page ne montre jamais : les identifiants internes (`X-...`, `M-...`, les
 * chemins de champ comme `results[2].value`) et l'empreinte sha256. Ce sont des repères
 * de développeur ; un lecteur n'en fait rien.
 */

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

function unique(values: Array<string | null | undefined>): string[] {
  return [...new Set(values.filter((value): value is string => Boolean(value)))];
}

function list(values: string[]): string {
  if (values.length <= 1) return values[0] ?? "";
  return `${values.slice(0, -1).join(", ")} et ${values[values.length - 1]}`;
}

function lower(text: string): string {
  return text ? text[0].toLowerCase() + text.slice(1) : text;
}

function asText(value: unknown): string {
  return typeof value === "object" && value !== null ? JSON.stringify(value) : String(value);
}

function Evidences({ items, summary }: { items: Array<{ field?: string | null; page: number | null; quote: string | null }>; summary: string }) {
  if (items.length === 0) return null;
  return (
    <details className="mt-2">
      <summary className="cursor-pointer text-xs text-tide-500">{summary}</summary>
      <div className="mt-2 grid gap-2">
        {items.map((evidence, index) => (
          <Quote
            key={index}
            quote={evidence.quote}
            page={evidence.page}
            label={evidence.field ? fieldLabel(evidence.field) : undefined}
          />
        ))}
      </div>
    </details>
  );
}

/** La phrase du haut : ce que le papier fait, avec quoi, à partir de quelles données. */
function Summary({ paper }: { paper: PaperDetailV2 }) {
  const tasks = unique(paper.experiments.map((experiment) => lower(taskLabel(experiment.task))));
  const proposed = unique(paper.methods.filter((method) => method.role === "PROPOSED").map((method) => method.name));
  const models = proposed.length > 0 ? proposed : unique(paper.experiments.map((experiment) => experiment.method));
  const data = unique(paper.experiments.flatMap((experiment) => experiment.datasets));
  const targets = unique(paper.experiments.map((experiment) => experiment.target));

  if (tasks.length === 0 && models.length === 0) return null;

  return (
    <div className="mt-6 rounded-2xl bg-tide-200/40 p-5 text-base leading-relaxed text-ink-900">
      <p>
        {tasks.length > 0
          ? <>Ce papier fait de la <strong className="font-semibold">{list(tasks)}</strong></>
          : <>Ce papier</>}
        {models.length > 0 ? <> avec <strong className="font-semibold">{list(models)}</strong></> : null}
        {data.length > 0 ? <>, à partir de <strong className="font-semibold">{list(data)}</strong></> : null}
        .
      </p>
      {targets.length > 0 ? <p className="mt-2 text-ink-600">Il prédit : {targets.join(" ; ")}.</p> : null}
    </div>
  );
}

/** Un résultat lisible seul : la valeur en grand, ce qu'elle mesure, la phrase repliée. */
function ResultCard({ row }: { row: ResultRow }) {
  return (
    <article className="min-w-0 rounded-xl border border-rule bg-sheet-2 p-4">
      <p className="font-display text-2xl font-medium text-ink-900">
        {row.value}
        {row.unit ? <span className="ml-1 text-base text-ink-400">{row.unit}</span> : null}
        {row.is_best_in_table ? (
          <span className="ml-2 align-middle rounded-full bg-tide-200/60 px-2 py-0.5 text-[11px] font-normal">
            meilleur du tableau
          </span>
        ) : null}
      </p>
      <p className="mt-1 break-words text-sm text-ink-900">
        {row.metric_raw || row.metric || "résultat"}
        {row.dataset ? <span className="text-ink-400"> · {row.dataset}</span> : null}
      </p>
      {row.baseline_name ? (
        <p className="mt-1 break-words text-sm text-ink-600">
          comparé à {row.baseline_name}
          {row.baseline_value !== null ? <span className="font-mono text-ink-900"> ({row.baseline_value})</span> : null}
        </p>
      ) : null}
      {[row.config, row.split].filter(Boolean).length > 0 ? (
        <p className="mt-1 break-words text-sm text-ink-400">{[row.config, row.split].filter(Boolean).join(" · ")}</p>
      ) : null}
      {row.note ? <p className="mt-1 break-words text-sm text-ink-400">{row.note}</p> : null}
      <details className="mt-2">
        <summary className="cursor-pointer text-xs text-tide-500">
          {row.quote ? "voir la phrase du papier" : "lue sur la page, sans citation"}
        </summary>
        <div className="mt-2">
          <Quote quote={row.quote} page={row.page} />
        </div>
      </details>
    </article>
  );
}

function Training({ values }: { values: TrainingValue[] }) {
  return (
    <div className="grid min-w-0 items-start gap-2 [&>*]:min-w-0 md:grid-cols-2">
      {values.map((value) => (
        <ValueWithSource
          key={value.field}
          label={fieldLabel(value.field)}
          value={asText(value.value)}
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
  );
}

/** Le tableau du bas : chaque fait à gauche, la phrase du papier à droite, rien de replié. */
function EverythingTable({ paper }: { paper: PaperDetailV2 }) {
  const rows: Array<{ label: string; value: string; quote: string | null; page: number | null }> = [];

  for (const experiment of paper.experiments) {
    rows.push({ label: "objectif", value: taskLabel(experiment.task), quote: null, page: null });
    if (experiment.target) {
      rows.push({ label: "ce qu'il prédit", value: experiment.target, quote: null, page: null });
    }
  }
  for (const method of paper.methods) {
    rows.push({
      label: method.role === "PROPOSED" ? "modèle proposé" : "comparé à",
      value: `${method.name} — ${familyLabel(method.family)}`,
      quote: method.evidence[0]?.quote ?? null,
      page: method.evidence[0]?.page ?? null,
    });
  }
  for (const dataset of paper.dataset_records) {
    rows.push({
      label: "données",
      value: [dataset.name, dataset.spatial_resolution, dataset.period.filter(Boolean).join(" → ")]
        .filter(Boolean).join(" — "),
      quote: dataset.evidence[0]?.quote ?? null,
      page: dataset.evidence[0]?.page ?? null,
    });
  }
  for (const experiment of paper.experiments) {
    for (const value of experiment.training) {
      rows.push({
        label: fieldLabel(value.field),
        value: [asText(value.value), value.unit].filter(Boolean).join(" "),
        quote: value.quote,
        page: value.page,
      });
    }
  }
  for (const result of [...paper.experiments.flatMap((e) => e.results), ...paper.orphan_results]) {
    rows.push({
      label: result.metric_raw || result.metric || "résultat",
      value: [result.value, result.unit].filter((part) => part !== null && part !== "").join(" "),
      quote: result.quote,
      page: result.page,
    });
  }
  for (const item of paper.not_reported) {
    rows.push({
      label: "non indiqué par les auteurs",
      value: fieldLabel(item.field.split(".").pop() ?? item.field)
        + (item.searched.length > 0 ? ` — cherché dans : ${item.searched.join(", ")}` : ""),
      quote: null,
      page: null,
    });
  }
  for (const limitation of paper.limitations) {
    rows.push({
      label: `limite — ${THEME_LABEL[limitation.theme] ?? limitation.theme}`,
      value: "reconnue par les auteurs",
      quote: limitation.quote,
      page: limitation.page,
    });
  }

  if (rows.length === 0) return null;

  return (
    <div className="overflow-hidden rounded-2xl border border-rule">
      <div className="grid grid-cols-[minmax(0,1fr)] md:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <div className="hidden bg-sheet-1 px-4 py-2 text-xs uppercase tracking-wide text-ink-400 md:block">
          ce que le papier fait
        </div>
        <div className="hidden bg-sheet-1 px-4 py-2 text-xs uppercase tracking-wide text-ink-400 md:block">
          la phrase du papier
        </div>
        {rows.map((row, index) => (
          <div key={index} className="contents">
            <div className="min-w-0 border-t border-rule px-4 py-3 text-sm">
              <span className="block text-ink-400">{row.label}</span>
              <span className="block break-words font-medium text-ink-900">{row.value}</span>
            </div>
            <div className="min-w-0 break-words border-t border-rule bg-sheet-1 px-4 py-3 text-sm text-ink-600 md:border-l">
              {row.quote ? (
                <>
                  « {row.quote} »
                  <span className="ml-1 font-mono text-[11px] text-ink-400">page {row.page}</span>
                </>
              ) : (
                <span className="text-ink-400">—</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default async function CorpusPaperPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  let paper: PaperDetailV2;
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

  const proposed = paper.methods.filter((method) => method.role === "PROPOSED");
  const baselines = paper.methods.filter((method) => method.role !== "PROPOSED");
  const allResults = [...paper.experiments.flatMap((experiment) => experiment.results), ...paper.orphan_results];
  const allTraining = paper.experiments.flatMap((experiment) => experiment.training);

  return (
    <div className="mx-auto max-w-5xl px-5 py-10">
      <Link href="/corpus" className="text-sm text-tide-500">← Corpus</Link>
      <h1 className="mt-3 font-display text-3xl font-medium leading-tight text-ink-900">{paper.title}</h1>
      <p className="mt-2 text-sm text-ink-400">
        {[paper.year, paper.venue, paper.doi, `${paper.source.pdf_pages} pages`].filter(Boolean).join(" · ")}
      </p>
      <p className="mt-4 flex flex-wrap gap-2 text-xs text-ink-600">
        {paper.domains.map((domain) => (
          <span key={domain} className="rounded-full bg-sheet-3 px-2.5 py-1">{domain}</span>
        ))}
      </p>

      {paper.excluded_evidence ? (
        <Section title="Papier écarté" hint="Ce papier n’entraîne aucun modèle : rien n’en a été extrait.">
          <p className="text-sm text-ink-600">{paper.excluded_evidence.reason}</p>
          <Quote quote={paper.excluded_evidence.quote ?? null} page={paper.excluded_evidence.page_pdf ?? null} />
        </Section>
      ) : (
        <Summary paper={paper} />
      )}

      {paper.source.edition ? (
        <div className="mt-4 rounded-2xl border border-rule bg-sheet-2 p-4 text-sm">
          <p className="text-ink-900">
            <span className="font-medium">Fichier lu : {EDITION_LABEL[paper.source.edition]}.</span>{" "}
            <span className="text-ink-600">{EDITION_CAVEAT[paper.source.edition]}</span>
          </p>
          {paper.source.edition_evidence ? (
            <Evidences
              summary="voir la phrase du papier"
              items={[{ quote: paper.source.edition_evidence.quote, page: paper.source.edition_evidence.page_pdf }]}
            />
          ) : null}
          {paper.source.resolved_from ? (
            <p className="mt-2 text-xs text-ink-400">
              Fichier retrouvé à partir du DOI {paper.source.resolved_from.doi} ({paper.source.resolved_from.via}).{" "}
              {paper.source.resolved_from.note}
            </p>
          ) : null}
        </div>
      ) : null}

      {paper.methods.length > 0 && (
        <Section title="Quel modèle ?" hint="La famille est un classement ; la phrase citée est ce que le papier dit.">
          {[
            { key: "proposé par les auteurs", methods: proposed, strong: true },
            { key: "comparé à", methods: baselines, strong: false },
          ].filter((group) => group.methods.length > 0).map((group) => (
            <div key={group.key} className="rounded-xl border border-rule bg-sheet-2 p-4">
              <p className="text-xs uppercase tracking-wide text-ink-400">{group.key}</p>
              <div className="mt-2 grid gap-3">
                {group.methods.map((method) => (
                  <div key={method.name} className="min-w-0">
                    <p className="flex flex-wrap items-baseline gap-2">
                      <span className={`text-base text-ink-900 ${group.strong ? "font-semibold" : "font-medium"}`}>
                        {method.name}
                      </span>
                      <span className={`rounded-full px-2.5 py-1 text-xs ${group.strong ? "bg-tide-200/50" : "bg-sheet-3"}`}>
                        {familyLabel(method.family)}
                      </span>
                      {method.is_novel_in_paper ? (
                        <span className="text-xs text-ink-400">nouveauté du papier</span>
                      ) : null}
                    </p>
                    {method.architecture_note ? (
                      <p className="mt-1 break-words text-sm text-ink-600">{method.architecture_note}</p>
                    ) : null}
                    <Evidences items={method.evidence} summary="voir les phrases du papier" />
                  </div>
                ))}
              </div>
            </div>
          ))}
        </Section>
      )}

      {paper.dataset_records.length > 0 && (
        <Section title="Quelles données ?">
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
                {(dataset.period[0] || dataset.period[1]) && (
                  <p>période : {dataset.period.filter(Boolean).join(" → ")}</p>
                )}
              </dl>
              <Evidences items={dataset.evidence} summary="voir les phrases du papier" />
            </article>
          ))}
        </Section>
      )}

      {!paper.excluded_evidence && (
        <Section
          title="Quels résultats ?"
          hint={allResults.length > 0 ? "Chaque chiffre porte la phrase dont il est tiré." : undefined}
        >
          {allResults.length === 0 ? (
            <p className="text-sm text-ink-600">
              Aucun chiffre lisible dans le texte. Ce que ce papier mesure vit dans ses figures,
              et aucune valeur n’a été relevée sur une courbe.
            </p>
          ) : (
            <div className="grid min-w-0 gap-3 [&>*]:min-w-0 md:grid-cols-2">
              {allResults.map((row, index) => <ResultCard key={index} row={row} />)}
            </div>
          )}
        </Section>
      )}

      {allTraining.length > 0 && (
        <Section title="Comment il a été entraîné" hint="Dépliez une ligne pour voir la phrase du papier.">
          {paper.experiments.length > 1
            ? paper.experiments
                .filter((experiment) => experiment.training.length > 0)
                .map((experiment, index) => (
                  <div key={experiment.id} className="min-w-0">
                    <p className="mb-2 text-sm text-ink-400">
                      {`Expérience ${index + 1} — `}
                      {[taskLabel(experiment.task), experiment.method, experiment.datasets.join(", ")]
                        .filter(Boolean).join(" · ")}
                    </p>
                    <Training values={experiment.training} />
                  </div>
                ))
            : <Training values={allTraining} />}
          {(() => {
            const settings = unique(
              paper.not_reported
                .filter((item) => item.field.includes(".training."))
                .map((item) => fieldLabel(item.field.split(".").pop() ?? "")),
            );
            return settings.length > 0 ? (
              <p className="text-sm text-ink-400">Non indiqué par les auteurs : {settings.join(", ")}.</p>
            ) : null;
          })()}
        </Section>
      )}

      {paper.limitations.length > 0 && (
        <Section title="Ce que les auteurs reconnaissent eux-mêmes" hint="Ils l’écrivent ; rien n’est déduit.">
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

      {paper.conflicts.length > 0 && (
        <Section title="Valeurs contradictoires" hint="Le papier donne deux valeurs ; les deux sont conservées.">
          {paper.conflicts.map((conflict, index) => (
            <article key={index} className="rounded-xl border border-rule bg-sheet-2 p-4">
              <p className="break-words text-sm text-ink-900">
                {conflict.values.map((value) => String(value)).join("  ou  ")} → retenu :{" "}
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

      {!paper.excluded_evidence && (
        <Section
          title="Tout, en un tableau"
          hint="Le même contenu sans rien à déplier : ce que le papier fait à gauche, sa phrase à droite."
        >
          <EverythingTable paper={paper} />
        </Section>
      )}

      <p className="mt-10 rounded-xl border border-rule bg-sheet-1 p-4 text-sm text-ink-600">
        {paper.claim_count} informations, {allTraining.length} réglages d’entraînement donnés par les auteurs,{" "}
        {paper.audit?.accepted ?? 0} confirmées à la main.{" "}
        <Link href={`/revue?slug=${paper.slug}`} className="text-tide-500 underline">
          Vérifier ce papier
        </Link>
      </p>
    </div>
  );
}
