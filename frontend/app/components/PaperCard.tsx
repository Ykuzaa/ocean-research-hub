import Link from "next/link";
import type { PaperSummary } from "@/app/lib/api";
import { formatAuthors } from "@/app/lib/fields";

export function ModelTag({ children }: { children: string }) {
  return (
    <span
      title={children}
      className="max-w-full truncate rounded-full bg-cyan-50 px-2.5 py-0.5 text-xs font-medium text-cyan-800 ring-1 ring-inset ring-cyan-100"
    >
      {children}
    </span>
  );
}

export function PaperCard({ paper }: { paper: PaperSummary }) {
  return (
    <Link
      href={`/papers/${paper.id}`}
      className="group flex h-full flex-col rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition duration-300 hover:-translate-y-1 hover:border-cyan-200 hover:shadow-xl hover:shadow-cyan-900/5"
    >
      <div className="flex items-start justify-between gap-3">
        <h3 className="line-clamp-3 font-semibold leading-snug text-slate-900 transition-colors group-hover:text-cyan-800">
          {paper.title ?? <span className="font-normal italic text-slate-400">Titre non détecté</span>}
        </h3>
        {paper.year && (
          <span className="shrink-0 rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium tabular-nums text-slate-600">
            {paper.year}
          </span>
        )}
      </div>

      {paper.authors.length > 0 && (
        <p className="mt-1.5 line-clamp-1 text-sm text-slate-500">{formatAuthors(paper.authors, 2)}</p>
      )}

      {paper.architecture.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {paper.architecture.slice(0, 3).map((name) => (
            <ModelTag key={name}>{name}</ModelTag>
          ))}
        </div>
      )}

      {paper.headline && (
        <p className="mt-3 line-clamp-3 border-l-2 border-cyan-300 pl-3 text-sm leading-relaxed text-slate-600">
          {paper.headline}
        </p>
      )}

      <span className="mt-auto pt-4 text-xs font-medium text-cyan-700 opacity-0 transition duration-300 group-hover:opacity-100">
        Voir la fiche →
      </span>
    </Link>
  );
}
