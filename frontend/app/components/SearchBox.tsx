"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { ArrowRight, Search } from "lucide-react";
import type { Domain, PaperSummary } from "@/app/lib/api";
import { DomainIcon } from "@/app/lib/domains";

type Result =
  | { kind: "domain"; href: string; domain: Domain }
  | { kind: "paper"; href: string; paper: PaperSummary };

function haystack(paper: PaperSummary): string {
  return [paper.title, paper.venue, paper.year, ...paper.authors, ...paper.architecture].join(" ").toLowerCase();
}

export function SearchBox({ papers, domains }: { papers: PaperSummary[]; domains: Domain[] }) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [focused, setFocused] = useState(false);
  const indexed = useMemo(() => papers.map((paper) => ({ paper, text: haystack(paper) })), [papers]);

  const terms = query.toLowerCase().split(/\s+/).filter(Boolean);
  const results: Result[] = terms.length
    ? [
        ...domains
          .filter((domain) => terms.every((term) => domain.name.toLowerCase().includes(term)))
          .slice(0, 3)
          .map((domain) => ({ kind: "domain" as const, href: `/domains/${domain.id}`, domain })),
        ...indexed
          .filter(({ text }) => terms.every((term) => text.includes(term)))
          .slice(0, 7)
          .map(({ paper }) => ({ kind: "paper" as const, href: `/papers/${paper.id}`, paper })),
      ]
    : [];
  const open = focused && terms.length > 0;

  return (
    <div className="relative mx-auto w-full max-w-2xl">
      <form
        className="relative"
        onSubmit={(event) => {
          event.preventDefault();
          if (results[0]) router.push(results[0].href);
        }}
      >
        <Search aria-hidden className="pointer-events-none absolute left-4 top-1/2 z-10 h-4.5 w-4.5 -translate-y-1/2 text-slate-400" />
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={() => setTimeout(() => setFocused(false), 150)}
          placeholder="Un modèle, un auteur, un sujet : GLONET, 4DVarNet, SST, Zanna…"
          aria-label="Rechercher un papier ou un domaine"
          className="w-full rounded-lg border border-slate-300 bg-white py-3 pl-12 pr-5 text-[0.9375rem] text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-100"
        />
      </form>

      {open && (
        <div className="absolute inset-x-0 top-full z-20 mt-2 overflow-hidden rounded-lg border border-slate-200 bg-white text-left shadow-xl">
          {results.length === 0 ? (
            <p className="px-5 py-4 text-sm text-slate-500">Rien trouvé pour « {query} ».</p>
          ) : (
            <ul className="max-h-96 overflow-y-auto py-2">
              {results.map((result) => (
                <li key={result.href}>
                  <Link href={result.href} className="group flex items-center gap-3 px-5 py-2.5 hover:bg-slate-50">
                    {result.kind === "domain" ? (
                      <>
                        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-cyan-50 text-cyan-700">
                          <DomainIcon id={result.domain.id} className="h-4 w-4" />
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block text-sm font-medium text-slate-900">{result.domain.name}</span>
                          <span className="block text-xs text-slate-500">Domaine · {result.domain.paper_count} papiers</span>
                        </span>
                      </>
                    ) : (
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-medium text-slate-900">
                          {result.paper.title ?? "Titre non détecté"}
                        </span>
                        <span className="block truncate text-xs text-slate-500">
                          {[result.paper.authors[0] && `${result.paper.authors[0]}${result.paper.authors.length > 1 ? " et al." : ""}`, result.paper.year]
                            .filter(Boolean)
                            .join(" · ")}
                        </span>
                      </span>
                    )}
                    <ArrowRight aria-hidden className="h-4 w-4 shrink-0 text-slate-300 transition group-hover:translate-x-0.5 group-hover:text-cyan-600" />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
