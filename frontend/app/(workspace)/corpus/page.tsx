import Link from "next/link";
import { ApiError } from "@/app/lib/api";
import { familyLabel, getCorpusSummary, listCorpusV2Papers, taskLabel } from "@/app/lib/corpusV2";

function one(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] : value;
}

function Counter({ value, label }: { value: React.ReactNode; label: string }) {
  return (
    <div className="rounded-xl border border-rule bg-sheet-2 px-4 py-3">
      <p className="font-display text-2xl font-medium text-ink-900">{value}</p>
      <p className="mt-1 text-xs uppercase tracking-wide text-ink-400">{label}</p>
    </div>
  );
}

function Chip({ href, active, children }: { href: string; active: boolean; children: React.ReactNode }) {
  return (
    <Link
      href={href}
      aria-current={active ? "true" : undefined}
      className={`rounded-full border px-3 py-1 text-xs transition ${
        active
          ? "border-tide-500 bg-tide-500 text-white"
          : "border-rule bg-sheet-2 text-ink-600 hover:border-tide-300"
      }`}
    >
      {children}
    </Link>
  );
}

export default async function CorpusPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const q = one(params.q);
  const task = one(params.task);
  const family = one(params.family);

  let data;
  let summary;
  try {
    [data, summary] = await Promise.all([listCorpusV2Papers({ q, task, family }), getCorpusSummary()]);
  } catch (error) {
    const message = error instanceof ApiError ? error.message : "erreur inconnue";
    return (
      <div className="mx-auto max-w-3xl px-5 py-16">
        <h1 className="font-display text-3xl font-medium text-ink-900">Corpus indisponible</h1>
        <p className="mt-3 text-ink-600">
          L’API ne répond pas ({message}). Lance le serveur&nbsp;:{" "}
          <code className="font-mono text-sm">uv run uvicorn ocean_research_hub.api:app</code>
        </p>
      </div>
    );
  }

  const keep = (next: Record<string, string | undefined>) => {
    const query = new URLSearchParams();
    const merged = { q, task, family, ...next };
    for (const [key, value] of Object.entries(merged)) if (value) query.set(key, value);
    const encoded = query.toString();
    return encoded ? `/corpus?${encoded}` : "/corpus";
  };

  return (
    <div className="mx-auto max-w-7xl px-5 py-10">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-tide-500">
        Corpus sourcé · {summary.quotes.toLocaleString("fr-FR")} citations relocalisées
      </p>
      <h1 className="mt-2 font-display text-4xl font-medium text-ink-900">Les papiers, détail par détail</h1>
      <p className="mt-3 max-w-3xl text-ink-600">{summary.notice}</p>

      <div className="mt-7 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <Counter value={summary.papers} label="papiers lus" />
        <Counter value={summary.experiments} label="expériences" />
        <Counter value={summary.results} label="résultats mesurés" />
        <Counter
          value={`${summary.audit.accepted}/${summary.audit.claims.toLocaleString("fr-FR")}`}
          label="informations confirmées à la main"
        />
        <Counter
          value={summary.access ? `${summary.access.reachable}/${summary.access.indexed}` : "—"}
          label="papiers accessibles"
        />
      </div>

      <form className="mt-7 flex flex-wrap gap-3 rounded-2xl border border-rule bg-sheet-2 p-4">
        <input
          name="q"
          defaultValue={q}
          placeholder="Titre, méthode, jeu de données, variable…"
          className="min-w-0 flex-1 rounded-lg border border-rule px-3 py-2 text-sm"
        />
        {task ? <input type="hidden" name="task" value={task} /> : null}
        {family ? <input type="hidden" name="family" value={family} /> : null}
        <button className="rounded-lg bg-ink-900 px-5 py-2 text-sm text-white">Chercher</button>
        {(q || task || family) && (
          <Link href="/corpus" className="rounded-lg border border-rule px-4 py-2 text-sm text-ink-600">
            Tout afficher
          </Link>
        )}
      </form>

      <div className="mt-5 grid gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs uppercase tracking-wide text-ink-400">Objectif</span>
          {Object.keys(summary.tasks).sort().map((key) => (
            <Chip key={key} href={keep({ task: task === key ? undefined : key })} active={task === key}>
              {taskLabel(key)} · {summary.tasks[key]}
            </Chip>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs uppercase tracking-wide text-ink-400">Architecture</span>
          {Object.keys(summary.families).sort().map((key) => (
            <Chip key={key} href={keep({ family: family === key ? undefined : key })} active={family === key}>
              {familyLabel(key)} · {summary.families[key]}
            </Chip>
          ))}
        </div>
      </div>

      <p className="mt-6 text-sm text-ink-400">
        {data.papers.length} papier(s) sur {summary.papers + summary.excluded} enregistrement(s)
      </p>

      <div className="mt-3 divide-y divide-rule overflow-hidden rounded-2xl border border-rule bg-sheet-2">
        {data.papers.map((paper) => (
          <Link
            key={paper.slug}
            href={`/corpus/${paper.slug}`}
            className="grid gap-3 p-5 transition hover:bg-sheet-1 md:grid-cols-[1fr_16rem]"
          >
            <div className="min-w-0">
              <h2 className="text-lg font-semibold text-ink-900">{paper.title}</h2>
              <p className="mt-1 text-sm text-ink-400">
                {[paper.year, paper.venue, paper.doi].filter(Boolean).join(" · ")}
              </p>
              {paper.excluded ? (
                <p className="mt-2 text-sm text-ink-600">Écarté : {paper.excluded}</p>
              ) : (
                <p className="mt-2 flex flex-wrap gap-2 text-xs text-ink-600">
                  {paper.tasks.map((key) => (
                    <span key={key} className="rounded-full bg-sheet-3 px-2.5 py-1">{taskLabel(key)}</span>
                  ))}
                  {paper.families.map((key) => (
                    <span key={key} className="rounded-full bg-tide-200/50 px-2.5 py-1">
                      {familyLabel(key)}
                    </span>
                  ))}
                </p>
              )}
            </div>
            <dl className="grid grid-cols-3 gap-2 text-center text-xs md:text-right">
              <div><dt className="text-ink-400">expériences</dt><dd className="font-mono text-base text-ink-900">{paper.experiment_count}</dd></div>
              <div><dt className="text-ink-400">résultats</dt><dd className="font-mono text-base text-ink-900">{paper.result_count}</dd></div>
              <div><dt className="text-ink-400">confirmés</dt><dd className="font-mono text-base text-ink-900">{paper.audit?.accepted ?? 0}/{paper.claim_count}</dd></div>
            </dl>
          </Link>
        ))}
        {data.papers.length === 0 && (
          <p className="p-6 text-sm text-ink-600">Aucun papier ne correspond à cette recherche.</p>
        )}
      </div>
    </div>
  );
}
