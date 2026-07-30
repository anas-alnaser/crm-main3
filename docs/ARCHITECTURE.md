# Architecture

## Overview

Fueldezign CRM is a decoupled single-page app + REST API.

- **Backend** — Django 5 + Django REST Framework, JWT auth (SimpleJWT), Django
  admin (Unfold). SQLite for local dev, PostgreSQL for production.
- **Frontend** — React 18 + Vite + TypeScript, TanStack Query/Table, React
  Router, React Hook Form + Zod, Tailwind CSS.

```
Browser ──HTTP──> nginx (frontend container)
                     ├── / , /assets  → static SPA (React build)
                     └── /api, /admin, /static → proxy → gunicorn (backend) → PostgreSQL
```

In development the SPA runs on Vite (`:5173`) and calls the API on `:8000`
directly (CORS allow-listed).

## Backend apps

| App | Responsibility |
| --- | --- |
| `accounts` | Custom `User` (admin/sales roles), auth, user administration |
| `clients` | Companies (soft-delete/archive, ownership) |
| `projects` | Delivery projects (ownership) |
| `tasks` | Tasks (ownership) |
| `activities` | Activity log (ownership) |
| `meetings` | Meetings/schedule (owner-scoped) |
| `sales` | Pipelines, stages, deals, commission, leaderboard |
| `ai_commands` | Natural-language admin commands + confirmation/undo |
| `crm` | Settings, URLs, dashboard, health, global search, shared utilities |

## Request flow (frontend)

Component → TanStack Query hook → `src/api/client.ts` (`apiRequest`/`fetchList`)
→ adds `Authorization: Bearer <access>` from `localStorage`, auto-refreshes on
401 → DRF viewset → serializer → ORM → response → query-cache invalidation →
re-render + toast.

## Cross-cutting

- **Pagination** — page-number pagination (`{count,next,previous,page,page_size,total_pages,results}`), `page_size` capped at 200.
- **Throttling** — per-user, per-anon, login (per-IP), and AI (per-user) scopes.
- **Permissions** — role checks + object-level ownership (`created_by`/`owner`).
- **Security** — production settings enable HSTS, SSL redirect, secure cookies, nosniff, referrer-policy, X-Frame-Options.
