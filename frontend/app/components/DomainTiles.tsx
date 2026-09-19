import Link from "next/link";
import { ArrowRight } from "lucide-react";
import type { Domain } from "@/app/lib/api";
import { DomainIcon, accentFor } from "@/app/lib/domains";
import { Reveal } from "@/app/components/Reveal";

export function DomainTiles({ domains }: { domains: Domain[] }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-3 xl:grid-cols-4">
      {domains.map((domain, index) => {
        const accent = accentFor(index);
        return (
          <Reveal key={domain.id} delay={(index % 8) * 40}>
            <Link
              href={`/domains/${domain.id}`}
              className="group flex h-full flex-col rounded-2xl border border-slate-200 bg-white p-4 shadow-sm transition duration-300 hover:-translate-y-1 hover:border-cyan-200 hover:shadow-xl hover:shadow-cyan-900/5 sm:p-5"
            >
              <span
                className={`flex h-10 w-10 items-center justify-center rounded-xl ring-1 transition-colors duration-300 sm:h-11 sm:w-11 ${accent.badge} ${accent.hover}`}
              >
                <DomainIcon id={domain.id} className="h-5 w-5" />
              </span>
              <h3 className="mt-3 text-sm font-semibold leading-snug text-slate-900 sm:mt-4 sm:text-base">{domain.name}</h3>
              <p className="mt-1.5 hidden text-sm leading-relaxed text-slate-500 sm:line-clamp-2">{domain.description}</p>
              <span className="mt-auto flex items-center justify-between pt-4 text-sm sm:pt-5">
                <span className="font-medium text-slate-700">
                  {domain.paper_count} papier{domain.paper_count === 1 ? "" : "s"}
                </span>
                <ArrowRight
                  aria-hidden
                  className="h-4 w-4 text-slate-300 transition duration-300 group-hover:translate-x-1 group-hover:text-cyan-600"
                />
              </span>
            </Link>
          </Reveal>
        );
      })}
    </div>
  );
}
