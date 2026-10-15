import Link from "next/link";

/**
 * The workspace shell: the same search field on every page, so a paper, a method or a
 * dataset can be reached without going back to a landing page first (issue #12).
 */
export default function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-full bg-sheet-0 text-ink-900">
      <header className="border-b border-rule/70 bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-3 px-5 py-4">
          <Link href="/" className="font-display text-xl font-semibold">Ocean Research Hub</Link>
          <form action="/corpus" className="order-last flex min-w-0 flex-1 basis-full gap-2 md:order-none md:basis-auto">
            <input
              name="q"
              type="search"
              placeholder="chercher un papier, une méthode, un jeu de données…"
              aria-label="Chercher dans le corpus"
              className="min-w-0 flex-1 rounded-lg border border-rule px-3 py-1.5 text-sm md:max-w-md"
            />
            <button className="rounded-lg border border-rule px-3 py-1.5 text-sm text-ink-600">Chercher</button>
          </form>
          <nav className="flex flex-wrap gap-x-5 gap-y-1 text-sm text-ink-600">
            <Link href="/corpus">Corpus</Link>
            <Link href="/demander">Demander</Link>
            <Link href="/analyse">Analyse</Link>
            <Link href="/revue">Audit</Link>
            <Link href="/explore">Catalogue</Link>
            <Link href="/compare">Comparer</Link>
          </nav>
        </div>
      </header>
      <main>{children}</main>
    </div>
  );
}
