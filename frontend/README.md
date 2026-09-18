# Ocean Research Hub — frontend

Next.js (App Router) + TypeScript + Tailwind CSS client for the FastAPI
backend in the repository root. Currently a single papers list/browse view
(`app/page.tsx`); paper detail and comparison still link out to the
backend's own server-rendered pages (`/papers/{id}`, `/papers/compare`).

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

`API_BASE_URL` in `.env.local` points at the backend (default
`http://127.0.0.1:8000`); it's a server-only env var since data fetching
happens in a Server Component, not the browser.

## Validate

```bash
npx tsc --noEmit
npm run build
```
