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
      <div className="mx-auto flex h-16 max-w-7xl items-center gap-4 px-4 sm:gap-6 sm:px-8">
        <Link
          href="/"
          className="flex shrink-0 items-center gap-2.5 text-ink-900 transition hover:text-tide-600"
        >
          <BrandMark className="h-7 w-7" />
          <Wordmark className="hidden text-base sm:inline" />
        </Link>

        <nav aria-label="Sections" className="ml-auto hidden items-center gap-7 md:flex">
          {ANCHORS.map((anchor) => (
            <a
              key={anchor.href}
              href={anchor.href}
              className="text-[0.9375rem] text-ink-600 transition hover:text-ink-900"
            >
              {anchor.label}
            </a>
          ))}
        </nav>

        <Link
          href="/explore"
          className="ml-auto whitespace-nowrap rounded border border-rule px-3 py-2 text-[0.9375rem] font-medium text-ink-900 transition hover:border-tide-500 hover:text-tide-600 sm:px-4 md:ml-0"
        >
          Workspace
        </Link>
      </div>
    </header>
  );
}
