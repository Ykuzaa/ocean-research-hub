import Link from "next/link";
import { listPapers, type PaperSummary } from "@/app/lib/api";
import { PaperGrid } from "@/app/components/PaperGrid";
import { BackendDown } from "@/app/components/BackendDown";

function StatTile({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white px-5 py-4 shadow-sm">
      <p className="text-sm text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums text-slate-900">{value.toLocaleString("fr-FR")}</p>
    </div>
  );
}

function stats(papers: PaperSummary[], total: number) {
  const models = new Set(papers.flatMap((paper) => paper.architecture.map((name) => name.toLowerCase())));
  return {
    total,
    fields: papers.reduce((sum, paper) => sum + paper.extracted_field_count, 0),
    models: models.size,
  };
}

export default async function HomePage() {
  let data: { papers: PaperSummary[]; total: number };
  try {
    data = await listPapers();
  } catch {
    return <BackendDown />;
  }
  const summary = stats(data.papers, data.total);

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Papiers</h1>
        <p className="mt-1 text-sm text-slate-500">
          Les détails techniques de chaque papier, lus directement dans le PDF. Clique sur une valeur pour voir
          la phrase exacte d&apos;où elle vient.
        </p>
      </header>

      <div className="grid gap-4 sm:grid-cols-3">
        <StatTile label="Papiers" value={summary.total} />
        <StatTile label="Infos techniques extraites" value={summary.fields} />
        <StatTile label="Familles de modèles" value={summary.models} />
      </div>

      {data.papers.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-300 bg-white px-6 py-14 text-center">
          <p className="font-medium text-slate-900">Aucun papier pour l&apos;instant</p>
          <p className="mt-1 text-sm text-slate-500">Colle un lien arXiv ou un PDF pour lancer la première extraction.</p>
          <Link
            href="/add"
            className="mt-5 inline-flex rounded-lg bg-cyan-700 px-4 py-2 text-sm font-medium text-white hover:bg-cyan-800"
          >
            Ajouter un papier
          </Link>
        </div>
      ) : (
        <PaperGrid papers={data.papers} />
      )}
    </div>
  );
}
