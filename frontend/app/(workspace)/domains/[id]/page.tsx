import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowRight } from "lucide-react";
import { isAnalyzed, listDomains, listPapers, type Domain, type PaperSummary } from "@/app/lib/api";
import { DomainIcon } from "@/app/lib/domains";
import { formatAuthors } from "@/app/lib/fields";
import { PaperCard } from "@/app/components/PaperCard";
import { Reveal } from "@/app/components/Reveal";
import { BackendDown } from "@/app/components/BackendDown";

function DomainSidebar({ domains, active }: { domains: Domain[]; active: string }) {
  return (
    <nav aria-label="Domaines" className="no-scrollbar lg:sticky lg:top-24 lg:max-h-[calc(100vh-7rem)] lg:overflow-y-auto">
      <p className="mb-3 px-3 text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Domaines</p>
      <ul className="flex gap-1 overflow-x-auto pb-2 lg:flex-col lg:overflow-visible lg:pb-0">
        {domains.map((domain) => {
          const current = domain.id === active;
          return (
            <li key={domain.id} className="shrink-0">
              <Link
                href={`/domains/${domain.id}`}
                aria-current={current ? "page" : undefined}
                className={`flex items-center gap-3 rounded-xl px-3 py-2 text-sm transition ${
                  current ? "bg-slate-900 text-white shadow-sm" : "text-slate-600 hover:bg-white hover:text-slate-900"
                }`}
              >
                <DomainIcon id={domain.id} className={`h-4 w-4 shrink-0 ${current ? "text-cyan-300" : "text-slate-400"}`} />
                <span className="flex-1 whitespace-nowrap lg:truncate lg:whitespace-normal">{domain.name}</span>
                <span className={`tabular-nums text-xs ${current ? "text-slate-300" : "text-slate-400"}`}>
                  {domain.paper_count}
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

function OtherPaperRow({ paper }: { paper: PaperSummary }) {
  const meta = [paper.authors.length ? formatAuthors(paper.authors, 2) : null, paper.venue, paper.year]
    .filter(Boolean)
    .join(" · ");
  return (
    <li>
      <Link href={`/papers/${paper.id}`} className="group flex items-center gap-4 px-5 py-4 transition hover:bg-slate-50">
        <span className="min-w-0 flex-1">
          <span className="block font-medium leading-snug text-slate-800 group-hover:text-cyan-800">
            {paper.title ?? "Titre non détecté"}
          </span>
          {meta && <span className="mt-0.5 block truncate text-sm text-slate-500">{meta}</span>}
        </span>
        <ArrowRight aria-hidden className="h-4 w-4 shrink-0 text-slate-300 transition group-hover:translate-x-0.5 group-hover:text-cyan-600" />
      </Link>
    </li>
  );
}

export default async function DomainPage(props: PageProps<"/domains/[id]">) {
  const { id } = await props.params;
  let domains: Domain[];
  try {
    domains = await listDomains();
  } catch {
    return <BackendDown />;
  }
  const domain = domains.find((item) => item.id === id);
  if (!domain) notFound();
  let papers: PaperSummary[];
  try {
    papers = await listPapers({ domain: id });
  } catch {
    return <BackendDown />;
  }

  const analyzed = papers.filter(isAnalyzed);
  const others = papers.filter((paper) => !isAnalyzed(paper));

  return (
    <div className="mx-auto grid max-w-6xl grid-cols-[minmax(0,1fr)] gap-10 px-4 py-10 sm:px-6 lg:grid-cols-[15rem_minmax(0,1fr)]">
      <aside className="min-w-0">
        <DomainSidebar domains={domains} active={id} />
      </aside>

      <div className="min-w-0 space-y-12">
        <Reveal>
          <header className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-cyan-50 via-white to-sky-50 p-8 ring-1 ring-slate-200">
            <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-white text-cyan-700 shadow-sm ring-1 ring-slate-200">
              <DomainIcon id={domain.id} className="h-6 w-6" />
            </span>
            <h1 className="mt-5 text-3xl font-semibold tracking-tight text-slate-900 sm:text-4xl">{domain.name}</h1>
            <p className="mt-2 max-w-2xl text-slate-600">{domain.description}</p>
            <p className="mt-4 text-sm text-slate-500">
              {papers.length} papier{papers.length === 1 ? "" : "s"}
              {analyzed.length > 0 && ` · ${analyzed.length} analysé${analyzed.length === 1 ? "" : "s"} en détail`}
            </p>
          </header>
        </Reveal>

        {analyzed.length > 0 && (
          <section>
            <h2 className="mb-5 text-lg font-semibold text-slate-900">Analysés en détail</h2>
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {analyzed.map((paper, index) => (
                <Reveal key={paper.id} delay={(index % 6) * 50}>
                  <PaperCard paper={paper} />
                </Reveal>
              ))}
            </div>
          </section>
        )}

        {others.length > 0 && (
          <section>
            <h2 className="text-lg font-semibold text-slate-900">
              {analyzed.length > 0 ? "Aussi dans ce domaine" : "Papiers du domaine"}
            </h2>
            <p className="mb-5 mt-1 text-sm text-slate-500">Détails techniques pas encore extraits de leur PDF.</p>
            <ul className="divide-y divide-slate-100 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
              {others.map((paper) => (
                <OtherPaperRow key={paper.id} paper={paper} />
              ))}
            </ul>
          </section>
        )}

        {papers.length === 0 && (
          <p className="rounded-2xl border border-dashed border-slate-300 bg-white px-6 py-12 text-center text-slate-500">
            Aucun papier dans ce domaine pour le moment.
          </p>
        )}
      </div>
    </div>
  );
}
