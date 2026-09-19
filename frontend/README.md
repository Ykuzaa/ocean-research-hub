# Ocean Research Hub — frontend

Next.js (App Router) + TypeScript + Tailwind CSS client for the FastAPI
backend in the repository root.

Pages:

- `/` — dashboard: stats, search, one card per paper (title, authors, year,
  model family, key result)
- `/papers/[id]` — every technical detail found in the paper, by section;
  click a value to see the exact sentence and page it was read from
- `/add` — paste an arXiv link/id or a PDF URL (optional DOI) to extract a
  new paper (takes 1–3 minutes with the LLM step enabled)
- `/compare?a=ID&b=ID` — two papers side by side, section by section

Values the extractor could not verify against the PDF are simply not shown.

## Prerequisites

The FastAPI backend must be running first (from the repository root):

```bash
uv run ocean-research-hub
```

## Install and run

```bash
npm install
cp .env.local.example .env.local   # only if .env.local doesn't already exist
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

`NEXT_PUBLIC_API_BASE_URL` in `.env.local` points at the backend (default
`http://127.0.0.1:8000`). It is public because the add-paper form calls the
backend directly from the browser (the backend allows this origin via CORS).

## Validate

```bash
npm run build
```
