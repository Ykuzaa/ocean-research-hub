"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import type { PaperSummary } from "@/app/lib/api";
import { PaperCard } from "@/app/components/PaperCard";

export function PaperCarousel({ papers }: { papers: PaperSummary[] }) {
  const track = useRef<HTMLDivElement>(null);
  const [edges, setEdges] = useState({ start: true, end: false });

  const measure = useCallback(() => {
    const node = track.current;
    if (!node) return;
    setEdges({
      start: node.scrollLeft <= 4,
      end: node.scrollLeft + node.clientWidth >= node.scrollWidth - 4,
    });
  }, []);

  useEffect(() => {
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [measure]);

  const scroll = (direction: 1 | -1) => {
    const node = track.current;
    if (node) node.scrollBy({ left: direction * node.clientWidth * 0.85, behavior: "smooth" });
  };

  const button =
    "flex h-10 w-10 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-700 shadow-sm transition hover:border-cyan-300 hover:text-cyan-700 disabled:pointer-events-none disabled:opacity-30";

  return (
    <div>
      <div className="mb-4 flex justify-end gap-2">
        <button type="button" aria-label="Papiers précédents" onClick={() => scroll(-1)} disabled={edges.start} className={button}>
          <ChevronLeft className="h-5 w-5" />
        </button>
        <button type="button" aria-label="Papiers suivants" onClick={() => scroll(1)} disabled={edges.end} className={button}>
          <ChevronRight className="h-5 w-5" />
        </button>
      </div>
      <div
        ref={track}
        onScroll={measure}
        className="no-scrollbar -mx-4 flex snap-x snap-mandatory gap-4 overflow-x-auto scroll-px-4 px-4 pb-4 pt-1"
      >
        {papers.map((paper) => (
          <div key={paper.id} className="w-[19rem] shrink-0 snap-start sm:w-80">
            <PaperCard paper={paper} />
          </div>
        ))}
      </div>
    </div>
  );
}
