import Link from "next/link";
import { ApiError } from "@/app/lib/api";
import {
  entityName, familyLabel, fieldLabel, getAnalysis, taskLabel, THEME_LABEL,
  type EntityKind, type EntitySummary, type Reporting,
} from "@/app/lib/corpusV2";

function Rate({ reporting, field }: { reporting: Reporting; field: string }) {
  const { reported, of } = reporting[field] ?? { reported: 0, of: 0 };
  const pct = of ? Math.round((reported / of) * 100) : 0;
  return (
    <span className="font-mono text-xs text-ink-600" title={`${reported} expériences sur ${of}`}>
      {pct}&nbsp;%
    </span>
  );
}

function EntityTable({ kind, rows, title, hint }: {
  kind: EntityKind; rows: EntitySummary[]; title: string; hint: string;
}) {
  return (
    <section className="mt-10">
      <h2 className="font-display text-2xl font-medium text-ink-900">{title}</h2>
      <p className="mt-1 max-w-3xl text-sm text-ink-400">{hint}</p>
      <div className="mt-4 overflow-x-auto rounded-2xl border border-rule bg-sheet-2">
        <table className="w-full min-w-[46rem] border-collapse text-sm">
          <thead className="bg-sheet-1 text-left text-xs uppercase tracking-wide text-ink-400">
            <tr>
              <th className="px-4 py-2 font-medium">Nom</th>
              <th className="px-3 py-2 font-medium">Papiers</th>
              <th className="px-3 py-2 font-medium">Expériences</th>
              <th className="px-3 py-2 font-medium">Résultats</th>
              <th className="px-3 py-2 font-medium">Fonction de coût</th>
              <th className="px-3 py-2 font-medium">Taux d’apprentissage</th>
              <th className="px-3 py-2 font-medium">Taille de lot</th>
              <th className="px-3 py-2 font-medium">Matériel</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-rule">
            {rows.map((row) => (
              <tr key={row.name} className="align-top">
                <td className="px-4 py-2">
                  <Link
                    href={`/analyse/${kind}/${encodeURIComponent(row.name)}`}
                    className="text-tide-500 underline underline-offset-2"
                  >
                    {entityName(kind, row.name)}
                  </Link>
                </td>
                <td className="px-3 py-2 font-mono">{row.papers}</td>
                <td className="px-3 py-2 font-mono">{row.experiments}</td>
                <td className="px-3 py-2 font-mono">{row.results}</td>
                <td className="px-3 py-2"><Rate reporting={row.reporting} field="loss" /></td>
                <td className="px-3 py-2"><Rate reporting={row.reporting} field="learning_rate" /></td>
                <td className="px-3 py-2"><Rate reporting={row.reporting} field="batch_size" /></td>
                <td className="px-3 py-2"><Rate reporting={row.reporting} field="hardware" /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default async function AnalysePage() {
  let data;
  try {
    data = await getAnalysis();
  } catch (error) {
    const message = error instanceof ApiError ? error.message : "erreur inconnue";
    return (
      <div className="mx-auto max-w-3xl px-5 py-16">
        <h1 className="font-display text-3xl font-medium text-ink-900">Analyse indisponible</h1>
        <p className="mt-3 text-ink-600">L’API ne répond pas ({message}).</p>
      </div>
    );
  }

  const shared = data.entities.dataset_group.filter((row) => row.papers > 1);
  const themes = Object.entries(data.problems).sort((a, b) => b[1].papers - a[1].papers);

  return (
    <div className="mx-auto max-w-7xl px-5 py-10">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-tide-500">Lecture transversale</p>
      <h1 className="mt-2 font-display text-4xl font-medium text-ink-900">
        Entrer par une architecture, un objectif, une source
      </h1>
      <p className="mt-3 max-w-3xl text-ink-600">
        Chaque chiffre de cette page est un décompte d’informations sourcées, et chaque pourcentage
        est une part des expériences concernées. Ce sont des pratiques et une couverture, jamais un
        classement : aucune combinaison (jeu de données, métrique, unité) n’est partagée par deux
        papiers de ce corpus, donc « quelle architecture est la meilleure » n’est pas calculable ici.
      </p>

      <EntityTable
        kind="family"
        rows={data.entities.family}
        title="Par architecture"
        hint="Les pourcentages disent quelle part des expériences de cette architecture rapporte le réglage. C’est une mesure du reporting du domaine, pas de la qualité des modèles."
      />
      <EntityTable
        kind="task"
        rows={data.entities.task}
        title="Par objectif"
        hint="Le même corpus vu par ce que les modèles cherchent à faire."
      />
      <EntityTable
        kind="dataset_group"
        rows={shared}
        title="Par source de données"
        hint={`Regroupement par source : les papiers nomment la même donnée de façons différentes. ${shared.length} sources apparaissent dans plus d’un papier, sur ${data.entities.dataset_group.length} noms distincts lus dans les papiers — c’est pourquoi une page par nom exact serait presque toujours une page sur un seul papier.`}
      />

      <section className="mt-12">
        <h2 className="font-display text-2xl font-medium text-ink-900">Ce que personne n’a publié ici</h2>
        <p className="mt-1 max-w-3xl text-sm text-ink-400">{data.coverage.caveat}</p>
        <div className="mt-4 overflow-x-auto rounded-2xl border border-rule bg-sheet-2">
          <table className="w-full min-w-[48rem] border-collapse text-sm">
            <thead className="bg-sheet-1 text-left text-xs uppercase tracking-wide text-ink-400">
              <tr>
                <th className="px-4 py-2 font-medium">Objectif \\ architecture</th>
                {data.coverage.families.map((family) => (
                  <th key={family} className="px-2 py-2 font-medium">{familyLabel(family)}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-rule">
              {data.coverage.matrix.map((row) => (
                <tr key={row.task}>
                  <th className="px-4 py-2 text-left font-normal text-ink-600">{taskLabel(row.task)}</th>
                  {row.cells.map((cell) => (
                    <td
                      key={cell.family}
                      className={`px-2 py-2 text-center font-mono ${
                        cell.papers ? "bg-tide-200/40 font-semibold text-ink-900" : "text-ink-400"
                      }`}
                    >
                      {cell.papers || "·"}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-sm text-ink-600">
          {data.coverage.empty_cells.length} cases vides sur{" "}
          {data.coverage.tasks.length * data.coverage.families.length}.
        </p>
      </section>

      <section className="mt-12">
        <h2 className="font-display text-2xl font-medium text-ink-900">Les limites que les auteurs énoncent</h2>
        <p className="mt-1 max-w-3xl text-sm text-ink-400">
          Regroupées par thème, avec la phrase de chaque papier. Rien n’est déduit : une promesse de
          travail futur, une mise à disposition de code ou une mesure de performance ne sont pas des
          limites et ont été retirées du corpus.
        </p>
        <div className="mt-4 grid min-w-0 gap-3 [&>*]:min-w-0 md:grid-cols-2">
          {themes.map(([theme, group]) => (
            <details key={theme} className="min-w-0 rounded-2xl border border-rule bg-sheet-2 p-4">
              <summary className="flex cursor-pointer items-baseline justify-between gap-3">
                <span className="font-medium text-ink-900">{THEME_LABEL[theme] ?? theme}</span>
                <span className="font-mono text-sm text-ink-400">{group.papers} papiers</span>
              </summary>
              <ul className="mt-3 grid min-w-0 gap-2 [&>*]:min-w-0">
                {group.items.map((item, index) => (
                  <li key={index} className="min-w-0 rounded-lg border border-rule bg-sheet-1 p-3 text-sm">
                    <p className="break-words text-ink-900">« {item.quote} »</p>
                    <p className="mt-1 font-mono text-[11px] text-ink-400">
                      <Link href={`/corpus/${item.slug}`} className="text-tide-500">{item.slug}</Link>
                      {item.page ? ` · page ${item.page}` : ""}
                    </p>
                  </li>
                ))}
              </ul>
            </details>
          ))}
        </div>
      </section>
    </div>
  );
}
