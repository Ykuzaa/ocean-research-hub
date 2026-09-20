import Link from "next/link";
import { BrandMark, Wordmark } from "@/app/components/BrandMark";

export default function NotFound() {
  return (
    <div className="flex min-h-full flex-1 flex-col">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex h-16 max-w-6xl items-center px-4 sm:px-6">
          <Link
            href="/"
            className="flex items-center gap-2.5 text-slate-900 transition hover:text-cyan-800"
          >
            <BrandMark className="h-7 w-7" />
            <Wordmark />
          </Link>
        </div>
      </header>
      <main className="mx-auto flex max-w-md flex-1 flex-col justify-center px-4 py-20 text-center">
        <p className="font-mono text-sm text-cyan-700">404</p>
        <h1 className="mt-2 text-2xl font-semibold text-slate-900">Page introuvable</h1>
        <p className="mt-2 text-sm text-slate-500">Ce papier n&apos;existe pas ou a été supprimé.</p>
        <Link
          href="/explore"
          className="mx-auto mt-6 inline-flex rounded-lg bg-cyan-700 px-4 py-2 text-sm font-medium text-white transition hover:bg-cyan-800"
        >
          Retour au corpus
        </Link>
      </main>
    </div>
  );
}
