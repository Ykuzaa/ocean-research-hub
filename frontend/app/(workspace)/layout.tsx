import Link from "next/link";

export default function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-full bg-sheet-0 text-ink-900">
      <header className="border-b border-rule/70 bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-x-5 gap-y-2 px-5 py-4">
          <Link href="/" className="font-display text-xl font-semibold">Ocean Research Hub</Link>
          <nav className="flex flex-wrap gap-x-5 gap-y-1 text-sm text-ink-600">
            <Link href="/corpus">Corpus</Link>
            <Link href="/demander">Demander</Link>
            <Link href="/analyse">Analyse</Link>
            <Link href="/revue">Audit</Link>
            <Link href="/explore">Catalogue</Link>
            <Link href="/compare">Comparer</Link>
            <Link href="/">Accueil</Link>
          </nav>
        </div>
      </header>
      <main>{children}</main>
    </div>
  );
}
