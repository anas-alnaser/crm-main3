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

## Pages

Beyond the core CRM pages, this build adds **My Shift** (`/my-shift`, shift-required
employees), **Leads** (`/leads`), and admin-only **Workforce** (`/workforce`),
**Audit Log** (`/audit`), and **Brand Profiles** (`/brands`). Navigation and routes
are role-gated; `AdminRoute` guards the admin pages and the server enforces the
same rules.

## Presence

`src/lib/presence.tsx` sends a throttled, content-free heartbeat (~30s, only when
genuine interaction occurred, coordinated across tabs via `BroadcastChannel`) so
the server can keep a work session alive. It records **nothing** about the
interaction — no keys, text, or coordinates. See
[../docs/WORKFORCE_POLICY.md](../docs/WORKFORCE_POLICY.md).

## Notes

- List endpoints are paginated; the app fetches through `fetchList`/`fetchPage`
  in `src/api/client.ts`. Multipart uploads use `uploadForm`; supplemental UI
  telemetry uses `sendTelemetry` (a whitelisted, best-effort call).
- The AI command bar (admin only) drives the server confirmation/undo flow; it
  never performs entity writes directly — see [../docs/AI_COMMANDS.md](../docs/AI_COMMANDS.md).
