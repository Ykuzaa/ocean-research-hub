import Link from "next/link";
import { notFound } from "next/navigation";
import { ApiError, getPaper, type StoredPaper } from "@/app/lib/api";
import { SECTIONS, fieldAt, hasContent, paperTitle, sectionEntries } from "@/app/lib/fields";
import { FieldValue } from "@/app/components/FieldValue";
import { ArchitectureTag } from "@/app/components/PaperCard";
import { BackendDown } from "@/app/components/BackendDown";

// Shown in the header instead of being repeated in the section list.
const HEADER_PATHS = new Set(["results.headline"]);

export default async function PaperPage(props: PageProps<"/papers/[id]">) {
  const { id } = await props.params;
  let paper: StoredPaper;
  try {
    paper = await getPaper(id);
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

  const sections = SECTIONS.map((section) => ({
    ...section,
    entries: sectionEntries(record, section.key).filter(
      (entry) => hasContent(entry.field) && !HEADER_PATHS.has(entry.path),
    ),
  })).filter((section) => section.entries.length > 0);

  const meta = [typeof year === "number" ? String(year) : null, typeof venue === "string" ? venue : null]
    .filter(Boolean)
    .join(" · ");

  return (
    <div className="space-y-6">
      <Link href="/" className="inline-flex text-sm text-slate-500 hover:text-cyan-700">
        ← Tous les papiers
      </Link>

      <header className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <h1 className="text-2xl font-semibold leading-tight tracking-tight text-slate-900">
              {title ?? <span className="font-normal italic text-slate-400">Titre non détecté</span>}
            </h1>
            {Array.isArray(authors) && authors.length > 0 && (
              <p className="mt-2 text-sm text-slate-600">{authors.join(", ")}</p>
            )}
            {(meta || paper.doi) && (
              <p className="mt-1 text-sm text-slate-500">
                {meta}
                {meta && paper.doi && " · "}
                {paper.doi && (
                  <a href={`https://doi.org/${paper.doi}`} className="text-cyan-700 hover:underline">
                    DOI {paper.doi}
                  </a>
                )}
              </p>
            )}
          </div>
          <Link
            href={`/compare?a=${paper.id}`}
            className="shrink-0 rounded-lg border border-slate-200 px-3.5 py-2 text-sm font-medium text-slate-700 transition hover:border-cyan-300 hover:text-cyan-800"
          >
            Comparer avec…
          </Link>
        </div>

        {Array.isArray(family) && family.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-1.5">
            {family.map((name) => (
              <ArchitectureTag key={String(name)}>{String(name)}</ArchitectureTag>
            ))}
          </div>
        )}

        {headline && hasContent(headline) && (
          <div className="mt-5 rounded-xl bg-cyan-50/70 p-4">
            <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-cyan-800">Résultat clé</p>
            <FieldValue field={headline} />
          </div>
        )}
      </header>

      {sections.length === 0 ? (
        <p className="rounded-xl border border-dashed border-slate-300 bg-white px-4 py-10 text-center text-sm text-slate-500">
          Aucun détail technique n&apos;a encore été extrait de ce papier.
        </p>
      ) : (
        <>
          <nav className="flex flex-wrap gap-2">
            {sections.map((section) => (
              <a
                key={section.key}
                href={`#${section.key}`}
                className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-medium text-slate-600 transition hover:border-cyan-300 hover:text-cyan-800"
              >
                {section.title} <span className="text-slate-400">{section.entries.length}</span>
              </a>
            ))}
          </nav>

          <div className="grid items-start gap-6 lg:grid-cols-2">
            {sections.map((section) => (
              <section
                key={section.key}
                id={section.key}
                className="scroll-mt-24 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
              >
                <h2 className="mb-3 font-semibold text-slate-900">{section.title}</h2>
                <dl className="divide-y divide-slate-100">
                  {section.entries.map((entry) => (
                    <div key={entry.path} className="grid gap-1 py-2.5 sm:grid-cols-[10rem_1fr] sm:gap-4">
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
