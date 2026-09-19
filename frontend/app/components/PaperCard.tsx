import Link from "next/link";
import type { PaperSummary } from "@/app/lib/api";
import { formatAuthors } from "@/app/lib/fields";

export function ArchitectureTag({ children }: { children: string }) {
  return (
    <span
      title={children}
      className="max-w-full truncate rounded-full bg-indigo-50 px-2.5 py-0.5 text-xs font-medium text-indigo-700 ring-1 ring-inset ring-indigo-200"
    >
      {children}
    </span>
  );
}

export function PaperCard({ paper }: { paper: PaperSummary }) {
  return (
    <Link
      href={`/papers/${paper.id}`}
      className="group flex flex-col rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:border-cyan-300 hover:shadow-md"
    >
      <div className="flex items-start justify-between gap-3">
        <h2 className="line-clamp-2 font-semibold leading-snug text-slate-900 group-hover:text-cyan-800">
          {paper.title ?? <span className="font-normal italic text-slate-400">Titre non détecté</span>}
        </h2>
        {paper.year && (
          <span className="shrink-0 rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
            {paper.year}
          </span>
        )}
      </div>

      {paper.authors.length > 0 && (
        <p className="mt-1 line-clamp-1 text-sm text-slate-500">{formatAuthors(paper.authors)}</p>
      )}

      {paper.architecture.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {paper.architecture.slice(0, 3).map((name) => (
            <ArchitectureTag key={name}>{name}</ArchitectureTag>
          ))}
        </div>
      )}

      {paper.headline && (
        <p className="mt-3 line-clamp-3 border-l-2 border-cyan-300 pl-3 text-sm leading-relaxed text-slate-600">
          {paper.headline}
        </p>
      )}

      <div className="mt-auto flex items-center justify-between pt-4 text-xs text-slate-500">
        <span>{paper.extracted_field_count} infos extraites</span>
        <span className="font-medium text-cyan-700 transition group-hover:translate-x-0.5">Voir la fiche →</span>
      </div>
    </Link>
  );
}
