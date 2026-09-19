import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, ExternalLink, FileText, GitCompareArrows } from "lucide-react";
import { ApiError, getPaper, listDomains, type Domain, type StoredPaper } from "@/app/lib/api";
import { SECTIONS, fieldAt, hasContent, paperTitle, sectionEntries } from "@/app/lib/fields";
import { DomainIcon } from "@/app/lib/domains";
import { FieldValue } from "@/app/components/FieldValue";
import { ModelTag } from "@/app/components/PaperCard";
import { BackendDown } from "@/app/components/BackendDown";
import { Reveal } from "@/app/components/Reveal";

// Shown in the header instead of being repeated in the section list.
const HEADER_PATHS = new Set(["results.headline"]);

export default async function PaperPage(props: PageProps<"/papers/[id]">) {
  const { id } = await props.params;
  let paper: StoredPaper;
  let domains: Domain[];
  try {
    [paper, domains] = await Promise.all([getPaper(id), listDomains()]);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    return <BackendDown />;
  }

  const record = paper.record;
  const title = paperTitle(record);
  const authors = fieldAt(record, "paper.authors")?.value;
  const year = fieldAt(record, "paper.year")?.value;
  const venue = fieldAt(record, "paper.venue")?.value;
  const family = fieldAt(record, "architecture.family")?.value;
  const headline = fieldAt(record, "results.headline");
  const paperDomains = paper.domains
    .map((domainId) => domains.find((domain) => domain.id === domainId))
    .filter((domain): domain is Domain => Boolean(domain));

  const sections = SECTIONS.map((section) => ({
    ...section,
    entries: sectionEntries(record, section.key).filter(
      (entry) => hasContent(entry.field) && !HEADER_PATHS.has(entry.path),
    ),
  })).filter((section) => section.entries.length > 0);

  const meta = [typeof year === "number" ? String(year) : null, typeof venue === "string" ? venue : null]
    .filter(Boolean)
    .join(" · ");
  const doiLink = paper.doi && !paper.doi.startsWith("10.48550/") ? `https://doi.org/${paper.doi}` : null;
  const arxivLink = paper.doi?.startsWith("10.48550/arxiv.")
    ? `https://arxiv.org/abs/${paper.doi.slice("10.48550/arxiv.".length)}`
    : null;
  const backHref = paperDomains[0] ? `/domains/${paperDomains[0].id}` : "/";

  return (
    <div className="mx-auto max-w-6xl space-y-8 px-4 py-10 sm:px-6">
      <Link href={backHref} className="inline-flex items-center gap-1.5 text-sm text-slate-500 transition hover:text-cyan-700">
        <ArrowLeft aria-hidden className="h-4 w-4" />
        {paperDomains[0] ? paperDomains[0].name : "Accueil"}
      </Link>

      <Reveal>
        <header className="relative overflow-hidden rounded-3xl bg-white p-6 shadow-sm ring-1 ring-slate-200 sm:p-10">
          <div aria-hidden className="absolute -right-24 -top-24 h-64 w-64 rounded-full bg-cyan-100/50 blur-3xl" />
          <div className="relative">
            {paperDomains.length > 0 && (
              <div className="mb-5 flex flex-wrap gap-2">
                {paperDomains.map((domain) => (
                  <Link
                    key={domain.id}
                    href={`/domains/${domain.id}`}
                    className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-700 transition hover:bg-cyan-50 hover:text-cyan-800"
                  >
                    <DomainIcon id={domain.id} className="h-3.5 w-3.5" />
                    {domain.name}
                  </Link>
                ))}
              </div>
            )}

            <h1 className="max-w-4xl text-2xl font-semibold leading-tight tracking-tight text-slate-900 sm:text-4xl">
              {title ?? <span className="font-normal italic text-slate-400">Titre non détecté</span>}
            </h1>
            {Array.isArray(authors) && authors.length > 0 && (
              <p className="mt-4 max-w-4xl text-sm leading-relaxed text-slate-600">{authors.join(", ")}</p>
            )}

            <div className="mt-5 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
              {meta && <span className="text-slate-500">{meta}</span>}
              {(doiLink || arxivLink) && (
                <a
                  href={doiLink ?? arxivLink!}
                  className="inline-flex items-center gap-1 font-medium text-cyan-700 hover:underline"
                >
                  {doiLink ? "Voir la publication" : "Voir sur arXiv"}
                  <ExternalLink aria-hidden className="h-3.5 w-3.5" />
                </a>
              )}
              {sections.length > 0 && (
                <Link
                  href={`/compare?a=${paper.id}`}
                  className="inline-flex items-center gap-1.5 font-medium text-slate-600 hover:text-cyan-700"
                >
                  <GitCompareArrows aria-hidden className="h-4 w-4" />
                  Comparer avec un autre papier
                </Link>
              )}
            </div>

            {Array.isArray(family) && family.length > 0 && (
              <div className="mt-6 flex flex-wrap gap-1.5">
                {family.map((name) => (
                  <ModelTag key={String(name)}>{String(name)}</ModelTag>
                ))}
              </div>
            )}

            {headline && hasContent(headline) && (
              <div className="mt-6 rounded-2xl bg-gradient-to-br from-cyan-50 to-sky-50 p-5 ring-1 ring-cyan-100">
                <p className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-cyan-800">Résultat clé</p>
                <FieldValue field={headline} />
              </div>
            )}
          </div>
        </header>
      </Reveal>

      {sections.length === 0 ? (
        <Reveal>
          <div className="flex items-start gap-4 rounded-3xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-slate-100 text-slate-500">
              <FileText aria-hidden className="h-5 w-5" />
            </span>
            <div>
              <p className="font-medium text-slate-900">Détails techniques pas encore extraits</p>
              <p className="mt-1 text-sm leading-relaxed text-slate-500">
                Soit le PDF n&apos;a pas encore été analysé, soit il n&apos;est pas en accès libre. Les informations
                ci-dessus viennent de la notice bibliographique du papier.
              </p>
            </div>
          </div>
        </Reveal>
      ) : (
        <>
          <nav className="flex flex-wrap gap-2">
            {sections.map((section) => (
              <a
                key={section.key}
                href={`#${section.key}`}
                className="rounded-full border border-slate-200 bg-white px-3.5 py-1.5 text-sm font-medium text-slate-600 transition hover:border-cyan-300 hover:text-cyan-800"
              >
                {section.title}
              </a>
            ))}
          </nav>

          <div className="grid items-start gap-6 lg:grid-cols-2">
            {sections.map((section) => (
              <section key={section.key} id={section.key} className="scroll-mt-24 rounded-3xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
                  <h2 className="mb-3 text-lg font-semibold text-slate-900">{section.title}</h2>
                  <dl className="divide-y divide-slate-100">
                    {section.entries.map((entry) => (
                      <div key={entry.path} className="grid gap-1 py-3 sm:grid-cols-[9.5rem_1fr] sm:gap-4">
                        <dt className="pt-1 text-sm text-slate-500">{entry.label}</dt>
                        <dd className="min-w-0">
                          <FieldValue field={entry.field} />
                        </dd>
                      </div>
                    ))}
                  </dl>
              </section>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
