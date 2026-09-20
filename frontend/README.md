# Ocean Research Hub — frontend

Next.js (App Router) + TypeScript + Tailwind CSS client for the FastAPI
backend in the repository root.

Two surfaces, split by route group:

- `app/(site)` — the public landing. Dark, English, editorial; one page.
- `app/(workspace)` — the research workspace. Light, French, dense; persistent
  navigation.

Pages:

- `/` — public landing: positioning, live corpus counters, and three product
  previews (limitation aggregate, extraction walkthrough, corpus intelligence).
  Every figure on it is aggregated from the live corpus at request time by
  `app/lib/landing.ts`; when the API is unreachable each panel says so instead
  of showing a number.
- `/explore` — workspace entry: instant search (papers and domains), the 19
  domain tiles, and a carousel of papers analysed in detail
- `/domains/[id]` — one domain: its analysed papers as cards, the others
  (bibliography only) as a list, and a sidebar to switch domain
- `/papers/[id]` — every technical detail found in the paper, by section;
  click a value to see the exact sentence and page it was read from
- `/compare?a=ID&b=ID` — two analysed papers side by side, section by section

Papers are added through the backend (`uv run ocean-research-hub-seed`, see
the root README), not from the UI.

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
`http://127.0.0.1:8000`).

## Validate

```bash
npm run typecheck
npm run build
```
