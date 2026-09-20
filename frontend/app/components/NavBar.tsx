"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BrandMark, Wordmark } from "@/app/components/BrandMark";

const LINKS = [
  {
    href: "/explore",
    label: "Domaines",
    match: (path: string) => path.startsWith("/explore") || path.startsWith("/domains"),
  },
  { href: "/compare", label: "Comparer", match: (path: string) => path.startsWith("/compare") },
];

export function NavBar() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-30 border-b border-slate-200/70 bg-white/80 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-6xl items-center gap-4 px-4 sm:gap-8 sm:px-6">
        <Link
          href="/explore"
          className="flex shrink-0 items-center gap-2.5 text-slate-900 transition hover:text-cyan-800"
        >
          <BrandMark className="h-7 w-7" />
          <Wordmark className="hidden sm:inline" />
        </Link>
        <nav className="ml-auto flex items-center gap-1">
          {LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={`rounded-full px-3 py-1.5 text-sm font-medium transition sm:px-4 ${
                link.match(pathname)
                  ? "bg-slate-900 text-white"
                  : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
              }`}
            >
              {link.label}
            </Link>
          ))}
          <Link
            href="/"
            className="ml-1 rounded-full px-3 py-1.5 text-sm text-slate-600 transition hover:text-slate-900 sm:px-4"
          >
            Présentation
          </Link>
        </nav>
      </div>
    </header>
  );
}
