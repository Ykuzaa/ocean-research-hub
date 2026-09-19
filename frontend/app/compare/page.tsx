import { getPaper, listPapers, type PaperSummary, type StoredPaper } from "@/app/lib/api";
import { SECTIONS, hasContent, paperTitle, sectionEntries, fieldAt } from "@/app/lib/fields";
import { ComparePicker } from "@/app/components/ComparePicker";
import { FieldValue } from "@/app/components/FieldValue";
import { BackendDown } from "@/app/components/BackendDown";

function single(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

function ComparisonTable({ left, right }: { left: StoredPaper; right: StoredPaper }) {
  const sections = SECTIONS.map((section) => {
    const rows = sectionEntries(left.record, section.key)
      .map((entry) => ({ ...entry, right: fieldAt(right.record, entry.path) }))
      .filter((row) => hasContent(row.field) || hasContent(row.right));
    return { ...section, rows };
  }).filter((section) => section.rows.length > 0);

  const headerCell = "min-w-0 text-sm font-semibold leading-snug text-slate-900";
  const empty = <span className="text-sm text-slate-300">—</span>;

  return (
    <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="min-w-[40rem]">
      <div className="grid grid-cols-[minmax(8rem,12rem)_1fr_1fr] gap-4 border-b border-slate-200 px-5 py-4">
        <span />
        <span className={headerCell}>{paperTitle(left.record) ?? "Papier 1"}</span>
        <span className={headerCell}>{paperTitle(right.record) ?? "Papier 2"}</span>
      </div>
      {sections.map((section) => (
        <section key={section.key}>
          <h2 className="border-b border-slate-100 bg-slate-50 px-5 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
            {section.title}
          </h2>
          {section.rows.map((row) => (
            <div
              key={row.path}
              className="grid grid-cols-[minmax(8rem,12rem)_1fr_1fr] gap-4 border-b border-slate-100 px-5 py-2.5 last:border-b-0"
            >
              <span className="pt-1 text-sm text-slate-500">{row.label}</span>
              <div className="min-w-0">{hasContent(row.field) ? <FieldValue field={row.field} /> : empty}</div>
              <div className="min-w-0">{row.right && hasContent(row.right) ? <FieldValue field={row.right} /> : empty}</div>
            </div>
          ))}
        </section>
      ))}
      </div>
    </div>
  );
}

export default async function ComparePage(props: PageProps<"/compare">) {
  const searchParams = await props.searchParams;
  const a = single(searchParams.a);
  const b = single(searchParams.b);

  let papers: PaperSummary[];
  let pair: [StoredPaper, StoredPaper] | null = null;
  try {
    papers = (await listPapers()).papers;
    if (a && b && a !== b) pair = await Promise.all([getPaper(a), getPaper(b)]);
  } catch {
    return <BackendDown />;
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Comparer deux papiers</h1>
        <p className="mt-1 text-sm text-slate-500">
          Section par section, uniquement les infos trouvées dans au moins un des deux papiers.
        </p>
      </header>

      <ComparePicker papers={papers} a={a} b={b} />

      {pair ? (
        <ComparisonTable left={pair[0]} right={pair[1]} />
      ) : (
        <p className="rounded-xl border border-dashed border-slate-300 bg-white px-4 py-10 text-center text-sm text-slate-500">
          {papers.length < 2
            ? "Il faut au moins deux papiers pour comparer. Ajoute-en un autre."
            : "Choisis deux papiers pour les voir côte à côte."}
        </p>
      )}
    </div>
  );
}
