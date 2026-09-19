"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { ApiError, ingestPaper } from "@/app/lib/api";

const ERROR_MESSAGES: Record<string, string> = {
  PARSER_ERROR: "Impossible de lire ce PDF. Vérifie que le lien mène bien à un PDF accessible publiquement.",
  INVALID_DOI: "Ce DOI n'a pas un format valide (exemple : 10.5194/gmd-16-2119-2023).",
  METADATA_PROVIDER_ERROR: "Impossible de récupérer les infos liées à ce DOI pour le moment.",
  INGESTION_CONFLICT: "Ce papier existe déjà avec un contenu différent.",
  PERSISTENCE_ERROR: "Le serveur n'a pas pu enregistrer le papier.",
};

/** Accepts an arXiv id, an arXiv abs/pdf link, or any direct PDF URL. */
function toPdfUrl(input: string): string | null {
  const text = input.trim();
  const bareId = text.match(/^(?:arxiv:)?(\d{4}\.\d{4,5}(?:v\d+)?)$/i);
  if (bareId) return `https://arxiv.org/pdf/${bareId[1]}`;
  const arxivLink = text.match(/^https?:\/\/(?:www\.)?arxiv\.org\/(?:abs|pdf)\/([^\s?#]+?)(?:\.pdf)?\/?$/i);
  if (arxivLink) return `https://arxiv.org/pdf/${arxivLink[1]}`;
  return /^https?:\/\/\S+$/i.test(text) ? text : null;
}

function Elapsed({ since }: { since: number }) {
  const [now, setNow] = useState(since);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const seconds = Math.max(0, Math.floor((now - since) / 1000));
  return (
    <span className="tabular-nums">
      {Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, "0")}
    </span>
  );
}

export default function AddPaperPage() {
  const router = useRouter();
  const [link, setLink] = useState("");
  const [doi, setDoi] = useState("");
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    const pdfUrl = toPdfUrl(link);
    if (!pdfUrl) {
      setError("Colle un lien arXiv (ex : https://arxiv.org/abs/2211.02556), un identifiant arXiv ou l'URL d'un PDF.");
      return;
    }
    setStartedAt(Date.now());
    try {
      const result = await ingestPaper({ pdf_url: pdfUrl, ...(doi.trim() ? { doi: doi.trim() } : {}) });
      router.push(`/papers/${result.paper.id}`);
    } catch (caught) {
      setStartedAt(null);
      if (caught instanceof ApiError) {
        setError((caught.code && ERROR_MESSAGES[caught.code]) ?? caught.message);
      } else {
        setError("Le serveur de données ne répond pas. Vérifie qu'il tourne (uv run ocean-research-hub).");
      }
    }
  }

  const busy = startedAt !== null;

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Ajouter un papier</h1>
        <p className="mt-1 text-sm text-slate-500">
          L&apos;IA lit tout le PDF, extrait les détails techniques et vérifie que chaque info se trouve bien
          mot pour mot dans le papier.
        </p>
      </header>

      <form onSubmit={onSubmit} className="space-y-5 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div>
          <label htmlFor="link" className="block text-sm font-medium text-slate-800">
            Lien du papier
          </label>
          <input
            id="link"
            required
            disabled={busy}
            value={link}
            onChange={(event) => setLink(event.target.value)}
            placeholder="https://arxiv.org/abs/2211.02556"
            className="mt-1.5 w-full rounded-lg border border-slate-300 px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-100 disabled:bg-slate-50"
          />
          <p className="mt-1.5 text-xs text-slate-500">Lien arXiv, identifiant arXiv, ou URL directe d&apos;un PDF.</p>
        </div>

        <div>
          <label htmlFor="doi" className="block text-sm font-medium text-slate-800">
            DOI <span className="font-normal text-slate-400">(optionnel)</span>
          </label>
          <input
            id="doi"
            disabled={busy}
            value={doi}
            onChange={(event) => setDoi(event.target.value)}
            placeholder="10.5194/gmd-16-2119-2023"
            className="mt-1.5 w-full rounded-lg border border-slate-300 px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-100 disabled:bg-slate-50"
          />
          <p className="mt-1.5 text-xs text-slate-500">
            Si tu l&apos;as, le titre, les auteurs et la revue viendront directement de la base Crossref.
          </p>
        </div>

        {error && (
          <p className="rounded-lg border border-rose-200 bg-rose-50 px-3.5 py-2.5 text-sm text-rose-800">{error}</p>
        )}

        {busy ? (
          <div className="flex items-center gap-3 rounded-lg bg-cyan-50 px-4 py-3 text-sm text-cyan-900">
            <span className="h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-cyan-600 border-t-transparent" />
            <span className="flex-1">
              Lecture et extraction en cours… en général 1 à 3 minutes. Tu peux laisser la page ouverte.
            </span>
            <Elapsed since={startedAt} />
          </div>
        ) : (
          <button
            type="submit"
            className="w-full rounded-lg bg-cyan-700 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-cyan-800"
          >
            Lancer l&apos;extraction
          </button>
        )}
      </form>
    </div>
  );
}
