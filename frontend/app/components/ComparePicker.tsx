"use client";

import { useRouter } from "next/navigation";
import type { PaperSummary } from "@/app/lib/api";

function label(paper: PaperSummary): string {
  const title = paper.title ?? "Titre non détecté";
  return paper.year ? `${title} (${paper.year})` : title;
}

export function ComparePicker({ papers, a, b }: { papers: PaperSummary[]; a?: string; b?: string }) {
  const router = useRouter();

  function select(side: "a" | "b", id: string) {
    const params = new URLSearchParams();
    const next = { a, b, [side]: id || undefined };
    if (next.a) params.set("a", next.a);
    if (next.b) params.set("b", next.b);
    router.push(`/compare?${params}`);
  }

  const selectClass =
    "w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 focus:border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-100";

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {(["a", "b"] as const).map((side) => (
        <label key={side} className="block">
          <span className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-500">
            Papier {side === "a" ? "1" : "2"}
          </span>
          <select
            value={(side === "a" ? a : b) ?? ""}
            onChange={(event) => select(side, event.target.value)}
            className={selectClass}
          >
            <option value="">Choisir un papier…</option>
            {papers.map((paper) => (
              <option key={paper.id} value={paper.id} disabled={paper.id === (side === "a" ? b : a)}>
                {label(paper)}
              </option>
            ))}
          </select>
        </label>
      ))}
    </div>
  );
}
