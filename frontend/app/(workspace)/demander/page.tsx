import Link from "next/link";
import { ApiError } from "@/app/lib/api";
import {
  askCorpus, familyLabel, fieldLabel, taskLabel, THEME_LABEL, type AskAnswer,
} from "@/app/lib/corpusV2";
import { Quote } from "../corpus/components/Quote";

const EXAMPLES = [
  "quel taux d’apprentissage pour la bathymétrie ?",
  "qui utilise ERA5 ?",
  "quelles limites de généralisation ?",
  "quel matériel pour les transformeurs ?",
  "quels résultats RMSE en reconstruction ?",
];

function one(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] : value;
}

function show(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function Understood({ answer }: { answer: AskAnswer }) {
  const chips: string[] = [
    ...answer.understood.tasks.map(taskLabel),
    ...answer.understood.families.map(familyLabel),
    ...answer.understood.dataset_groups,
    ...answer.understood.variables,
    ...answer.understood.methods,
    ...answer.understood.fields.map(fieldLabel),
    ...answer.understood.themes.map((theme) => THEME_LABEL[theme] ?? theme),
  ];
  if (chips.length === 0) return null;
  return (
    <p className="mt-4 flex flex-wrap items-center gap-2 text-sm">
      <span className="text-ink-400">Compris&nbsp;:</span>
      {chips.map((chip) => (
        <span key={chip} className="rounded-full bg-tide-200/50 px-2.5 py-1 text-xs">{chip}</span>
      ))}
    </p>
  );
}

export default async function DemanderPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const question = one(params.q)?.trim();

  let answer: AskAnswer | null = null;
  let failure: string | null = null;
  if (question) {
    try {
      answer = await askCorpus(question);
    } catch (error) {
      failure = error instanceof ApiError ? error.message : "erreur inconnue";
    }
  }

  return (
    <div className="mx-auto max-w-5xl px-5 py-10">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-tide-500">Interroger le corpus</p>
      <h1 className="mt-2 font-display text-4xl font-medium text-ink-900">Une question, des citations</h1>
      <p className="mt-3 max-w-3xl text-ink-600">
        Ta question est transformée en filtres sur les informations enregistrées : rien n’est
        rédigé, chaque ligne de la réponse est une valeur lue dans un papier, avec sa phrase et
        sa page. Si un mot n’est pas compris, c’est dit plutôt que deviné.
      </p>

      <form className="mt-7 flex flex-wrap gap-3 rounded-2xl border border-rule bg-sheet-2 p-4">
        <input
          name="q"
          defaultValue={question}
          placeholder="quel taux d’apprentissage pour la bathymétrie ?"
          className="min-w-0 flex-1 rounded-lg border border-rule px-3 py-2 text-sm"
        />
        <button className="rounded-lg bg-ink-900 px-5 py-2 text-sm text-white">Demander</button>
      </form>

      <p className="mt-3 flex flex-wrap gap-2 text-xs">
        {EXAMPLES.map((example) => (
          <Link
            key={example}
            href={`/demander?q=${encodeURIComponent(example)}`}
            className="rounded-full border border-rule px-3 py-1 text-ink-600 transition hover:border-tide-300"
          >
            {example}
          </Link>
        ))}
      </p>

      {failure ? (
        <p className="mt-6 rounded-xl border border-rule bg-sheet-1 p-4 text-sm text-ink-900">
          L’API ne répond pas ({failure}).
        </p>
      ) : null}

      {answer ? (
        <section className="mt-8">
          <Understood answer={answer} />
          {answer.understood_nothing ? null : (
            <p className="mt-3 text-sm text-ink-400">
              {answer.experiments_matched} expérience(s) dans {answer.papers_matched} papier(s).
            </p>
          )}

          {answer.answers.map((block, index) => (
            <article key={index} className="mt-6 min-w-0 rounded-2xl border border-rule bg-sheet-2 p-5">
              {block.kind === "training" && (
                <>
                  <h2 className="font-display text-xl font-medium text-ink-900">
                    {fieldLabel(block.field)} — {block.reported} expérience(s) sur {block.of} le rapportent
                  </h2>
                  <ul className="mt-4 grid min-w-0 gap-2 [&>*]:min-w-0">
                    {block.values.map((value, position) => (
                      <li key={position} className="min-w-0 rounded-lg border border-rule bg-sheet-1 p-3">
                        <p className="font-mono text-ink-900">
                          {show(value.value)}
                          {value.unit ? <span className="ml-1 text-ink-400">{value.unit}</span> : null}
                        </p>
                        <p className="mt-1 text-xs text-ink-400">
                          <Link href={`/corpus/${value.slug}`} className="text-tide-500">{value.slug}</Link>
                          {value.method ? ` · ${value.method}` : ""}
                          {value.task ? ` · ${taskLabel(value.task)}` : ""}
                        </p>
                        <div className="mt-2">
                          <Quote quote={value.quote} page={value.page} />
                        </div>
                        {value.note ? <p className="mt-1 text-xs text-ink-400">Note : {value.note}</p> : null}
                      </li>
                    ))}
                  </ul>
                </>
              )}

              {block.kind === "results" && (
                <>
                  <h2 className="font-display text-xl font-medium text-ink-900">
                    {block.count} résultat(s) mesuré(s)
                  </h2>
                  <ul className="mt-4 grid min-w-0 gap-2 [&>*]:min-w-0">
                    {block.values.map((value, position) => (
                      <li key={position} className="min-w-0 rounded-lg border border-rule bg-sheet-1 p-3">
                        <p className="font-mono text-ink-900">
                          {value.metric} = {show(value.value)}
                          {value.unit ? <span className="ml-1 text-ink-400">{value.unit}</span> : null}
                          {value.baseline_name ? (
                            <span className="ml-2 text-xs text-ink-400">
                              vs {value.baseline_name} {value.baseline_value ?? ""}
                            </span>
                          ) : null}
                        </p>
                        <p className="mt-1 text-xs text-ink-400">
                          <Link href={`/corpus/${value.slug}`} className="text-tide-500">{value.slug}</Link>
                          {value.config ? ` · ${value.config}` : ""}
                          {value.split ? ` · ${value.split}` : ""}
                        </p>
                        <div className="mt-2">
                          <Quote quote={value.quote} page={value.page} />
                        </div>
                      </li>
                    ))}
                  </ul>
                </>
              )}

              {block.kind === "limitations" && (
                <>
                  <h2 className="font-display text-xl font-medium text-ink-900">
                    {block.count} limite(s) énoncée(s) par les auteurs
                  </h2>
                  <ul className="mt-4 grid min-w-0 gap-2 [&>*]:min-w-0">
                    {block.values.map((value, position) => (
                      <li key={position} className="min-w-0 rounded-lg border border-rule bg-sheet-1 p-3">
                        <p className="font-mono text-[11px] uppercase tracking-wide text-ink-400">
                          {THEME_LABEL[value.theme] ?? value.theme}
                        </p>
                        <p className="mt-1 break-words text-sm text-ink-900">« {value.quote} »</p>
                        <p className="mt-1 text-xs text-ink-400">
                          <Link href={`/corpus/${value.slug}`} className="text-tide-500">{value.slug}</Link>
                          {value.page ? ` · page ${value.page}` : ""}
                        </p>
                      </li>
                    ))}
                  </ul>
                </>
              )}

              {block.kind === "experiments" && (
                <>
                  <h2 className="font-display text-xl font-medium text-ink-900">
                    {block.count} expérience(s)
                  </h2>
                  <ul className="mt-4 grid min-w-0 gap-2 [&>*]:min-w-0">
                    {block.values.map((value, position) => (
                      <li key={position} className="min-w-0 rounded-lg border border-rule bg-sheet-1 p-3 text-sm">
                        <Link href={`/corpus/${value.slug}`} className="text-tide-500">{value.title}</Link>
                        <p className="mt-1 text-xs text-ink-400">
                          {[taskLabel(value.task), value.method, value.variable].filter(Boolean).join(" · ")}
                        </p>
                        <p className="mt-1 text-xs text-ink-600">
                          réglages donnés : {value.reported.length > 0
                            ? value.reported.map(fieldLabel).join(", ")
                            : "aucun"}
                        </p>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </article>
          ))}

          {answer.caveats.length > 0 && (
            <div className="mt-6 grid gap-2 rounded-2xl border border-rule bg-sheet-1 p-4 text-sm text-ink-900">
              {answer.caveats.map((caveat) => <p key={caveat}>{caveat}</p>)}
            </div>
          )}
        </section>
      ) : null}
    </div>
  );
}
