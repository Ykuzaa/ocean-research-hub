import type { Domain, PaperSummary } from "@/app/lib/api";
import { SearchBox } from "@/app/components/SearchBox";

// Two identical periods (720 px each) per 1440 px half, so sliding the layer
// by exactly half its width loops without a seam.
const WAVE = "M0 40 Q180 0 360 40 T720 40 T1080 40 T1440 40 T1800 40 T2160 40 T2520 40 T2880 40 V120 H0 Z";

function WaveLayer({ className, fill }: { className: string; fill: string }) {
  return (
    <svg viewBox="0 0 2880 120" preserveAspectRatio="none" aria-hidden className={`absolute bottom-0 left-0 h-24 w-[200%] ${className}`}>
      <path d={WAVE} className={fill} />
    </svg>
  );
}

export function Hero({ papers, domains }: { papers: PaperSummary[]; domains: Domain[] }) {
  const analyzed = papers.filter((paper) => paper.extracted_field_count > 0).length;

  return (
    <section className="relative isolate overflow-hidden bg-gradient-to-b from-cyan-50 via-sky-50/60 to-slate-50">
      <div aria-hidden className="absolute -top-40 left-1/2 -z-10 h-[32rem] w-[64rem] -translate-x-1/2 rounded-full bg-cyan-200/30 blur-3xl" />

      <div className="relative mx-auto max-w-4xl px-4 pb-36 pt-20 text-center sm:px-6 sm:pt-28">
        <p className="text-xs font-semibold uppercase tracking-[0.25em] text-cyan-700">Machine learning × océanographie</p>
        <h1 className="mt-5 bg-gradient-to-br from-slate-900 via-cyan-900 to-cyan-600 bg-clip-text pb-2 text-5xl font-semibold tracking-tight text-transparent sm:text-7xl">
          Ocean Research Hub
        </h1>
        <p className="mx-auto mt-5 max-w-2xl text-lg leading-relaxed text-slate-600">
          Les détails techniques des papiers d&apos;IA pour l&apos;océan — données, architecture, entraînement,
          résultats — lus dans le PDF et classés par domaine.
        </p>
        <div className="mt-10">
          <SearchBox papers={papers} domains={domains} />
        </div>
        <p className="mt-5 text-sm text-slate-500">
          {papers.length} papiers dans {domains.length} domaines
          {analyzed > 0 && ` · ${analyzed} analysés en détail`}
        </p>
      </div>

      <WaveLayer className="wave-layer wave-layer-slow bottom-3 opacity-60" fill="fill-cyan-100" />
      <WaveLayer className="wave-layer" fill="fill-slate-50" />
    </section>
  );
}
