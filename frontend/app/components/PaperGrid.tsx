"use client";

import { useMemo, useState } from "react";
import type { PaperSummary } from "@/app/lib/api";
import { PaperCard } from "@/app/components/PaperCard";

function searchableText(paper: PaperSummary): string {
  return [paper.title, paper.venue, paper.headline, paper.year, ...paper.authors, ...paper.architecture]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

export function PaperGrid({ papers }: { papers: PaperSummary[] }) {
  const [query, setQuery] = useState("");
  const index = useMemo(() => papers.map((paper) => [paper, searchableText(paper)] as const), [papers]);
  const terms = query.toLowerCase().split(/\s+/).filter(Boolean);
  const visible = index.filter(([, text]) => terms.every((term) => text.includes(term))).map(([paper]) => paper);

  return (
    <section>
      <div className="relative mb-5">
        <svg
          viewBox="0 0 20 20"
          aria-hidden
          className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 fill-slate-400"
        >
          <path d="M8.5 3a5.5 5.5 0 0 1 4.38 8.83l3.65 3.64a.75.75 0 1 1-1.06 1.06l-3.64-3.65A5.5 5.5 0 1 1 8.5 3Zm0 1.5a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z" />
        </svg>
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Rechercher par titre, auteur, modèle, résultat…"
          className="w-full rounded-xl border border-slate-200 bg-white py-2.5 pl-10 pr-4 text-sm text-slate-800 shadow-sm placeholder:text-slate-400 focus:border-cyan-400 focus:outline-none focus:ring-2 focus:ring-cyan-100"
        />
      </div>

      {visible.length === 0 ? (
        <p className="rounded-xl border border-dashed border-slate-300 bg-white px-4 py-10 text-center text-sm text-slate-500">
          Aucun papier ne correspond à « {query} ».
        </p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {visible.map((paper) => (
            <PaperCard key={paper.id} paper={paper} />
          ))}
        </div>
      )}
    </section>
  );
}
