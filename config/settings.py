"""Django settings for edital-depad-comunidades project."""

import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env file if it exists
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv(
    "SECRET_KEY",
    "django-insecure-default-change-in-production-random-50-character-key-here",
)

DEBUG = os.getenv("DEBUG", "True").lower() in ("true", "1", "yes")

allowed_hosts_raw = os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,0.0.0.0,testserver")
ALLOWED_HOSTS = [host.strip() for host in allowed_hosts_raw.split(",") if host.strip()]

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Local Apps
    "apps.accounts.apps.AccountsConfig",
    "apps.editais.apps.EditaisConfig",
    "apps.institutions.apps.InstitutionsConfig",
    "apps.submissions.apps.SubmissionsConfig",
    "apps.evaluations.apps.EvaluationsConfig",
    "apps.reviews.apps.ReviewsConfig",
    "apps.ranking.apps.RankingConfig",
    "apps.reporting.apps.ReportingConfig",
    "apps.audit.apps.AuditConfig",
]

# Optional migration/regression boundary. New edital runtime is independent.
ENABLE_LEGACY_IMPORT = os.getenv("ENABLE_LEGACY_IMPORT", "true").lower() == "true"
if ENABLE_LEGACY_IMPORT:
    INSTALLED_APPS.append("apps.legacy_import")

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
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

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Database
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'db.sqlite3'}")
DATABASES = {
    "default": dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=600,
        conn_health_checks=True,
    )
}

# Custom User Model
AUTH_USER_MODEL = "accounts.User"

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internationalization
LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Authentication URLs
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

# Authentication Adapter Configuration
AUTH_ADAPTER = os.getenv("AUTH_ADAPTER", "local")

# Microsoft Entra ID (Azure AD) / MSAL Configuration
# Preenchidos via .env. Só são usados quando AUTH_ADAPTER=microsoft.
MS_CLIENT_ID = os.getenv("MS_CLIENT_ID", "")
MS_CLIENT_SECRET = os.getenv("MS_CLIENT_SECRET", "")
MS_TENANT_ID = os.getenv("MS_TENANT_ID", "")
# Authority padrão single-tenant. Pode ser sobrescrita no .env se necessário.
MS_AUTHORITY = os.getenv(
    "MS_AUTHORITY",
    f"https://login.microsoftonline.com/{MS_TENANT_ID}" if MS_TENANT_ID else "",
)
# Deve coincidir EXATAMENTE com o Redirect URI registrado no portal do Entra ID.
MS_REDIRECT_URI = os.getenv(
    "MS_REDIRECT_URI",
    "http://localhost:8000/auth/microsoft/callback/",
)
# Escopos de recurso. openid/profile/offline_access são adicionados pelo MSAL.
MS_SCOPES = [s.strip() for s in os.getenv("MS_SCOPES", "User.Read").split(",") if s.strip()]

# Logging Configuration
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "simple": {
            "format": "[{asctime}] {levelname} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": os.getenv("LOG_LEVEL", "INFO"),
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": os.getenv("DJANGO_LOG_LEVEL", "INFO"),
            "propagate": False,
        },
        "apps": {
            "handlers": ["console"],
            "level": "DEBUG" if DEBUG else "INFO",
            "propagate": False,
        },
    },
}

# Security Hardening
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # Permite envio de cabeçalho X-CSRFToken pelo HTMX
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True

if not DEBUG:
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", "True").lower() == "true"
    SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
