"use client";

import { useState, type KeyboardEvent, type ReactNode } from "react";
import type { EvidenceField, SourceEvidence } from "@/app/lib/api";

function renderValue(value: unknown): ReactNode {
  if (Array.isArray(value)) {
    const compact = value.every((item) => typeof item === "string" && item.length <= 40);
    if (compact) {
      return (
        <span className="flex flex-wrap gap-1.5">
          {value.map((item, index) => (
            <span key={index} className="rounded-md bg-slate-100 px-2 py-0.5 text-slate-700">
              {String(item)}
            </span>
          ))}
        </span>
      );
    }
    return (
      <ul className="list-disc space-y-1 pl-4 marker:text-slate-300">
        {value.map((item, index) => (
          <li key={index}>{String(item)}</li>
        ))}
      </ul>
    );
  }
  if (typeof value === "boolean") return value ? "Oui" : "Non";
  if (typeof value === "number") return value.toLocaleString("fr-FR");
  if (typeof value === "object" && value !== null) {
    const links = Object.values(value).flat().filter((v): v is string => typeof v === "string");
    return (
      <span className="flex flex-col gap-0.5">
        {links.map((href) => (
          <a key={href} href={href} className="truncate text-cyan-700 hover:underline" onClick={(e) => e.stopPropagation()}>
            {href}
          </a>
        ))}
      </span>
    );
  }
  return String(value);
}

function SourceQuote({ source }: { source: SourceEvidence }) {
  const where = [
    source.page ? `Page ${source.page}` : null,
    source.section,
    source.origin === "SUPPLEMENTARY_MATERIAL" ? "Matériel supplémentaire" : null,
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <figure className="rounded-lg border border-cyan-100 bg-cyan-50/60 px-3.5 py-2.5">
      <blockquote className="text-sm italic leading-relaxed text-slate-700">« {source.evidence} »</blockquote>
      {where && <figcaption className="mt-1.5 text-xs font-medium text-cyan-800">{where}</figcaption>}
    </figure>
  );
}

/** A value from the paper; clicking it reveals the exact sentence and page it was read from. */
export function FieldValue({ field }: { field: EvidenceField }) {
  const [open, setOpen] = useState(false);
  const sources = [field.source, ...field.sources].filter((source) => source.evidence);
  const isConflict = field.value === null && field.conflict_values.length > 0;
  const clickable = sources.length > 0;

  const toggle = () => clickable && setOpen((current) => !current);
  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      toggle();
    }
  };

  return (
    <div>
      <div
        role={clickable ? "button" : undefined}
        tabIndex={clickable ? 0 : undefined}
        aria-expanded={clickable ? open : undefined}
        onClick={toggle}
        onKeyDown={clickable ? onKeyDown : undefined}
        className={`group -mx-2 flex items-start gap-2 rounded-md px-2 py-1 text-sm text-slate-800 ${
          clickable ? "cursor-pointer hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500" : ""
        }`}
      >
        <div className="min-w-0 flex-1">
          {isConflict ? (
            <div>
              <p className="mb-1 text-xs font-medium text-amber-700">Le papier donne deux valeurs différentes :</p>
              {renderValue(field.conflict_values)}
            </div>
          ) : (
            renderValue(field.value)
          )}
        </div>
        {clickable && (
          <span
            className={`mt-0.5 shrink-0 text-xs font-medium transition ${
              open ? "text-cyan-700" : "text-slate-300 group-hover:text-cyan-700"
            }`}
          >
            {open ? "Masquer" : "Source"}
          </span>
        )}
      </div>
      {open && (
        <div className="mt-2 space-y-2">
          {sources.map((source, index) => (
            <SourceQuote key={index} source={source} />
          ))}
        </div>
      )}
    </div>
  );
}
