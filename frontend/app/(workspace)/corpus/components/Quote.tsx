/**
 * The sentence a value was read from, with the page it sits on.
 *
 * Every number in the corpus v2 views is shown through this component, because a value
 * without its sentence is exactly what made the first corpus unusable.
 */
export function Quote({ quote, page, label }: { quote: string | null; page: number | null; label?: string }) {
  if (!quote) {
    // The contract forbids storing an altered sentence, so the absence is shown as such.
    return (
      <p className="rounded-lg border border-dashed border-rule bg-sheet-1 p-3 text-sm text-ink-600">
        Valeur lue sur la page telle qu’elle s’affiche{page ? ` (page ${page})` : ""}. Le papier
        l’imprime en notation mathématique&nbsp;: aucune phrase ne peut la porter sans l’altérer,
        donc aucune citation n’a été enregistrée. À confirmer à l’œil.
      </p>
    );
  }
  return (
    <figure className="m-0 min-w-0 rounded-lg border border-rule bg-sheet-1 p-3">
      <blockquote className="m-0 break-words text-sm leading-relaxed text-ink-900">« {quote} »</blockquote>
      <figcaption className="mt-2 font-mono text-[11px] tracking-wide text-ink-400">
        {[label, page ? `page ${page}` : null].filter(Boolean).join(" · ")}
      </figcaption>
    </figure>
  );
}

/** A value with its sentence folded away: the page stays readable, the proof stays one click deep. */
export function ValueWithSource({
  label, value, unit, quote, page, note, children,
}: {
  label: string; value: React.ReactNode; unit?: string | null; quote: string | null;
  page: number | null; note?: string | null; children?: React.ReactNode;
}) {
  return (
    <details className="group rounded-lg border border-rule bg-sheet-2">
      <summary className="flex cursor-pointer flex-wrap items-baseline gap-x-3 gap-y-1 px-3 py-2 text-sm">
        <span className="text-ink-400">{label}</span>
        <span className="font-mono font-medium text-ink-900">
          {value}
          {unit ? <span className="ml-1 text-ink-400">{unit}</span> : null}
        </span>
        <span className="ml-auto text-xs text-tide-500 group-open:hidden">
          {quote ? "voir la phrase source" : "lue sur la page, sans citation"}
        </span>
      </summary>
      <div className="grid gap-2 border-t border-rule p-3">
        <Quote quote={quote} page={page} />
        {note ? <p className="text-xs text-ink-400">Note d’extraction : {note}</p> : null}
        {children}
      </div>
    </details>
  );
}
