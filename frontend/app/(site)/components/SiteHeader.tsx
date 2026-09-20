import Link from "next/link";
import { BrandMark, Wordmark } from "@/app/components/BrandMark";

const ANCHORS = [
  { href: "#query", label: "Query" },
  { href: "#extraction", label: "Extraction" },
  { href: "#intelligence", label: "Intelligence" },
];

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-30 border-b border-rule/70 bg-sheet-0/85 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-6xl items-center gap-6 px-5 sm:px-8">
        <Link
          href="/"
          className="flex shrink-0 items-center gap-2.5 text-ink-900 transition hover:text-tide-600"
        >
          <BrandMark className="h-7 w-7" />
          <Wordmark className="hidden text-[0.9375rem] sm:inline" />
        </Link>

        <nav aria-label="Sections" className="ml-auto hidden items-center gap-7 md:flex">
          {ANCHORS.map((anchor) => (
            <a
              key={anchor.href}
              href={anchor.href}
              className="text-sm text-ink-600 transition hover:text-ink-900"
            >
              {anchor.label}
            </a>
          ))}
        </nav>

        <Link
          href="/explore"
          className="ml-auto rounded border border-rule px-3.5 py-1.5 text-sm font-medium text-ink-900 transition hover:border-tide-500 hover:text-tide-600 md:ml-0"
        >
          Workspace
        </Link>
      </div>
    </header>
  );
}
