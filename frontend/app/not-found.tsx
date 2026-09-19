import Link from "next/link";

export default function NotFound() {
  return (
    <div className="mx-auto max-w-md py-20 text-center">
      <p className="text-sm font-medium text-cyan-700">404</p>
      <h1 className="mt-1 text-2xl font-semibold text-slate-900">Page introuvable</h1>
      <p className="mt-2 text-sm text-slate-500">Ce papier n&apos;existe pas ou a été supprimé.</p>
      <Link href="/" className="mt-6 inline-flex rounded-lg bg-cyan-700 px-4 py-2 text-sm font-medium text-white hover:bg-cyan-800">
        Retour aux papiers
      </Link>
    </div>
  );
}
