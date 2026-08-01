from datetime import timedelta
import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


def _load_single_env_file(env_path):
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def load_env_file():
    """Load ``.env`` plus any extra files named in ``DJANGO_ENV_FILE``.

    ``DJANGO_ENV_FILE`` (comma-separated, relative to ``Backend/``) lets a
    developer point Django at an alternative environment without editing ``.env``
    — e.g. ``DJANGO_ENV_FILE=.env.supabase.local`` to run migrations against the
    Supabase project. Existing OS env vars always win (``setdefault``), and the
    real files stay git-ignored.
    """
    _load_single_env_file(BASE_DIR / ".env")
    for name in os.environ.get("DJANGO_ENV_FILE", "").split(","):
        name = name.strip()
        if name:
            _load_single_env_file(BASE_DIR / name)


load_env_file()


def env(name, default=None):
    return os.environ.get(name, default)


SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-only-secret-key-change-me")
DEBUG = env("DJANGO_DEBUG", "True").lower() == "true"
ALLOWED_HOSTS = [host.strip() for host in env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if host.strip()]

INSTALLED_APPS = [
    "unfold",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "django_filters",
    "rest_framework_simplejwt",
    "accounts",
    "clients",
    "projects",
    "sales",
    "tasks",
    "activities",
    "meetings",
    "ai_commands",
    "audit",
    "workforce",
    "leads",
    "branding",
    "mediastore",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "crm.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "crm.wsgi.application"

# Database — Supabase (or any) PostgreSQL is the *host*; the Django ORM stays
# authoritative over the schema and migrations. See crm/dbconfig.py for the
# resolution order (DATABASE_URL -> POSTGRES_* -> SQLite dev fallback) and for
# credential-safe redaction. Production never silently falls back to SQLite.
from crm.dbconfig import build_database_config  # noqa: E402

DATABASES = {"default": build_database_config(env, debug=DEBUG)}

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
# Timestamps are stored in UTC (USE_TZ=True). Shift/workforce logic and business
# reporting use the business timezone below (Asia/Amman) for day boundaries and
# the 9:00 AM–9:00 PM working window.
TIME_ZONE = "UTC"
BUSINESS_TIMEZONE = env("BUSINESS_TIMEZONE", "Asia/Amman")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# Plain storage by default (dev/tests need no collectstatic); production swaps
# in WhiteNoise's compressed, hashed manifest storage below.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# CORS — the SPA (Cloudflare Pages) is a different origin from the API (Cloud
# Run), so its exact HTTPS origin(s) must be listed here in production, e.g.
# CORS_ALLOWED_ORIGINS=https://crm.pages.dev,https://crm.example.com
# The origin list is always explicit; the wildcard "allow all" mode is never
# enabled. Auth uses bearer JWTs in the Authorization header (not cookies), so
# credentialed CORS stays off unless explicitly turned on.
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in env(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174,http://localhost:5175,http://127.0.0.1:5175",
    ).split(",")
    if origin.strip()
]
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOW_CREDENTIALS = env("CORS_ALLOW_CREDENTIALS", "False").lower() == "true"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "crm.pagination.DefaultPagination",
    "PAGE_SIZE": int(env("API_PAGE_SIZE", "25")),
    "EXCEPTION_HANDLER": "crm.exception_handler.custom_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.AnonRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "user": env("THROTTLE_USER", "5000/hour"),
        "anon": env("THROTTLE_ANON", "100/hour"),
        "login": env("THROTTLE_LOGIN", "20/min"),
        "ai": env("THROTTLE_AI", "30/min"),
        # Irreversible superadmin endpoints (permanent delete + full reset).
        "danger": env("THROTTLE_DANGER", "40/min"),
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(env("JWT_ACCESS_MINUTES", "30"))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(env("JWT_REFRESH_DAYS", "7"))),
    "ROTATE_REFRESH_TOKENS": env("JWT_ROTATE_REFRESH", "False").lower() == "true",
}

# --- AI command configuration ---
# The AI command feature is optional; when disabled or unconfigured the
# endpoints return 503 without leaking provider details.
AI_COMMANDS_ENABLED = env("AI_COMMANDS_ENABLED", "True").lower() == "true"
AI_CONFIRMATION_TTL_SECONDS = int(env("AI_CONFIRMATION_TTL_SECONDS", "300"))
AI_COMMAND_MAX_LENGTH = int(env("AI_COMMAND_MAX_LENGTH", "2000"))
AI_CONFIDENCE_THRESHOLD = float(env("AI_CONFIDENCE_THRESHOLD", "0.75"))

# --- Workforce / shift configuration ---
# The shift window and daily target are policy defaults; each EmployeeWorkPolicy
# can override them. Inactivity closes a session after this many idle minutes,
# and the full idle window is credited (see docs/WORKFORCE_POLICY.md).
WORKFORCE_INACTIVITY_MINUTES = int(env("WORKFORCE_INACTIVITY_MINUTES", "10"))
WORKFORCE_HEARTBEAT_SECONDS = int(env("WORKFORCE_HEARTBEAT_SECONDS", "30"))
WORKFORCE_DEFAULT_START_TIME = env("WORKFORCE_DEFAULT_START_TIME", "09:00")
WORKFORCE_DEFAULT_END_TIME = env("WORKFORCE_DEFAULT_END_TIME", "21:00")
WORKFORCE_DEFAULT_DAILY_TARGET_MINUTES = int(env("WORKFORCE_DEFAULT_DAILY_TARGET_MINUTES", "180"))

# --- Scheduler reconciliation endpoint (Google Cloud Scheduler) ---
# POST /internal/workforce/reconcile/ closes stale work sessions once a minute.
# It authenticates the caller with the OIDC token Cloud Scheduler attaches:
#   WORKFORCE_SCHEDULER_AUDIENCE         must equal the job's --oidc-token-audience
#   WORKFORCE_SCHEDULER_SERVICE_ACCOUNT  the scheduler service account email
# Both must be set for the endpoint to run; unset -> the endpoint returns 503,
# so it is safely inert until deployment configures it.
WORKFORCE_SCHEDULER_AUDIENCE = env("WORKFORCE_SCHEDULER_AUDIENCE", "")
WORKFORCE_SCHEDULER_SERVICE_ACCOUNT = env("WORKFORCE_SCHEDULER_SERVICE_ACCOUNT", "")

# --- Media / uploaded assets (brand logos, signatures) ---
# Cloud Run's filesystem is ephemeral and per-instance, so uploaded logos and
# signatures must NOT live on disk in production. By default they are persisted
# in the primary database (Supabase PostgreSQL) via crm.storage.DatabaseStorage
# and served by crm.views.serve_stored_media — durable with zero extra cost or
# infrastructure. Local development keeps simple on-disk storage. Override with
# MEDIA_STORAGE_BACKEND=filesystem|database. (Generated documents never touch the
# filesystem — they are database rows plus an immutable JSON snapshot.)
MEDIA_URL = env("MEDIA_URL", "/media/")
MEDIA_ROOT = BASE_DIR / "media"
_media_backend = env("MEDIA_STORAGE_BACKEND", "filesystem" if DEBUG else "database").strip().lower()
MEDIA_USE_DATABASE = _media_backend == "database"
if MEDIA_USE_DATABASE:
    STORAGES["default"]["BACKEND"] = "crm.storage.DatabaseStorage"
# Hard caps enforced when validating uploads (bytes / pixels).
UPLOAD_MAX_IMAGE_BYTES = int(env("UPLOAD_MAX_IMAGE_BYTES", str(5 * 1024 * 1024)))
UPLOAD_MAX_IMAGE_DIMENSION = int(env("UPLOAD_MAX_IMAGE_DIMENSION", "4000"))
LEAD_IMPORT_MAX_BYTES = int(env("LEAD_IMPORT_MAX_BYTES", str(5 * 1024 * 1024)))
LEAD_IMPORT_MAX_ROWS = int(env("LEAD_IMPORT_MAX_ROWS", "5000"))

UNFOLD = {
    "SITE_TITLE": "Fueldezign CRM",
    "SITE_HEADER": "Fueldezign CRM",
}

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in env("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

# --- Security hardening ---
# Dev keeps convenient defaults; production (DEBUG=False) must supply real
# secrets and turns on transport security. HSTS/SSL redirect are never enabled
# in development.
INSECURE_SECRET_KEYS = {"dev-only-secret-key-change-me", "change-me"}

if not DEBUG:
    if SECRET_KEY in INSECURE_SECRET_KEYS:
        raise RuntimeError(
            "DJANGO_SECRET_KEY must be set to a strong, unique value when DJANGO_DEBUG=False."
        )
    if not ALLOWED_HOSTS:
        raise RuntimeError("DJANGO_ALLOWED_HOSTS must be set when DJANGO_DEBUG=False.")

    SECURE_SSL_REDIRECT = env("SECURE_SSL_REDIRECT", "True").lower() == "true"
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(env("SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    # When running behind a TLS-terminating proxy (nginx, load balancer).
    if env("USE_X_FORWARDED_PROTO", "True").lower() == "true":
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    STORAGES["staticfiles"]["BACKEND"] = "whitenoise.storage.CompressedManifestStaticFilesStorage"

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "standard"},
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
    "loggers": {
        # Provider/interpretation detail is logged here, never returned to clients.
        "ai_commands": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
    },
}
