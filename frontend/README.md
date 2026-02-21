# CVviewer — Frontend

Next.js frontend for the CVviewer AI job-matching agent.

## Stack

- **Framework**: Next.js 16 (App Router, TypeScript)
- **Styling**: Tailwind CSS v4
- **State**: Zustand (`src/core/store/`)
- **Linting**: ESLint (`eslint-config-next`)

## Structure

```
src/
├── app/          # Next.js App Router (pages, layouts)
└── core/
    ├── api/      # Fetch wrappers for backend REST endpoints
    ├── store/    # Zustand state stores
    └── types/    # Shared TypeScript types
```

> `core/` is a strict business-logic boundary. Components in `app/` import from `core/`, never the reverse.

## Dev Commands

```bash
npm run dev       # Start dev server at http://localhost:3000
npm run build     # Production build
npm run lint      # ESLint
npm run format    # Prettier (auto-fix)
npm run type-check # TypeScript compiler check
npm run test      # Vitest run
```

> The dev server proxies all `/api/*` requests to the FastAPI backend on `http://localhost:8000` via `next.config.ts` rewrites. Both servers must be running concurrently.
