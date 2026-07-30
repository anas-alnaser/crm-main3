# Fueldezign CRM — Read-Only Technical Audit

**Audit date:** 2026-07-31
**Repository:** `crm-morph-fuel/crm-main` (branch `main`, single commit `8982cc7`)
**Scope:** Complete, read-only audit. No files were modified. Conclusions are traced to code with `path:line` evidence.

**Evidence legend:** **Fact** = directly verified in code. **Likely** = strongly implied but not runtime-verified. **Unverified** = could not be confirmed in this environment (no Django/Node dependencies installed; see Phase 6).

---

## 1. Executive summary

Fueldezign CRM is a **private, internal sales/agency CRM** consisting of a Django REST Framework backend and a React/Vite/TypeScript frontend. It is a **single-tenant, invite-only tool** (no public registration; users are created by admins) that manages companies, projects, tasks, activities, meetings, and a drag-and-drop sales pipeline with deals, commissions, and a leaderboard. It also includes an **admin-only natural-language "AI command" bar** backed by the Anthropic API.

**Overall maturity: Functional MVP / internal beta.** The core CRUD product is broad, coherent, and genuinely wired end-to-end (UI → API client → DRF viewset → DB → cache refresh). The code compiles (Python `compileall` passes) and the architecture is consistent. However, it is **not production-ready** and has notable gaps:

- **Zero automated tests** anywhere (backend or frontend). **Fact.**
- The **AI "confirmation-required" safety tier is not actually enforced** on the server — confident commands in every non-blocked tier execute immediately; the confirmation code path is dead code and the confirm endpoint returns `410 GONE`. **Fact.**
- The **AI frontend is badly out of sync** with the backend: only 2 of ~14 actionable intents have review UI, blocked/refused commands produce **no user feedback**, and the **undo** capability (which exists in the backend) has **no UI at all**. **Fact.**
- **No object-level ownership** on companies, projects, tasks, or activities — any authenticated user (including `sales`) has full create/edit/**delete** on all of them. **Fact.**
- **Not production-hardened:** insecure default `SECRET_KEY`, `DEBUG=True` default, no throttling/rate-limiting, no pagination, no production server/Docker for the app, JWT in `localStorage`, and the required `ANTHROPIC_API_KEY` is undocumented in `.env.example`. **Fact.**

**What a user can realistically do today:** Log in; manage companies/projects/tasks/activities/meetings; run a full sales pipeline with drag-and-drop deal movement, commissions, dashboard metrics, and a leaderboard; admins can manage users and commission rate and issue confident AI commands. These flows work.

**Largest blockers to production:** (1) no tests, (2) AI confirmation/undo/feedback gaps and the un-enforced confirmation tier, (3) authorization model is coarse (no ownership on core entities), (4) security/deploy hardening, (5) cascade-delete data-loss risk on companies.

---

## 2. Repository and architecture overview

**Repository type:** Monorepo with two apps: `Backend/` (Django) and `Frontend/` (Vite React). 137 tracked files. `repomix-output.xml` at root is an untracked generated artifact.

**Stack (Fact, from manifests):**
- **Backend** — `Backend/requirements.txt`: Django 5.x, Django REST Framework 3.15, `djangorestframework-simplejwt` 5.3 (JWT), `django-cors-headers`, `django-filter`, `django-unfold` (admin theme), `psycopg[binary]` 3 (PostgreSQL), `certifi`.
- **Frontend** — `Frontend/package.json`: React 18, Vite 5, TypeScript 5.6 (`strict: true`), TanStack Query 5, TanStack Table 8, React Router 6, React Hook Form 7 + Zod 3, `@dnd-kit/core` (drag-drop), `framer-motion`, `lucide-react`, Tailwind 3 + `class-variance-authority`/`tailwind-merge`.

**Architecture:** Classic decoupled SPA + REST API. Django serves the JSON API under `/api/` and the admin under `/admin/` (+ `/django-admin/`). Frontend is a client-side-routed SPA calling the API with a bearer JWT.

**Runtime components / entry points (Fact):**
- Backend WSGI: `Backend/crm/wsgi.py`; ASGI: `Backend/crm/asgi.py`; management: `Backend/manage.py`. URL root: `Backend/crm/urls.py`.
- Frontend entry: `Frontend/index.html` → `Frontend/src/main.tsx` → `App.tsx`. Providers wired in `main.tsx:14-28`: `QueryClientProvider` → `BrowserRouter` → `ThemeProvider` → `ToastProvider` → `AuthProvider`.

**Data flow (Fact):** Component → TanStack Query hook (`useCrud.ts` or inline `useQuery`/`useMutation`) → `src/api/client.ts` `apiRequest()` (adds `Authorization: Bearer <accessToken>` from `localStorage`, auto-refreshes on 401) → DRF router/view → serializer → ORM → SQLite/Postgres → response → query cache invalidation → re-render + toast.

**Database options (Fact, `settings.py:85-102`):** PostgreSQL when `POSTGRES_DB` is set, otherwise SQLite fallback (`db.sqlite3`). `docker-compose.yml` provides a Postgres 16 container (db/user/password all `crm`) — **for the DB only; there is no Dockerfile for the Django app or the frontend.**

**Authentication (Fact):** SimpleJWT. Access token 30 min, refresh 7 days (`settings.py:144-147`). No token rotation/blacklist configured. Default DRF permission `IsAuthenticated` (`settings.py:130-142`). Custom `AUTH_USER_MODEL = accounts.User` with a `role` field (`admin`/`sales`).

**API structure (Fact):** DRF `DefaultRouter` for 9 resources + explicit paths for auth, dashboard, commission, leaderboard, and AI. See §7.

**State management (Fact):** Server state via TanStack Query; auth/theme/toast via React Context. No Redux/Zustand.

**Styling/UI (Fact):** Tailwind CSS with hand-rolled shadcn-style primitives in `src/components/ui/*`. Dark/light theme via a `.dark` class on `<html>` (`lib/theme.tsx`).

**External services (Fact):** Anthropic Messages API (`ai_commands/services.py:12-13`, model `claude-haiku-4-5-20251001`, `api.anthropic.com/v1/messages`). No other third-party runtime services.

**Required environment variables (Fact):**
- Backend (`Backend/.env.example`): `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `POSTGRES_DB/USER/PASSWORD/HOST/PORT`.
- Backend, **missing from `.env.example`**: `ANTHROPIC_API_KEY` (required for the AI feature; read at `services.py:144`). **This is an undocumented required variable.**
- Frontend (`Frontend/.env.example`): `VITE_API_BASE_URL`.

**Missing/expected files:** No CI/CD (no `.github/`, no pipelines). No app Dockerfiles. No test files. No `pytest.ini`/`tox.ini`. No linter/formatter config (no `.eslintrc`, `ruff.toml`, `.prettierrc`). No `LICENSE`. `.env` files are correctly gitignored and not committed (**Fact**).

---

## 3. Current implementation status (evidence-based estimates)

Percentages are **subjective estimates** based on "coherent, wired, and functional" vs "missing/broken/untested", not a metric.

| Area | Estimate | Basis |
| --- | --- | --- |
| Backend (CRUD/domain) | ~85% | All 9 domains modeled, serialized, routed, admin-registered; compiles clean. Gaps: coarse authz, no tests, unhandled delete-of-referenced-user. |
| Frontend (CRUD/pages) | ~85% | 12 pages, all wired to API, loading/empty/error/success states present, responsive, themed. Gaps: AI UI, no user-delete/reactivate. |
| Backend/Frontend integration | ~80% | Core flows fully connected. AI + undo + some field-refresh paths are the weak spots. |
| Authentication | ~90% | Login, refresh, me, logout, protected/admin routes all work. Gaps: localStorage storage, no rotation, no throttling. |
| Authorization | ~55% | Deals & meetings have object ownership; **companies/projects/tasks/activities have none**; admin gating works. |
| Business functionality (sales) | ~85% | Pipeline, deals, stages, commission, leaderboard, dashboard all implemented and consistent. |
| AI functionality | ~45% | Interpretation + auto/blocked tiers work; confirmation tier not enforced; undo & most review UI absent; config-dependent. |
| Testing | ~0% | No tests of any kind. **Fact.** |
| Security hardening | ~30% | Sensible defaults for CORS/JWT auth, but no prod hardening, throttling, or secret discipline. |
| Deployment readiness | ~20% | DB compose only; no app container, no server config, no CI, no docs for prod. |

---

## 4. Implemented feature catalog (verified)

Each item below was traced in code.

**Authentication & session**
- JWT login via `username`/`password` (`urls.py:30,32`; `LoginPage.tsx`; `lib/auth.tsx:39-45`).
- Access/refresh token storage in `localStorage`, automatic refresh on 401 (`api/client.ts:9-41`).
- Current-user retrieval `GET /api/auth/me/` (`accounts/views.py:11-15`).
- Logout clears tokens and user state (`lib/auth.tsx:46-50`).
- Route protection: `ProtectedRoute` (auth gate) and `AdminRoute` (role gate) (`components/ProtectedRoute.tsx`, `AdminRoute.tsx`, `App.tsx:23-37`).

**User management (admin-only)**
- List/create users, change role, deactivate (`accounts/views.py:18-30`; `UsersPage.tsx`). Create requires `temp_password`≥8 and `role` (`accounts/serializers.py:32-42`).
- Admin role sync to `is_staff` on create/update (`serializers.py:48-53,60-65`).

**Companies (clients)** — full CRUD, filter/search/sort (`clients/views.py`; `ClientsPage.tsx`).
**Projects** — full CRUD, typed status/type, budget/dates (`projects/*`; `ProjectsPage.tsx`).
**Tasks** — full CRUD, links to client/deal/project, calendar-by-due-date view (`tasks/*`; `TasksPage.tsx`).
**Activities** — full CRUD (call/meeting/email/note), links to client/deal/project (`activities/*`; `ActivitiesPage.tsx`).
**Meetings/Schedule** — full CRUD + `upcoming` endpoint, week/agenda views, status transitions, owner scoping, deal→meeting prefill (`meetings/*`; `SchedulePage.tsx`, `OverviewPage.tsx`).

**Sales pipeline**
- Pipelines & Stages (won/lost flags, order); a **default pipeline + 6 stages is seeded by data migration** (`sales/migrations/0001_initial.py:6-24`). **Fact.**
- Deals with company/owner/pipeline/stage/value/currency (default `JOD`)/expected-close/notes; status auto-derived from stage (`sales/models.py:57-65`).
- Drag-and-drop stage movement with optimistic updates (`PipelinePage.tsx:377-427`) and a dedicated `move` action (`sales/views.py:75-90`).
- Deal ownership enforcement + monetary masking for non-owner sales (`accounts/permissions.py:16-27`; `sales/serializers.py:39-54`).
- Commission (flat % from `SalesSettings`) — earned/potential, personal vs company scope (`sales/views.py:93-120`; `OverviewPage.tsx`, `SettingsPage.tsx`).
- Leaderboard with rank, this-month/all-time, per-rep masking for non-admins (`sales/views.py:123-196`; `LeaderboardPage.tsx`).
- Dashboard stats: open deals, pipeline value, won-this-month, win rate, value-by-stage (`crm/views.py`; `OverviewPage.tsx`).

**Cross-cutting**
- Global workspace search across clients/deals/tasks/meetings/activities via `?search=` (`DashboardLayout.tsx:225-242`).
- Theme toggle (dark/light, persisted) (`lib/theme.tsx`).
- Toast notifications (`lib/toast.tsx`).
- Loading skeletons, empty states, error states across pages (**Fact**, present in every page).
- Responsive sidebar/mobile nav (`DashboardLayout.tsx`).

**AI command (admin-only)** — see §10 for full detail.

---

## 5. Feature status matrix

Status vocabulary as requested. "Connected E2E" = full UI→API→DB→refresh chain verified.

| Area | Feature | Backend | Frontend | Connected E2E | Tests | Status | Evidence | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Auth | Login (JWT) | Yes | Yes | Yes | No | Fully implemented | `urls.py:30`, `auth.tsx:39` | — |
| Auth | Token refresh | Yes | Yes | Yes | No | Fully implemented | `client.ts:19-41` | localStorage |
| Auth | Current user | Yes | Yes | Yes | No | Fully implemented | `accounts/views.py:11` | — |
| Auth | Logout | n/a | Yes | Yes | No | Fully implemented | `auth.tsx:46` | client-side only |
| Auth | Role-based nav/routes | Yes | Yes | Yes | No | Fully implemented | `AdminRoute.tsx`, `DashboardLayout.tsx:65` | client gate + server gate |
| Users | List/create/role/deactivate | Yes | Yes | Yes | No | Fully implemented | `accounts/views.py:18-30`, `UsersPage.tsx` | admin-only |
| Users | Delete user | Yes (route) | No UI | No | No | Backend only | ModelViewSet DELETE | can 500 if user owns deals (PROTECT) |
| Users | Reactivate user | No | No | No | No | Not implemented | — | only deactivate exists |
| Companies | CRUD | Yes | Yes | Yes | No | Fully implemented | `clients/*`, `ClientsPage.tsx` | no ownership; cascade-delete risk |
| Projects | CRUD | Yes | Yes | Yes | No | Fully implemented | `projects/*`, `ProjectsPage.tsx` | no ownership |
| Tasks | CRUD + calendar | Yes | Yes | Yes | No | Fully implemented | `tasks/*`, `TasksPage.tsx` | no ownership |
| Activities | CRUD | Yes | Yes | Yes | No | Fully implemented | `activities/*`, `ActivitiesPage.tsx` | no ownership |
| Meetings | CRUD + upcoming + status | Yes | Yes | Yes | No | Fully implemented | `meetings/*`, `SchedulePage.tsx` | owner-scoped |
| Sales | Pipelines/stages (read) | Yes | Yes | Yes | No | Fully implemented | `sales/views.py:36-53`, `SettingsPage.tsx` | seed migration |
| Sales | Pipeline/stage create/edit | Yes | No UI | No | No | Backend only | `IsAdminOrReadOnly` | admin/API/Django-admin only |
| Sales | Deal CRUD | Yes | Yes | Yes | No | Fully implemented | `sales/views.py:56-73`, `DealsPage.tsx` | — |
| Sales | Drag-drop move | Yes | Yes | Yes | No | Fully implemented | `sales/views.py:75-90`, `PipelinePage.tsx:377` | optimistic |
| Sales | Deal ownership/masking | Yes | Yes | Yes | No | Fully implemented | `permissions.py:16`, `serializers.py:48` | value masked for non-owners |
| Sales | Commission calc | Yes | Yes | Yes | No | Fully implemented | `sales/views.py:93`, `OverviewPage.tsx` | flat % |
| Sales | Leaderboard | Yes | Yes | Yes | No | Fully implemented | `sales/views.py:123`, `LeaderboardPage.tsx` | — |
| Sales | Commission rate settings | Yes | Yes | Yes | No | Fully implemented | `sales/views.py:113`, `SettingsPage.tsx` | admin-only |
| Dashboard | Stats overview | Yes | Yes | Yes | No | Fully implemented | `crm/views.py`, `OverviewPage.tsx` | scope by role |
| Search | Global search | Yes (per-resource) | Yes | Yes | No | Fully implemented | `DashboardLayout.tsx:225` | client-side fan-out |
| List | Filter/sort | Yes | Partial | Partial | No | Partially implemented | viewsets `filterset_fields` | many filters client-side only |
| List | Pagination | No | Table-only | No | No | Partially implemented | no DRF pagination; `DealsPage` paginates client-side | see risk R-08 |
| AI | Interpret command | Yes | Yes | Yes | No | Configuration-dependent | `services.py`, `AICommandBar.tsx` | needs `ANTHROPIC_API_KEY` |
| AI | Auto-execute (tier 1) | Yes | Partial | Partial | No | Partially implemented | `views.py:716-726` | success toast only; no list refresh for most |
| AI | Confirmation (tier 2) | **Not enforced** | Mislabeled | No | No | Broken | `views.py:349,726`; confirm=`410` | executes immediately; see R-01 |
| AI | Blocked (tier 3) | Yes | **No feedback** | No | No | Partially implemented | `views.py:721-722`; `AICommandBar.tsx:59-67` | refusal never shown to user |
| AI | Disambiguation UI | Yes | 2 intents only | Partial | No | Partially implemented | `AICommandBar.tsx:166-174` | only move_deal/create_meeting |
| AI | Undo | Yes | **No UI** | No | No | Backend only | `views.py:755-807`; no FE caller | R-02 |
| AI | Command logging | Yes | n/a (admin) | Yes | No | Fully implemented | `views.py:728-742`, `ai_commands/admin.py` | viewable in Django admin |
| Infra | Theme toggle | n/a | Yes | Yes | No | Fully implemented | `lib/theme.tsx` | — |
| Infra | Toasts | n/a | Yes | Yes | No | Fully implemented | `lib/toast.tsx` | — |
| Infra | PostgreSQL support | Yes | n/a | Yes | No | Configuration-dependent | `settings.py:85`, `docker-compose.yml` | DB container only |
| Quality | Automated tests | No | No | — | — | Not implemented | no test files | **Fact** |
| Ops | CI/CD | No | No | — | — | Not implemented | no workflows | — |

---

## 6. Page and route inventory

All routes from `Frontend/src/App.tsx`. All pages verified wired to the API.

| Route | Page | Purpose | Role | API dependencies | Main actions | Status | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `/login` | LoginPage | Auth | Public | `/auth/token/`, `/auth/me/` | Login | Working | `LoginPage.tsx` |
| `/` | PipelinePage | Kanban board | admin+sales | `/stages/`, `/deals/`, `/clients/`, `/users/`(admin), `/tasks/`, `/activities/`, `/meetings/`, `/deals/{id}/move/` | Create/edit deal, drag-move, log activity, view meetings/tasks | Working | `PipelinePage.tsx` |
| `/overview` | OverviewPage | Dashboard | admin+sales | `/dashboard/stats/`, `/deals/`, `/activities/`, `/commission/`, `/meetings/upcoming/` | View metrics | Working | `OverviewPage.tsx` |
| `/deals` | DealsPage | Deal table | admin+sales | `/deals/`, `/clients/`, `/stages/`, `/users/`(admin) | Search/sort/filter, CRUD, delete | Working | `DealsPage.tsx` |
| `/clients` | ClientsPage | Companies | admin+sales | `/clients/` | CRUD | Working | `ClientsPage.tsx` |
| `/projects` | ProjectsPage | Projects | admin+sales | `/projects/`, `/clients/` | CRUD | Working | `ProjectsPage.tsx` |
| `/tasks` | TasksPage | Tasks + calendar | admin+sales | `/tasks/`, `/clients/`, `/projects/`, `/deals/` | CRUD, calendar filter | Working | `TasksPage.tsx` |
| `/schedule` | SchedulePage | Meetings calendar | admin+sales | `/meetings/`, `/clients/`, `/deals/`, `/users/`(admin) | CRUD, status change, scope | Working | `SchedulePage.tsx` |
| `/activities` | ActivitiesPage | Activity log | admin+sales | `/activities/`, `/clients/`, `/projects/`, `/deals/` | CRUD | Working | `ActivitiesPage.tsx` |
| `/leaderboard` | LeaderboardPage | Sales ranking | admin+sales | `/leaderboard/` | Period toggle | Working | `LeaderboardPage.tsx` |
| `/users` | UsersPage | User admin | **admin** | `/users/`, `/users/{id}/deactivate/` | Create, role, deactivate | Working | `UsersPage.tsx` |
| `/settings` | SettingsPage | Config | **admin** | `/commission/`, `/pipelines/`, `/stages/` | Set commission rate; view pipelines/stages | Working | `SettingsPage.tsx` |
| `*` | → `/` | Fallback | any | — | Redirect | Working | `App.tsx:40` |

Additional non-page UI: the **AI command bar** (`AICommandBar.tsx`) is rendered inside `DashboardLayout` **only for admins** (`DashboardLayout.tsx:208`).

**No broken imports, undefined routes, dead nav links, or unrouted pages were found.** Every `ui/*` primitive imported (`badge, button, empty-state, input, motion, select, skeleton, table, textarea`) exists. Every page in `App.tsx` exists. **Fact.**

---

## 7. API inventory

Traced from `Backend/crm/urls.py` and each viewset. "Auth" = required to be authenticated; "Authz" = additional role/ownership rule.

| Method | Endpoint | Purpose | Auth | Authz | Impl status | Frontend usage | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| POST | `/api/auth/token/`, `/api/auth/login/` | Obtain JWT | Public | — | Complete | LoginPage | `urls.py:30,32` |
| POST | `/api/auth/token/refresh/`, `/api/auth/refresh/` | Refresh JWT | Public | — | Complete | api client auto | `urls.py:31,33` |
| GET | `/api/auth/me/` | Current user | Yes | — | Complete | AuthProvider | `accounts/views.py:11` |
| GET/POST | `/api/users/` | List/create users | Yes | **admin** | Complete | UsersPage | `accounts/views.py:18-21` |
| GET/PUT/PATCH/DELETE | `/api/users/{id}/` | Retrieve/update/**delete** user | Yes | **admin** | Complete (delete unguarded) | patch role only | ModelViewSet |
| PATCH | `/api/users/{id}/deactivate/` | Deactivate | Yes | **admin** | Complete | UsersPage | `accounts/views.py:25-30` |
| CRUD | `/api/clients/` `/{id}/` | Companies | Yes | **none (any user, incl. delete)** | Complete | ClientsPage | `clients/views.py:7` |
| CRUD | `/api/projects/` `/{id}/` | Projects | Yes | **none** | Complete | ProjectsPage | `projects/views.py:7` |
| CRUD | `/api/pipelines/` `/{id}/` | Pipelines | Yes | admin-write / read-all | Complete | SettingsPage (read) | `sales/views.py:36-43` |
| CRUD | `/api/stages/` `/{id}/` | Stages | Yes | admin-write / read-all | Complete | Settings/Pipeline (read) | `sales/views.py:46-53` |
| CRUD | `/api/deals/` `/{id}/` | Deals | Yes | owner or admin to write; all can read (value masked) | Complete | DealsPage, PipelinePage | `sales/views.py:56-73` |
| PATCH | `/api/deals/{id}/move/` | Move deal stage | Yes | owner or admin | Complete | Pipeline drag, AI drawer | `sales/views.py:75-90` |
| CRUD | `/api/tasks/` `/{id}/` | Tasks | Yes | **none** | Complete | TasksPage | `tasks/views.py:7` |
| CRUD | `/api/activities/` `/{id}/` | Activities | Yes | **none** | Complete | ActivitiesPage, Pipeline | `activities/views.py:7` |
| CRUD | `/api/meetings/` `/{id}/` | Meetings | Yes | owner or admin | Complete | SchedulePage | `meetings/views.py:23` |
| GET | `/api/meetings/upcoming/` | Next 7 days | Yes | owner-scoped | Complete | OverviewPage | `meetings/views.py:59-69` |
| GET | `/api/dashboard/stats/` | Metrics | Yes | scope by role | Complete | OverviewPage | `crm/views.py:12` |
| GET | `/api/commission/` | Commission summary | Yes | scope by role | Complete | Overview, Settings | `sales/views.py:96` |
| PATCH | `/api/commission/` | Set rate | Yes | **admin** (checked in body) | Complete | SettingsPage | `sales/views.py:113-120` |
| GET | `/api/leaderboard/` | Ranking | Yes | mask non-admins | Complete | LeaderboardPage | `sales/views.py:126` |
| POST | `/api/ai/command/` | Interpret+act | Yes | **admin** | Complete (see caveats) | AICommandBar | `ai_commands/views.py:690` |
| POST | `/api/ai/command/confirm/` | (deprecated) | Yes | **admin** | **Always `410 GONE`** | Not used | `ai_commands/views.py:745-752` |
| POST | `/api/ai/command/undo/` | Undo AI action | Yes | **admin** | Complete | **No frontend caller** | `ai_commands/views.py:755` |
| — | `/admin/`, `/django-admin/` | Django admin (unfold) | session | staff | Complete | external | `urls.py:28-29` |

**Route/view coherence:** No routes point to missing views; no views lack routes (all viewsets registered on the router; all `APIView`s pathed). **Fact.** Note `/admin/` and `/django-admin/` both map to the same `admin.site.urls` (harmless duplication).

---

## 8. User roles and permissions

Two roles: `admin` and `sales` (`accounts/models.py:6-10`). `is_admin_role` is true when `role == admin` **or** `is_superuser` **or** `is_staff` (`accounts/models.py:12-14`). **Fact.**

**Admin can:**
- Full CRUD on users; change roles; deactivate; **hard-delete users** (route exists, no UI).
- Read/write everything: all deals (values visible), all meetings, commission rate, pipelines/stages (via API/Django admin).
- See company-scoped dashboard, full leaderboard (all reps' figures), personal+company commission.
- Use the AI command bar (admin-only).

**Sales can:**
- Full CRUD on **companies, projects, tasks, activities** — with **no ownership restriction** (any sales user can edit/delete any of these records). **Fact — this is broader than typical role design.**
- Create deals (owner forced to self on create, `sales/views.py:71-73`); edit/move/delete **only their own** deals (`permissions.py:22-27`).
- **Read all deals**, but `value` and `commission` are masked to `null` for deals they don't own (`serializers.py:48-54`). Other fields (title, company, contact, notes, owner, dates) remain visible.
- Manage **only their own** meetings (`meetings/views.py:17-20,32-46`).
- See personal-scoped dashboard/commission; see own leaderboard row fully, others masked (`sales/views.py:174-186`).
- **Cannot** access `/users`, `/settings`, user APIs, pipeline/stage writes, commission PATCH, or the AI bar.

**Object-level permission summary:**
- Enforced: Deals (`DealPermission`), Meetings (`MeetingPermission`).
- **Not enforced (gap):** Clients, Projects, Tasks, Activities — default `IsAuthenticated` only, so **any authenticated user has full CRUD including delete**.

**Confirm/administer:** Only admins administer users, commission, pipelines. There is **no per-object confirmation** for destructive actions beyond a browser `window.confirm()` on the client (`EntityTable.tsx:33`, `DealsPage.tsx:253`, `SchedulePage.tsx:240`).

---

## 9. Main user workflows (end-to-end status)

For brevity, "connected" means the full UI→API→DB→refresh chain was verified in code.

1. **Startup** — `main.tsx` mounts providers; `AuthProvider` reads `accessToken` and calls `/auth/me/` (`auth.tsx:19-33`). **Connected.**
2. **Login** — `LoginPage`→`auth.login`→`/auth/token/`, stores tokens, fetches `/auth/me/`, navigates `/` (`auth.tsx:39-45`). **Connected.** Error path: invalid creds → "Invalid username or password" (`LoginPage.tsx:35`).
3. **Token storage** — `localStorage` (`auth.tsx:41-42`). **Connected.** Risk: XSS-exposed (R-11).
4. **Authenticated requests** — bearer header injected (`client.ts:12-16`). **Connected.**
5. **Token refresh** — on 401, POST `/auth/token/refresh/`, retry once (`client.ts:19-41`). **Connected.** If refresh fails, original 401 error propagates; `AuthProvider` clears tokens on `/auth/me/` failure but other pages just show error states.
6. **Logout** — clears tokens + user (`auth.tsx:46-50`). **Connected.**
7. **Role-based navigation** — nav items and AI bar gated by `user.role` (`DashboardLayout.tsx:65,208`); `AdminRoute` guards `/users`,`/settings`. **Connected** (server also enforces).
8–10. **Create/edit/deactivate user** — `UsersPage` → `/users/`, `patch role`, `/deactivate/`. **Connected.** No delete/reactivate UI.
11. **Create/edit company** — `ClientsPage` via `useCrud`. **Connected.** Delete cascades to deals/projects (R-05).
12. **Create/edit project** — `ProjectsPage`. **Connected.**
13. **Create/update task** — `TasksPage` (+ calendar). **Connected.**
14. **Log activity** — `ActivitiesPage` and inline in deal drawer (`PipelinePage.tsx:398-411`). **Connected.**
15. **Create meeting** — `SchedulePage` (+ deal prefill via `?deal=`). **Connected.**
16. **Create deal** — `DealsPage`/`PipelinePage`. **Connected.**
17. **Move deal between stages** — drag-drop → `/deals/{id}/move/`, optimistic update + rollback on error (`PipelinePage.tsx:377-396`). **Connected.**
18. **Update deal** — `updateEntity('deals')`. **Connected.** Note: PUT allows changing `owner` on an owned deal (no `perform_update` guard) — minor (R-07).
19. **Dashboard load** — `/dashboard/stats/` + supporting queries. **Connected.**
20. **Leaderboard** — `/leaderboard/?period=`. **Connected.** Ranking sorts by potential, then earned, then won count (`sales/views.py:164`).
21. **Settings change** — commission PATCH (admin). **Connected.**
22–26. **AI submission/interpretation/confirmation/execution/undo** — see §10. Interpretation + auto-execution **connected but partial**; confirmation **not enforced**; undo **not wired to any UI**.

---

## 10. AI command functionality

**Provider/model (Fact):** Anthropic Messages API, model `claude-haiku-4-5-20251001`, `temperature=0`, `max_tokens=500`, called via `urllib` with `certifi` TLS (`ai_commands/services.py:12-13,143-176`). Requires `ANTHROPIC_API_KEY` (`services.py:144`), which is **absent from `.env.example`** and undocumented.

**Access:** All three AI endpoints require `IsAdminRole` (`views.py:691,746,756`); the bar renders only for admins. **Fact.**

**Flow (Fact):** `AICommandView.post` → `interpret_command` builds a JSON-only prompt with today's date and the allowed-intent taxonomy (`services.py:90-140`), calls Anthropic, parses/normalizes the draft (`services.py:69-87`), then `evaluate_draft` (`views.py:716-726`):
- Unknown intent → `build_unknown_response` (refusal).
- Blocked intent → `build_blocked_response` (refusal).
- `confidence < 0.75` → review response (`views.py:724-725`).
- Otherwise → `AICommandExecutor(user).execute(draft)` — **executes immediately**.

**Supported intents (`views.py:29-59`):**
- **Tier 1 (auto):** `create_meeting, create_task, log_activity, move_deal, create_deal, create_company, add_note, schedule_followup`.
- **Tier 2 (labeled "confirmation required"):** `update_deal_value, update_deal_close_date, reassign_deal_owner, edit_company_details, edit_meeting, update_task`.
- **Tier 3 (blocked):** `delete_*`, `change_commission_rate`, `change_user_role`, `create_user`, `deactivate_user`, `bulk_operation`.

**Automatically executed actions:** All Tier-1 **and Tier-2** intents that resolve with confidence ≥ 0.75. **Fact.** The executor has a `preview(draft)` (`views.py:349-350`) and every Tier-2 handler contains an `if not execute:` confirmation branch — but **`preview()` is never called and `evaluate_draft` always calls `execute()`** (`views.py:726`). So the confirmation branches are **dead code** and Tier-2 edits (including deal value, close date, and owner reassignment) apply immediately without confirmation. **This is the single most important AI finding (R-01).**

**Confirmation-required actions:** Intended for Tier 2, but **not enforced** server-side. The dedicated confirm endpoint `POST /api/ai/command/confirm/` unconditionally returns **`410 GONE`** (`views.py:745-752`). The frontend's "Confirmation required" drawer does **not** call any AI-confirm endpoint; it re-implements two actions directly (`/deals/{id}/move/` and `createEntity('meetings')`) — `AICommandBar.tsx:200-213, 262-280`.

**Blocked actions:** Returned with `blocked: true` and a `refusal` string (`views.py:285-304`), and logged with outcome `blocked`. **But the frontend never surfaces them:** `onSuccess` only reacts to `response.acted` or `response.draft`; blocked/unknown responses carry neither, so the user gets **no feedback at all** (`AICommandBar.tsx:59-67`). **Fact (R-03).**

**Missing-information & ambiguity handling:** Backend resolvers (`views.py:109-204`) detect missing/ambiguous entities and return a review response with a `missing` list and disambiguation `options`. **But the frontend review UI only implements `move_deal` and `create_meeting`** (`AICommandBar.tsx:166-174`); any other intent that needs review shows "I could not identify a supported action." So ambiguous `create_deal`/`create_company`/`update_*` etc. are **not resolvable from the UI**. **Fact.**

**Logging:** Every command is logged to `AICommandLog` with user, raw text, resolved intent, tier, outcome, summary, draft, action_data, and undo timestamp (`ai_commands/models.py`, `views.py:728-742`), viewable read-only in Django admin (`ai_commands/admin.py`). **Fact.** This is the most complete part of the AI feature.

**Undo:** Backend `POST /api/ai/command/undo/` reverses `create` (delete) and `update` (restore old field values) actions for the requesting user's own logged action (`views.py:755-807`). Executed actions return `action_id`/`undoable` in the response. **No frontend code calls this endpoint or renders an undo affordance** — verified by search (only `/ai/command/` appears in the frontend). **Backend-only (R-02).**

**Required env config:** `ANTHROPIC_API_KEY`. If absent, the endpoint returns `503` with "AI command service is not configured" (`views.py:701-704`). **Config-dependent.**

**Failure handling:** Provider/parse errors → `502` "Could not interpret command" with the raw error string in `error` (`views.py:705-708`) — this **leaks the internal exception text** to the client (R-10, low). All failures are logged.

**Security boundaries:** Admin-only; destructive/system intents are blocked at the taxonomy level; interpretation is constrained to a fixed intent list (unknown intents refused). Weaknesses: no rate-limiting/cost guard on the endpoint; masked-value bypass is not a concern since AI is admin-only; the un-enforced confirmation tier weakens the intended "human-in-the-loop" guarantee for edits.

---

## 11. Validation results

Environment: Python 3.12.3, Node 24.13.1, npm 11.8.0. **No backend virtualenv, no `Frontend/node_modules`, Django not importable.** Per audit rules, no dependencies were installed.

| Command | Result | Verdict | Notes |
| --- | --- | --- | --- |
| `python -m compileall -q Backend` | Exit 0, no output | **Pass** | All backend `.py` (incl. migrations) compile. **Code-clean.** |
| `python -c "import django"` | ImportError | **Blocked (env)** | Django not installed; not a code defect. |
| `python manage.py check` | Not run | **Unavailable** | Requires Django install (prohibited). Model/URL coherence checked by reading. |
| `python manage.py makemigrations --check` | Not run | **Unavailable** | Migration/model drift **unverified**; single initial migrations per app suggest consistency but not confirmed. |
| `tsc -b` / `npm run build` | Not run | **Blocked (env)** | No `node_modules`; install prohibited. `strict: true` in `tsconfig.json`. Types **unverified** by compiler but read as consistent. |
| Backend test discovery | No test files found | **Pass (absence confirmed)** | `find` for `test*.py`/`tests.py`/`conftest.py`/`pytest.ini` → none. |
| Frontend test discovery | No test files/config | **Pass (absence confirmed)** | No test runner in `package.json`. |
| Secret scan (`grep` api_key/secret/password/token) | Only env reads + JWT config | **Pass** | No hardcoded credentials; `SECRET_KEY` has insecure **default**, from env otherwise. |
| TODO/FIXME/mock/placeholder scan | Only `placeholder=` HTML attrs and status enums | **Pass** | No `TODO`/`FIXME`/`HACK`/mock-data markers in `src/`. |
| Tracked `.env` scan | Only `.env.example` files | **Pass** | No real secrets committed. |
| `git status`/log | 1 commit, clean tree + untracked `repomix-output.xml` | Info | No history to mine. |

**Interpretation:** No failures attributable to the code were found in the checks that could run. The checks marked *Unavailable/Blocked* are due to the sandbox lacking dependencies, not code defects — but they mean **type-checking, Django system checks, and migration-drift checks remain unverified** and should be run in a real environment before relying on them.

---

## 12. Missing, incomplete, or disconnected functionality

**Missing entirely**
- Automated tests (backend + frontend).
- CI/CD; app Dockerfiles; production server config; deployment docs.
- User **reactivate** and user-delete UI; last-admin / self-deactivation protection.
- Pagination (server-side) and server-driven filtering UI wiring for most lists.
- Rate-limiting / throttling / brute-force protection; audit logging beyond AI.
- Password-change / reset flow for users (temp password only).

**Backend only (no UI)**
- AI **undo** (`/ai/command/undo/`).
- Pipeline/stage **create/edit/delete** APIs (managed via Django admin only).
- User **delete** endpoint.

**Frontend only / client-side only**
- Deal list filtering (stage/owner/status/search) and pagination are computed client-side over the full dataset (`DealsPage.tsx:171-222`) rather than via the API's filter params.
- Logout is purely client-side (no server token invalidation — acceptable for stateless JWT but worth noting).

**Partially implemented**
- AI command bar: auto-execute works headlessly (toast only) but does **not refresh** most lists after non-`move_deal`/`create_meeting` intents (`AICommandBar.tsx:74-82`); review UI covers only 2 intents; blocked responses give no feedback.
- Global search fans out 5 requests and slices client-side (`DashboardLayout.tsx:225-242`) — works but not scalable.

**Present but unverified**
- TypeScript type-safety (no `tsc` run), Django system checks, migration/model consistency (no Django), Anthropic integration (no key/network in audit).

**Configuration-dependent**
- AI feature (needs `ANTHROPIC_API_KEY`); PostgreSQL (needs `POSTGRES_DB` + running container).

**Broken or inconsistent**
- AI Tier-2 "confirmation required" is not enforced (dead confirmation code; confirm endpoint `410`).
- Frontend `AICommandResponse`/`AICommandIntent` types (`api/types.ts:167-185`) are narrower than the backend contract (missing `blocked`, `refusal`, `needs_review`, `requires_disambiguation`, `undoable`, `action_id`, `options`, `preview`, `tier`), which is why blocked/undo/most-intents aren't handled.

---

## 13. Defects and risks (ordered by severity)

> Severities reflect this being a **private internal tool**, not a public app. No fixes were applied.

**R-01 — High — AI "confirmation-required" tier is not enforced (immediate execution of edits)**
Evidence: `ai_commands/views.py:726` always calls `.execute()`; `preview()` at `:349` is never called; Tier-2 handlers' `if not execute:` confirmation branches (e.g. `:542, 564, 586, 613, 647, 679`) are unreachable in the request flow; confirm endpoint returns `410` (`:745-752`).
Impact: A confident AI command to change a **deal value, close date, or owner**, or edit a company/meeting/task, is applied instantly with no human confirmation — contrary to the feature's stated design and the "Confirmation required" UI label. Mitigated by admin-only access and the undo log, but undo isn't exposed in the UI (see R-02).
Code path: `POST /api/ai/command/` with e.g. "set the Acme deal value to 50000".
Recommended correction: Either return the confirmation/preview response for Tier-2 (call `preview()` and require a second explicit execute call), or remove the misleading "confirmation required" labeling and document immediate execution. Re-enable a real confirm endpoint or a two-step execute token.

**R-02 — High — AI undo exists in backend but is unreachable from the UI**
Evidence: `views.py:755-807` implements undo; frontend search shows no caller (only `/ai/command/` is used, `AICommandBar.tsx:55`); `action_id`/`undoable` in responses are never read.
Impact: The primary safety net for immediate AI execution (R-01) is inaccessible to users; mistaken auto-executed edits/creates can only be reversed via Django admin/API. 
Recommended correction: Surface an "Undo" action on the success toast/drawer that POSTs `{action_id}` to `/ai/command/undo/`.

**R-03 — Medium — Blocked/refused and unknown AI commands give the user no feedback**
Evidence: `AICommandBar.tsx:59-67` handles only `acted` and `draft`; `build_blocked_response`/`build_unknown_response` (`views.py:285-304`) include neither, so nothing renders.
Impact: A user issuing a delete/role/commission/bulk command sees the button return to idle with no message; appears broken. 
Recommended correction: Handle `blocked`/`refusal`/`needs_review` in the mutation `onSuccess` and show a toast/panel.

**R-04 — Medium — No object-level ownership on companies, projects, tasks, activities**
Evidence: `clients/views.py:7`, `projects/views.py:7`, `tasks/views.py:7`, `activities/views.py:7` have no `permission_classes` → default `IsAuthenticated`; full CRUD incl. DELETE for any user.
Impact: Any `sales` user can edit or delete any company/project/task/activity, including records created by others. For a small trusted team this may be acceptable, but it is broader than the role model implies and offers no accountability.
Recommended correction: Decide policy; if restriction is desired, add ownership fields + object permissions, or restrict delete to admin.

**R-05 — Medium — Deleting a company cascades to its deals and projects (silent data loss)**
Evidence: `sales/models.py:41` `company = FK(Client, on_delete=CASCADE)`; `projects/models.py:21` `client = FK(Client, on_delete=CASCADE)`. Frontend delete only shows a generic `window.confirm("Delete this record?")` (`EntityTable.tsx:33`).
Impact: A single company deletion (allowed for any user, R-04) destroys all associated deals and projects (and nulls tasks/activities/meetings). No warning of scope.
Recommended correction: Use soft-delete or `PROTECT`/`RESTRICT`, or a scoped confirmation listing dependent records; restrict to admin.

**R-06 — Medium — Deleting a user who owns deals/meetings returns an unhandled 500**
Evidence: `Deal.owner`/`Meeting.owner` are `on_delete=PROTECT` (`sales/models.py:47`, `meetings/models.py:21`); `UserViewSet` is a full `ModelViewSet` (admin) with a DELETE route and no guard.
Impact: `DELETE /api/users/{id}/` on an owner raises `ProtectedError` → 500 with a stack trace when `DEBUG=True`. No UI triggers this, but the endpoint is exposed.
Recommended correction: Disable user delete (deactivate only) or catch `ProtectedError` and return 409.

**R-07 — Low — Deal owner can be reassigned on update by a non-admin owner**
Evidence: `DealSerializer` exposes writable `owner` (`serializers.py:37`); `DealViewSet` has `perform_create` owner-forcing but **no `perform_update` guard** (`sales/views.py:71-73`); object permission allows the owner to PUT/PATCH their own deal.
Impact: A sales user editing their own deal could hand it to another user (not steal others'). Minor.
Recommended correction: Force/validate `owner` on update for non-admins.

**R-08 — Low — No server-side pagination on any list endpoint**
Evidence: no `DEFAULT_PAGINATION_CLASS`/`PAGE_SIZE` in `settings.py:130-142`; list endpoints return full arrays (frontend `listEntities<T>` expects `T[]`).
Impact: As data grows, list/search endpoints load entire tables into memory and over the wire; the global search fans out 5 unbounded queries. Fine at small scale, degrades later.
Recommended correction: Add DRF pagination and adapt the client to page.

**R-09 — Low — "Won this month" / win-rate rely on `updated_at`, not a close timestamp**
Evidence: `crm/views.py:55` filters won deals by `updated_at__date__gte=month_start`; `updated_at` auto-updates on any edit (`sales/models.py:52`).
Impact: Editing an old won deal this month makes it count as "won this month"; metrics can drift. 
Recommended correction: Add a dedicated `closed_at`/`won_at` timestamp set on status transition.

**R-10 — Low — AI error responses leak internal exception text**
Evidence: `views.py:708` returns `{"error": str(exc)}` (provider/parse exception) to the client.
Impact: Minor information disclosure (admin-only audience). 
Recommended correction: Log detail server-side; return a generic message.

**R-11 — Low/Informational — JWT stored in `localStorage`**
Evidence: `api/client.ts:9,35`, `auth.tsx:41-42`.
Impact: Tokens are readable by any injected script (XSS). Standard SPA tradeoff; acceptable for an internal tool but worth noting. No refresh-token rotation/blacklist configured (`settings.py:144-147`), so a leaked refresh token is valid 7 days.

**R-12 — Informational — Production hardening absent**
Evidence: `settings.py:28-30` insecure default `SECRET_KEY`, `DEBUG` defaults `True`; no `SECURE_SSL_REDIRECT`/HSTS/secure-cookie settings; no throttling; no app Dockerfile; DB compose uses trivial `crm/crm/crm` credentials.
Impact: Not safe to deploy as-is to a public host. 
Recommended correction: See §15 checklist.

---

## 14. Test coverage and quality gaps

- **Backend tests:** none (no `tests.py`/`test_*`/`conftest.py`/`pytest.ini`). **Fact.**
- **Frontend tests:** none (no Vitest/Jest/RTL/Playwright config or specs). **Fact.**
- **Frameworks configured:** none for testing. Type safety via TS `strict` (uncompiled here). No linter/formatter configured.
- **CI:** none; builds are not reproducible via pipeline. Lockfiles: `Frontend/package-lock.json` present (good); backend uses version ranges in `requirements.txt` (no hash-pinned lock).

**Prioritized test-gap list (highest value first):**
1. **AI command safety** — tier routing (auto/confirm/blocked/unknown), confidence gating, and (critically) whether Tier-2 requires confirmation; undo correctness for create/update.
2. **Permissions** — deal/meeting object ownership; admin-only user/commission/pipeline/AI endpoints; value/commission masking for non-owners; leaderboard masking.
3. **Sales calculations** — commission (earned/potential), win rate, pipeline value, leaderboard ranking/sort, dashboard scoping.
4. **Pipeline movement** — `move` action stage/pipeline consistency and status derivation (`Deal.save`).
5. **CRUD + validation** — deal pipeline/stage consistency (`serializers.py:56-61`), meeting end>start and company↔deal match (`meetings/serializers.py:20-30`), commission-rate bounds.
6. **Auth** — login, refresh-on-401 retry, logout, protected/admin routing.
7. **Frontend forms** — Zod schemas and submit→persist for each page; optimistic move rollback.
8. **Error/empty/loading states** — already present in UI; add regression tests.
9. **Delete safety** — company cascade, user-delete PROTECT behavior.
10. **E2E** — login → create company → create deal → move → dashboard/leaderboard reflect changes.

---

## 15. Production-readiness blockers (checklist)

Must-do before production:
- [ ] Set a real `DJANGO_SECRET_KEY`; force `DEBUG=False`; set explicit `DJANGO_ALLOWED_HOSTS`.
- [ ] Add `ANTHROPIC_API_KEY` to `Backend/.env.example` and document it; decide AI on/off default.
- [ ] Resolve the AI confirmation contract (R-01) and expose undo (R-02) or disable Tier-2 auto-execution.
- [ ] Handle blocked/refused AI responses in the UI (R-03).
- [ ] Decide and enforce authorization for companies/projects/tasks/activities (R-04); restrict destructive cascades (R-05); guard user delete (R-06).
- [ ] Add security headers/settings: HTTPS redirect, HSTS, secure/HTTP-only cookies (if used), `SECURE_*`.
- [ ] Add throttling/rate-limiting (login + AI endpoint at minimum) and brute-force protection.
- [ ] Add server-side pagination (R-08).
- [ ] Introduce automated tests + CI; pin backend dependencies (hashes/lock).
- [ ] Provide production runtime: WSGI/ASGI server (gunicorn/uvicorn), static file handling (`collectstatic`/WhiteNoise/CDN), app Dockerfile(s), non-trivial DB credentials, backups.
- [ ] Add observability/error reporting (e.g., Sentry) and structured logging.
- [ ] Run `manage.py check --deploy`, `makemigrations --check`, and `tsc -b` in a real environment and fix findings (unverified here).

---

## 16. Recommended roadmap

**Immediate blockers (P0)**
- P0: Fix/clarify AI Tier-2 confirmation (R-01) and wire undo into the UI (R-02).
- P0: Surface blocked/error AI feedback (R-03).
- P0: Add `ANTHROPIC_API_KEY` to `.env.example` + docs; set secure `SECRET_KEY`/`DEBUG` for any shared deploy.
- P0: Guard destructive paths — company cascade (R-05), user delete (R-06).

**Next stabilization (P1)**
- P1: Decide + implement authorization policy for clients/projects/tasks/activities (R-04).
- P1: Align frontend AI types with the backend contract; extend review UI beyond 2 intents or route auto-execution feedback consistently (incl. list refresh after all intents).
- P1: Add server-side pagination + push list filtering to the API (R-08).
- P1: Add `closed_at` for accurate won-this-month/win-rate (R-09).

**Product completion (P2)**
- P2: User reactivate + last-admin/self-deactivation safeguards; password reset flow.
- P2: Pipeline/stage management UI (currently admin-only).
- P2: AI: confirmation preview panel, cost/rate guardrails, richer disambiguation for all intents.

**Testing (P1–P2)**
- P1: Backend tests for permissions, sales math, AI tiers/undo, pipeline move.
- P2: Frontend form/integration tests + one E2E happy path; add CI.

**Security (P0–P1)**
- P0: Throttling on login + AI; stop leaking exception text (R-10).
- P1: Reconsider token storage/rotation (R-11); add `SECURE_*` headers (R-12).

**Deployment (P1–P2)**
- P1: App Dockerfile(s), gunicorn/uvicorn, static handling, real DB creds, backups.
- P2: CI/CD pipeline, observability/error reporting, deployment docs.

**Later improvements (P3)**
- P3: Audit logging beyond AI; soft-delete/restore; bulk actions with confirmations; scalable global search (single endpoint); accessibility pass (some interactive elements lack labels/roles).

---

## 17. Final verdict

**Functional MVP (early internal beta).**

**Rationale (evidence-based):** The product's core — auth, role-based navigation, and full CRUD across companies, projects, tasks, activities, meetings, and a complete sales pipeline with deals, drag-and-drop movement, commissions, leaderboard, and dashboard — is **genuinely implemented and wired end-to-end**, compiles cleanly (`compileall` exit 0), and shows consistent, non-placeholder engineering (loading/empty/error/success states, optimistic updates, theming, toasts). That places it well above a prototype.

It is **not** an internal-beta-plus/release candidate because: there are **no automated tests** at all; the **AI feature is materially incomplete and internally inconsistent** (un-enforced confirmation tier, no undo/feedback UI, only 2 review intents); the **authorization model is coarse** (no ownership on four core entities, cascade-delete and user-delete hazards); and it is **not production-hardened** (insecure defaults, no throttling/pagination, no app container/CI, undocumented required AI key). Type-checking, Django system checks, and migration-drift checks could not be executed here and remain **unverified**.

In short: **a solid, usable internal MVP for a trusted small team, not yet a production system.** Addressing the P0/P1 items in §16 — especially tests, the AI confirmation/undo contract, authorization, and deployment/security hardening — is the path to release readiness.
