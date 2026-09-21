import Link from "next/link";
import { BrandMark, Wordmark } from "@/app/components/BrandMark";

export function SiteFooter() {
  return (
    <footer className="border-t border-rule bg-sheet-0">
      <div className="mx-auto flex max-w-6xl flex-col gap-6 px-5 py-10 sm:flex-row sm:items-center sm:justify-between sm:px-8">
        <div>
          <span className="flex items-center gap-2.5 text-ink-900">
            <BrandMark className="h-6 w-6" />
            <Wordmark className="text-base" />
          </span>
          <p className="mt-3 max-w-md text-sm leading-relaxed text-ink-400">
            A value is only shown when the source paper states it. Missing values stay{" "}
            <span className="font-mono text-ink-600">NOT_REPORTED</span>; disagreements stay{" "}
            <span className="font-mono text-ink-600">CONFLICT</span>.
          </p>
        </div>
        <nav aria-label="Footer" className="flex flex-wrap gap-6 text-sm">
          <Link href="/explore" className="text-ink-600 transition hover:text-tide-600">
            Research workspace
          </Link>
          <Link href="/compare" className="text-ink-600 transition hover:text-tide-600">
            Compare papers
          </Link>
        </nav>
      </div>
    </footer>
  );
}
