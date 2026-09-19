import { isAnalyzed, listDomains, listPapers, type Domain, type PaperSummary } from "@/app/lib/api";
import { Hero } from "@/app/components/Hero";
import { DomainTiles } from "@/app/components/DomainTiles";
import { PaperCarousel } from "@/app/components/PaperCarousel";
import { BackendDown } from "@/app/components/BackendDown";
import { Reveal } from "@/app/components/Reveal";

function SectionHeading({ kicker, title, children }: { kicker: string; title: string; children?: React.ReactNode }) {
  return (
    <div className="mb-8 max-w-2xl">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-700">{kicker}</p>
      <h2 className="mt-2 text-3xl font-semibold tracking-tight text-slate-900">{title}</h2>
      {children && <p className="mt-2 text-slate-500">{children}</p>}
    </div>
  );
}

export default async function HomePage() {
  let papers: PaperSummary[];
  let domains: Domain[];
  try {
    [papers, domains] = await Promise.all([listPapers(), listDomains()]);
  } catch {
    return <BackendDown />;
  }
  const featured = papers.filter(isAnalyzed).slice(0, 12);

  return (
    <>
      <Hero papers={papers} domains={domains} />

      <div className="mx-auto max-w-6xl space-y-24 px-4 pb-24 sm:px-6">
        <section>
          <Reveal>
            <SectionHeading kicker="Explorer" title="Par domaine">
              Un papier peut appartenir à plusieurs domaines : GLONET est à la fois un système de prévision, un
              neural operator et un modèle de courants.
            </SectionHeading>
          </Reveal>
          <DomainTiles domains={domains} />
        </section>

        {featured.length > 0 && (
          <section>
            <Reveal>
              <SectionHeading kicker="À la une" title="Papiers analysés en détail">
                Architecture, données, entraînement et résultats extraits du PDF. Clique sur une valeur dans une fiche
                pour voir la phrase exacte du papier.
              </SectionHeading>
            </Reveal>
            <Reveal delay={80}>
              <PaperCarousel papers={featured} />
            </Reveal>
          </section>
        )}
      </div>
    </>
  );
}
