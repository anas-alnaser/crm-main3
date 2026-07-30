# Fueldezign CRM Frontend

React dashboard for the private Fueldezign CRM workspace.

## Setup

```bash
cd Frontend
npm install
cp .env.example .env      # VITE_API_BASE_URL (default http://localhost:8000/api)
npm run dev
```

Open `http://localhost:5173` and log in with a Django user.

## Scripts

| Script | Purpose |
| --- | --- |
| `npm run dev` | Vite dev server |
| `npm run build` | Type-check + production build |
| `npm run preview` | Preview the production build |
| `npm run typecheck` | `tsc` type-check only |
| `npm run lint` | ESLint |
| `npm run test` | Vitest (run once) |
| `npm run test:watch` | Vitest watch mode |
| `npm run test:coverage` | Vitest with coverage |
| `npm run format` / `format:check` | Prettier write / check |

## Stack

- Vite, React 18, TypeScript (strict)
- Tailwind CSS with shadcn/ui-style primitives
- TanStack Query and TanStack Table
- React Hook Form and Zod
- React Router
- Vitest + Testing Library for tests

## Notes

- List endpoints are paginated; the app fetches through `fetchList`/`fetchPage`
  in `src/api/client.ts`.
- The AI command bar (admin only) drives the server confirmation/undo flow; it
  never performs entity writes directly — see [../docs/AI_COMMANDS.md](../docs/AI_COMMANDS.md).
