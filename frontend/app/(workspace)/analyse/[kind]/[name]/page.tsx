import Link from "next/link";
import { notFound } from "next/navigation";
import { ApiError } from "@/app/lib/api";
import {
  ENTITY_LABEL, entityName, familyLabel, fieldLabel, getEntity, taskLabel, THEME_LABEL,
  type EntityKind,
} from "@/app/lib/corpusV2";

const KINDS: EntityKind[] = ["family", "task", "dataset", "dataset_group", "variable", "method"];
const TRAINING = ["loss", "optimizer", "learning_rate", "batch_size", "epochs", "hardware"];

function Tally({ title, rows, href }: {
  title: string; rows: Record<string, number>; href?: (key: string) => string;
}) {
  const entries = Object.entries(rows);
  if (entries.length === 0) return null;
  return (
    <div className="min-w-0">
      <h3 className="text-xs uppercase tracking-wide text-ink-400">{title}</h3>
      <ul className="mt-2 grid min-w-0 gap-1 text-sm">
        {entries.map(([key, count]) => (
          <li key={key} className="flex min-w-0 justify-between gap-3 border-b border-rule pb-1">
            <span className="min-w-0 break-words text-ink-600">
              {href ? <Link href={href(key)} className="text-tide-500">{key}</Link> : key}
            </span>
            <span className="font-mono text-ink-400">{count}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default async function EntityPage({ params }: {
  params: Promise<{ kind: string; name: string }>;
}) {
  const { kind, name } = await params;
  if (!KINDS.includes(kind as EntityKind)) notFound();
  const decoded = decodeURIComponent(name);

  let entity;
  try {
    entity = await getEntity(kind as EntityKind, decoded);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    const message = error instanceof ApiError ? error.message : "erreur inconnue";
    return (
      <div className="mx-auto max-w-3xl px-5 py-16">
        <h1 className="font-display text-3xl font-medium text-ink-900">Page indisponible</h1>
        <p className="mt-3 text-ink-600">L’API ne répond pas ({message}).</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl px-5 py-10">
      <Link href="/analyse" className="text-sm text-tide-500">← Lecture transversale</Link>
      <p className="mt-3 text-xs uppercase tracking-wide text-ink-400">{ENTITY_LABEL[kind as EntityKind]}</p>
      <h1 className="mt-1 font-display text-3xl font-medium text-ink-900">
        {entityName(kind as EntityKind, entity.name)}
      </h1>

      <div className="mt-6 grid gap-3 rounded-2xl border border-rule bg-sheet-2 p-4 text-sm sm:grid-cols-4">
        <p><span className="block text-xs uppercase tracking-wide text-ink-400">papiers</span>{entity.papers}</p>
        <p><span className="block text-xs uppercase tracking-wide text-ink-400">expériences</span>{entity.experiments}</p>
        <p><span className="block text-xs uppercase tracking-wide text-ink-400">résultats mesurés</span>{entity.results}</p>
        <p><span className="block text-xs uppercase tracking-wide text-ink-400">mesures distinctes</span>{Object.keys(entity.metrics).length}</p>
      </div>
      <p className="mt-3 max-w-3xl text-sm text-ink-600">{entity.comparability}</p>

      <section className="mt-10">
        <h2 className="font-display text-2xl font-medium text-ink-900">Ce qui est rapporté, et ce qui ne l’est pas</h2>
        <div className="mt-4 grid gap-1">
          {TRAINING.map((field) => {
            const { reported, of } = entity.reporting[field] ?? { reported: 0, of: 0 };
            const pct = of ? Math.round((reported / of) * 100) : 0;
            return (
              <div key={field} className="grid grid-cols-[9rem_minmax(0,1fr)_5rem] items-center gap-3 border-b border-rule py-2 text-sm">
                <span className="text-ink-600">{fieldLabel(field)}</span>
                <span className="h-3 min-w-0 bg-sheet-3">
                  <span className="block h-3 bg-tide-400" style={{ width: `${pct}%` }} />
                </span>
                <span className="text-right font-mono text-ink-600">{reported}/{of}</span>
              </div>
            );
          })}
        </div>
      </section>

      <section className="mt-10 grid min-w-0 gap-6 [&>*]:min-w-0 md:grid-cols-2 lg:grid-cols-3">
        <Tally title="Objectifs" rows={Object.fromEntries(Object.entries(entity.tasks).map(([k, v]) => [taskLabel(k), v]))} />
        <Tally title="Architectures" rows={Object.fromEntries(Object.entries(entity.families).map(([k, v]) => [familyLabel(k), v]))} />
        <Tally title="Jeux de données" rows={entity.datasets} />
        <Tally title="Variables prédites" rows={entity.variables} />
        <Tally title="Méthodes nommées" rows={entity.methods} />
        <Tally title="Mesures employées" rows={entity.metrics} />
      </section>

      <section className="mt-10">
        <h2 className="font-display text-2xl font-medium text-ink-900">Les papiers</h2>
        <ul className="mt-4 divide-y divide-rule overflow-hidden rounded-2xl border border-rule bg-sheet-2">
          {entity.paper_list.map((paper) => (
            <li key={paper.slug}>
              <Link href={`/corpus/${paper.slug}`} className="block px-5 py-3 transition hover:bg-sheet-1">
                <span className="text-ink-900">{paper.title}</span>
                {paper.year ? <span className="ml-2 font-mono text-xs text-ink-400">{paper.year}</span> : null}
              </Link>
            </li>
          ))}
        </ul>
      </section>

      {entity.problems.length > 0 && (
        <section className="mt-10">
          <h2 className="font-display text-2xl font-medium text-ink-900">Les limites annoncées dans ces papiers</h2>
          <ul className="mt-4 grid min-w-0 gap-2 [&>*]:min-w-0">
            {entity.problems.map((problem, index) => (
              <li key={index} className="min-w-0 rounded-lg border border-rule bg-sheet-2 p-3 text-sm">
                <span className="font-mono text-[11px] uppercase tracking-wide text-ink-400">
                  {THEME_LABEL[problem.theme] ?? problem.theme}
                </span>
                <p className="mt-1 break-words text-ink-900">« {problem.quote} »</p>
                <p className="mt-1 break-words font-mono text-[11px] text-ink-400">
                  <Link href={`/corpus/${problem.slug}`} className="text-tide-500">{problem.slug}</Link>
                  {problem.page ? ` · page ${problem.page}` : ""}
                </p>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
