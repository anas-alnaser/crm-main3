# Near‑zero‑cost deployment: Cloud Run + Cloud Scheduler + Cloudflare Pages

This guide deploys the CRM for near‑zero idle cost:

| Component | Platform | Idle cost |
|-----------|----------|-----------|
| Django API | Google Cloud Run (scale‑to‑zero, request‑billed) | \$0 when no traffic |
| React SPA | Cloudflare Pages (static, generated `*.pages.dev`) | \$0 |
| Database | Existing Supabase PostgreSQL | existing |
| Minute reconciliation | Google Cloud Scheduler → HTTP endpoint | ~\$0 (1 job) |

There is **no always‑running scheduler service**. A single Cloud Scheduler job
calls one authenticated endpoint once a minute; the reconciliation is a short,
idempotent database sweep that runs inside the same Cloud Run service (which
scales back to zero afterwards).

> **Nothing in this file is a secret.** Real values (DB URL, Django secret key,
> Supabase credentials) are supplied at deploy time through Google Secret Manager
> and are never printed, committed, or sent to the frontend.

---

## 0. Target configuration (authoritative values)

```
# Google Cloud
Project ID .................. crm-morph-fuel
Deploy account .............. anasalnaser24@gmail.com
Region ...................... asia-southeast1            (Singapore)
Cloud Run service ........... crm-morph-fuel-api
  min instances ............. 0
  max instances ............. 1
  CPU ....................... 1
  memory .................... 512Mi
  billing ................... request-based (CPU throttled between requests)
  container port ............ 8000
  ingress ................... all (public; the SPA must reach it)
  auth ...................... allow-unauthenticated (endpoint-level auth in app)
Scheduler service account ... crm-scheduler@crm-morph-fuel.iam.gserviceaccount.com
Cloud Scheduler job ......... crm-workforce-reconcile   (every minute, OIDC)

# Cloudflare Pages
Project name ................ morph-fuel-crm
Repo layout ................. monorepo
Frontend root ............... Frontend
Build command ............... npm run build
Build output ................ dist
Production branch ........... feature/workforce-leads-multibrand-supabase
Domain ...................... generated morph-fuel-crm.pages.dev (no custom domain yet)
```

---

## 1. Prerequisites (interactive — you run these)

Browser‑based authentication cannot be automated from here. **Run these
yourself** and come back:

```bash
# Google Cloud SDK (opens a browser; sign in as anasalnaser24@gmail.com)
gcloud auth login
gcloud config set project crm-morph-fuel
gcloud config set run/region asia-southeast1

# Cloudflare Wrangler (opens a browser)
npx wrangler login
```

Enable the APIs used below (safe to re‑run):

```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  cloudscheduler.googleapis.com \
  secretmanager.googleapis.com \
  iam.googleapis.com
```

Optional — install Cloudflare's agent tooling (per
`https://developers.cloudflare.com/agent-setup/prompt.md`). Run inside Claude
Code:

```
claude plugin marketplace add cloudflare/skills
claude plugin install cloudflare@cloudflare
```
then run `/reload-plugins` to activate them.

---

## 2. Secrets in Google Secret Manager (never in the image or repo)

Pipe your real values straight into Secret Manager so they are never echoed.
Replace the `…` prompts with your actual values.

```bash
# Django secret key — generate a fresh 50-char key and store it
python -c "import secrets; print(secrets.token_urlsafe(50))" | \
  gcloud secrets create django-secret-key --data-file=-

# Supabase connection string (Session Pooler, port 5432 — see §6)
#   postgresql://USER:PASSWORD@HOST:5432/postgres
printf '%s' 'PASTE_DATABASE_URL_HERE' | \
  gcloud secrets create database-url --data-file=-

# Optional: Anthropic key for the AI-command feature (omit to disable it)
printf '%s' 'PASTE_ANTHROPIC_KEY_HERE' | \
  gcloud secrets create anthropic-api-key --data-file=-
```

Create a dedicated runtime service account for the API and let it read those
secrets (least privilege — it is not the scheduler account):

```bash
gcloud iam service-accounts create crm-run \
  --display-name="CRM Cloud Run runtime"

for S in django-secret-key database-url anthropic-api-key; do
  gcloud secrets add-iam-policy-binding "$S" \
    --member="serviceAccount:crm-run@crm-morph-fuel.iam.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"
done
```

---

## 3. Deploy the API to Cloud Run — Phase A (first deploy)

`ALLOWED_HOSTS` and the scheduler audience depend on the service URL, which you
only learn after the first deploy — so deploy once, read the URL, then finalize
in Phase B.

Deploy straight from the `Backend/` source (Cloud Build builds the existing,
unchanged `Backend/Dockerfile`):

```bash
gcloud run deploy crm-morph-fuel-api \
  --source Backend \
  --region asia-southeast1 \
  --service-account crm-run@crm-morph-fuel.iam.gserviceaccount.com \
  --min-instances 0 \
  --max-instances 1 \
  --cpu 1 \
  --memory 512Mi \
  --cpu-throttling \
  --port 8000 \
  --concurrency 80 \
  --timeout 120 \
  --allow-unauthenticated \
  --set-secrets "DJANGO_SECRET_KEY=django-secret-key:latest,DATABASE_URL=database-url:latest" \
  --set-env-vars "DJANGO_DEBUG=False" \
  --set-env-vars "DJANGO_ALLOWED_HOSTS=placeholder.invalid" \
  --set-env-vars "^##^CORS_ALLOWED_ORIGINS=https://morph-fuel-crm.pages.dev" \
  --set-env-vars "^##^CSRF_TRUSTED_ORIGINS=https://morph-fuel-crm.pages.dev" \
  --set-env-vars "DATABASE_SSLMODE=require" \
  --set-env-vars "DATABASE_CONN_MAX_AGE=0" \
  --set-env-vars "SECURE_SSL_REDIRECT=True" \
  --set-env-vars "USE_X_FORWARDED_PROTO=True" \
  --set-env-vars "BUSINESS_TIMEZONE=Asia/Amman" \
  --set-env-vars "MEDIA_STORAGE_BACKEND=database" \
  --set-env-vars "GUNICORN_WORKERS=2"
```

Notes:
- **`--cpu-throttling`** is request‑based billing: CPU is allocated only while a
  request is in flight, so an idle service costs nothing. (`--no-cpu-throttling`
  would switch to always‑on, instance‑based billing — do **not** use it.)
- **`--min-instances 0`** lets it scale to zero; **`--max-instances 1`** caps
  spend and guarantees the minute sweep never runs concurrently with itself.
- **`--port 8000`** matches the preserved Dockerfile (`EXPOSE 8000`); Cloud Run
  injects `PORT=8000` and `entrypoint.sh` binds gunicorn to `0.0.0.0:${PORT}`.
- **`--allow-unauthenticated`** is required because the browser SPA calls this
  service. The scheduler endpoint is not protected by Cloud Run IAM — it is
  protected inside Django by OIDC verification (§5).
- `^##^` changes the delimiter to `##` for that one variable so a value that
  itself contains commas is not split.
- `entrypoint.sh` runs `migrate` and `collectstatic` on start (both idempotent);
  static is served by WhiteNoise from inside the image, not from disk.

Capture the URL:

```bash
gcloud run services describe crm-morph-fuel-api \
  --region asia-southeast1 --format='value(status.url)'
# e.g. https://crm-morph-fuel-api-abc123-as.a.run.app
```

---

## 4. Finalize host‑dependent settings — Phase B

Let `RUN_URL` be the URL from the previous step (no trailing slash) and
`RUN_HOST` its hostname.

```bash
RUN_URL="https://crm-morph-fuel-api-abc123-as.a.run.app"     # <- your value
RUN_HOST="${RUN_URL#https://}"
RECONCILE_URL="${RUN_URL}/internal/workforce/reconcile/"

gcloud run services update crm-morph-fuel-api \
  --region asia-southeast1 \
  --update-env-vars "DJANGO_ALLOWED_HOSTS=${RUN_HOST}" \
  --update-env-vars "^##^CSRF_TRUSTED_ORIGINS=https://morph-fuel-crm.pages.dev##${RUN_URL}" \
  --update-env-vars "WORKFORCE_SCHEDULER_AUDIENCE=${RECONCILE_URL}" \
  --update-env-vars "WORKFORCE_SCHEDULER_SERVICE_ACCOUNT=crm-scheduler@crm-morph-fuel.iam.gserviceaccount.com"
```

- `DJANGO_ALLOWED_HOSTS` is the Cloud Run host (the API's own `Host` header).
- `CSRF_TRUSTED_ORIGINS` includes the SPA origin and the Cloud Run origin (the
  latter for the Django admin, which is served same‑origin over HTTPS).
- `WORKFORCE_SCHEDULER_AUDIENCE` must equal the scheduler job's
  `--oidc-token-audience` **exactly** (§5).

---

## 5. Cloud Scheduler — one minute job with a verified OIDC token

Create the scheduler identity and (defense in depth) grant it invoker on the
service:

```bash
gcloud iam service-accounts create crm-scheduler \
  --display-name="CRM workforce minute reconciliation"

gcloud run services add-iam-policy-binding crm-morph-fuel-api \
  --region asia-southeast1 \
  --member="serviceAccount:crm-scheduler@crm-morph-fuel.iam.gserviceaccount.com" \
  --role="roles/run.invoker"
```

Create the job (every minute, POST, OIDC token minted for the scheduler SA with
the reconcile URL as its audience):

```bash
gcloud scheduler jobs create http crm-workforce-reconcile \
  --location asia-southeast1 \
  --schedule "* * * * *" \
  --time-zone "Etc/UTC" \
  --uri "${RECONCILE_URL}" \
  --http-method POST \
  --oidc-service-account-email "crm-scheduler@crm-morph-fuel.iam.gserviceaccount.com" \
  --oidc-token-audience "${RECONCILE_URL}" \
  --attempt-deadline 30s \
  --max-retry-attempts 1
```

How the endpoint authenticates the call (`workforce/scheduler_auth.py`):

1. The request must present `Authorization: Bearer <oidc-jwt>`.
2. The JWT signature is verified against Google's public keys (RS256), with the
   audience pinned to `WORKFORCE_SCHEDULER_AUDIENCE` and `exp`/`iat` enforced.
3. The verified token must be Google‑issued (`iss`) for
   `WORKFORCE_SCHEDULER_SERVICE_ACCOUNT`, with `email_verified: true`.

Anything else — a normal user's app JWT, an admin's browser session, or an
anonymous request — carries no such token and is rejected (401/403). The handler
**ignores the request body entirely**: it accepts no user id and no timestamp,
and always reconciles every open session against the server clock.

Verify and inspect:

```bash
gcloud scheduler jobs run crm-workforce-reconcile --location asia-southeast1
gcloud run services logs read crm-morph-fuel-api --region asia-southeast1 --limit 20
# Expect HTTP 200: {"status":"ok","inspected":N,"closed":M,"at":"..."}
```

Troubleshooting: if job creation reports it cannot mint tokens for the SA, grant
the Cloud Scheduler service agent the token‑creator role once:
`gcloud iam service-accounts add-iam-policy-binding crm-scheduler@crm-morph-fuel.iam.gserviceaccount.com --member="serviceAccount:service-$(gcloud projects describe crm-morph-fuel --format='value(projectNumber)')@gcp-sa-cloudscheduler.iam.gserviceaccount.com" --role="roles/iam.serviceAccountTokenCreator"`.

---

## 6. Database (Supabase)

- Use the **Session Pooler** connection string on **port 5432**
  (`...@HOST:5432/postgres`). Django/psycopg3 uses prepared statements, which are
  incompatible with the transaction pooler (6543); the session pooler is correct.
- Keep `DATABASE_SSLMODE=require`.
- `DATABASE_CONN_MAX_AGE=0` is recommended on Cloud Run: because CPU is throttled
  between requests, holding a pooled connection open across idle periods can go
  stale. Opening per request via the pooler is robust and still cheap. (Raise it
  only if you measure a need and the pooler has spare slots.)
- The Django ORM stays authoritative over the schema; migrations run on container
  start. See `docs/SUPABASE_CUTOVER_CHECKLIST.md`.

---

## 7. Cloudflare Pages (React/Vite SPA)

The only build‑time variable the frontend needs is the **public** API base URL.
It is embedded into the JS bundle, so it must never contain a secret — set it to
the Cloud Run URL + `/api`:

```
VITE_API_BASE_URL = https://crm-morph-fuel-api-abc123-as.a.run.app/api
```

**Do not** put `DATABASE_URL`, `DATABASE_MIGRATION_URL`, `DJANGO_SECRET_KEY`,
Supabase credentials, or any service credential into Pages — those are backend
Cloud Run / Secret Manager values only.

### Option A — Git‑connected build (recommended)

In the Cloudflare dashboard → Workers & Pages → Create → Pages → Connect to Git:

```
Project name .............. morph-fuel-crm
Production branch ......... feature/workforce-leads-multibrand-supabase
Root directory ............ Frontend
Framework preset .......... Vite
Build command ............. npm run build
Build output directory .... dist
Environment variables ..... VITE_API_BASE_URL = https://<RUN_HOST>/api   (Production)
```

Cloudflare runs `npm ci && npm run build` in `Frontend/` on every push to the
production branch and publishes `Frontend/dist` to `morph-fuel-crm.pages.dev`.

### Option B — Direct upload with Wrangler (build locally, then upload)

`Frontend/wrangler.jsonc` records the project name and output dir. Build with the
API URL, then deploy the static output as a production deployment:

```bash
cd Frontend
npm ci
VITE_API_BASE_URL="https://<RUN_HOST>/api" npm run build
npx wrangler pages deploy dist \
  --project-name morph-fuel-crm \
  --branch feature/workforce-leads-multibrand-supabase
```

(`--branch` set to the production branch marks it a production deployment on the
generated `morph-fuel-crm.pages.dev` domain. No custom domain is configured yet.)

### After the SPA URL is known

If the exact `pages.dev` origin differs from `https://morph-fuel-crm.pages.dev`,
update the API's CORS/CSRF to match:

```bash
gcloud run services update crm-morph-fuel-api --region asia-southeast1 \
  --update-env-vars "^##^CORS_ALLOWED_ORIGINS=https://morph-fuel-crm.pages.dev"
```

---

## 8. Cloud Run environment variables (reference — no secrets)

| Variable | Source | Example / value | Notes |
|----------|--------|-----------------|-------|
| `DJANGO_SECRET_KEY` | Secret Manager | `django-secret-key:latest` | never in repo/image |
| `DATABASE_URL` | Secret Manager | `database-url:latest` | Supabase session pooler, :5432 |
| `ANTHROPIC_API_KEY` | Secret Manager (optional) | `anthropic-api-key:latest` | omit to disable AI commands |
| `DJANGO_DEBUG` | env | `False` | forces prod hardening |
| `DJANGO_ALLOWED_HOSTS` | env | `<RUN_HOST>` | Cloud Run hostname |
| `CORS_ALLOWED_ORIGINS` | env | `https://morph-fuel-crm.pages.dev` | SPA origin(s) |
| `CSRF_TRUSTED_ORIGINS` | env | `https://morph-fuel-crm.pages.dev##<RUN_URL>` | admin + SPA |
| `DATABASE_SSLMODE` | env | `require` | Supabase requires TLS |
| `DATABASE_CONN_MAX_AGE` | env | `0` | robust on scale‑to‑zero |
| `SECURE_SSL_REDIRECT` | env | `True` | Cloud Run terminates TLS |
| `USE_X_FORWARDED_PROTO` | env | `True` | trust proxy TLS header |
| `BUSINESS_TIMEZONE` | env | `Asia/Amman` | shift 9AM–9PM window |
| `MEDIA_STORAGE_BACKEND` | env | `database` | logos/signatures in Postgres |
| `WORKFORCE_SCHEDULER_AUDIENCE` | env | `<RECONCILE_URL>` | == job OIDC audience |
| `WORKFORCE_SCHEDULER_SERVICE_ACCOUNT` | env | `crm-scheduler@crm-morph-fuel.iam.gserviceaccount.com` | scheduler identity |
| `GUNICORN_WORKERS` | env | `2` | fits 512Mi |

Frontend (Cloudflare Pages) build variable — public, non‑secret:

| Variable | Value |
|----------|-------|
| `VITE_API_BASE_URL` | `https://<RUN_HOST>/api` |

---

## 9. Uploaded media & the ephemeral filesystem

Cloud Run's filesystem is in‑memory and per‑instance — anything written to disk
is lost on restart, redeploy, or scale event. This app therefore keeps **no**
uploaded asset on disk in production:

- **Brand logos & signature images** — stored in the database
  (`mediastore.StoredFile` via `crm.storage.DatabaseStorage`, selected by
  `MEDIA_STORAGE_BACKEND=database`, which is the default when `DJANGO_DEBUG=False`)
  and served by `crm.views.serve_stored_media` at `/media/<path>`. They survive
  restarts and are covered by Supabase backups.
- **Generated documents** — never files: each is a database row plus an immutable
  JSON/column snapshot (`branding.GeneratedDocumentSnapshot`).
- **Collected static & logs** — static is baked into the image and served by
  WhiteNoise; logs go to stdout (Cloud Logging). Neither is user data.

No persistent volume or object‑storage bucket is required.

---

## 10. Post‑deploy smoke test

```bash
curl -fsS "${RUN_URL}/api/health/"                       # {"status":"ok","database":true}
curl -i  -X POST "${RECONCILE_URL}"                      # 401 (no OIDC token) — good
gcloud scheduler jobs run crm-workforce-reconcile --location asia-southeast1
# then open https://morph-fuel-crm.pages.dev and log in
```

Roll back the API to a previous revision at any time with
`gcloud run services update-traffic crm-morph-fuel-api --region asia-southeast1 --to-revisions <REVISION>=100`.
