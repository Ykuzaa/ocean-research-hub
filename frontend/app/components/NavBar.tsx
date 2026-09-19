"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Papiers" },
  { href: "/compare", label: "Comparer" },
];

function WaveMark() {
  return (
    <svg viewBox="0 0 32 32" aria-hidden className="h-8 w-8">
      <rect width="32" height="32" rx="8" className="fill-cyan-600" />
      <path
        d="M5 18c2.5 0 2.5-3 5-3s2.5 3 5 3 2.5-3 5-3 2.5 3 5 3 2-1.5 2-1.5M5 23c2.5 0 2.5-3 5-3s2.5 3 5 3 2.5-3 5-3 2.5 3 5 3 2-1.5 2-1.5"
        fill="none"
        strokeWidth="2"
        strokeLinecap="round"
        className="stroke-white"
      />
      <circle cx="22" cy="10" r="2.5" className="fill-white/80" />
    </svg>
  );
}

export function NavBar() {
  const pathname = usePathname();
  const isActive = (href: string) =>
    href === "/" ? pathname === "/" || pathname.startsWith("/papers") : pathname.startsWith(href);

  return (
    <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/90 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-6xl items-center gap-6 px-4 sm:px-6">
        <Link href="/" className="flex items-center gap-2.5">
          <WaveMark />
          <span className="font-semibold tracking-tight text-slate-900">Ocean Research Hub</span>
        </Link>
        <nav className="hidden items-center gap-1 sm:flex">
          {LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${
                isActive(link.href)
                  ? "bg-cyan-50 text-cyan-800"
                  : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
              }`}
            >
              {link.label}
            </Link>
          ))}
        </nav>
        <Link
          href="/add"
          className="ml-auto inline-flex items-center gap-1.5 rounded-lg bg-cyan-700 px-3.5 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-cyan-800"
        >
          <span aria-hidden className="text-base leading-none">+</span>
          Ajouter un papier
        </Link>
      </div>
    </header>
  );
}
