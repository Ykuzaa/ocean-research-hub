import type { Domain, PaperSummary } from "@/app/lib/api";
import { isAnalyzed } from "@/app/lib/api";
import { SearchBox } from "@/app/components/SearchBox";

/**
 * Workspace entry header. Deliberately restrained: the public story lives on
 * the landing page, this one exists to get the researcher into the corpus.
 */
export function WorkspaceHeader({ papers, domains }: { papers: PaperSummary[]; domains: Domain[] }) {
  const analyzed = papers.filter(isAnalyzed).length;

  return (
    <section className="border-b border-slate-200 bg-white">
      <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6 sm:py-12">
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900 sm:text-3xl">
          Corpus Océan × IA
        </h1>
        <p className="mt-2 max-w-2xl text-slate-600">
          Données, architecture, entraînement et résultats, lus dans le PDF et rattachés à leur page
          source.
        </p>
        <div className="mt-6 max-w-2xl">
          <SearchBox papers={papers} domains={domains} />
        </div>
        <p className="mt-4 text-sm text-slate-500">
          {papers.length} papiers · {domains.length} domaines
          {analyzed > 0 && ` · ${analyzed} analysés en détail`}
        </p>
      </div>
    </section>
  );
}
