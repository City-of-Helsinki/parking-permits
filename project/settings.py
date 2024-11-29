from os import environ as os_environ
from os import path
from pathlib import Path

import dj_database_url
import environ
import sentry_sdk
from corsheaders.defaults import default_headers
from sentry_sdk.integrations.django import DjangoIntegration

GDAL_LIBRARY_PATH = os_environ.get("GDAL_LIBRARY_PATH")
GEOS_LIBRARY_PATH = os_environ.get("GEOS_LIBRARY_PATH")

env = environ.Env(
    DEBUG=(bool, False),
    DJANGO_SECRET_KEY=(str, ""),
    ALLOWED_HOSTS=(list, ["*"]),
    CORS_ALLOWED_ORIGINS=(list, ["http://localhost:3000"]),
    CSRF_TRUSTED_ORIGINS=(list, ["https://*.hel.fi", "https://*.hel.ninja"]),
    DATABASE_URL=(str, "sqlite:////tmp/my-tmp-sqlite.db"),
    TALPA_NAMESPACE=(str, "asukaspysakointi"),
    TALPA_API_KEY=(str, ""),
    TALPA_MERCHANT_EXPERIENCE_API=(
        str,
        "",
    ),
    TALPA_PRODUCT_EXPERIENCE_API=(str, ""),
    TALPA_ORDER_EXPERIENCE_API=(str, ""),
    TALPA_ORDER_PAYMENT_MAX_PERIOD_MINS=(int, 15),
    TALPA_ORDER_PAYMENT_WEBHOOK_WAIT_BUFFER_MINS=(int, 0),
    TALPA_WEBHOOK_WAIT_BUFFER_SECONDS=(int, 5),
    TALPA_SUBSCRIPTION_PERIOD_UNIT=(str, "monthly"),
    TALPA_DEFAULT_ACCOUNTING_COMPANY_CODE=(str, ""),
    TALPA_DEFAULT_ACCOUNTING_VAT_CODE=(str, ""),
    TALPA_DEFAULT_ACCOUNTING_INTERNAL_ORDER=(str, ""),
    TALPA_DEFAULT_ACCOUNTING_PROFIT_CENTER=(str, ""),
    TALPA_DEFAULT_ACCOUNTING_BALANCE_PROFIT_CENTER=(str, ""),
    TALPA_DEFAULT_ACCOUNTING_PROJECT=(str, ""),
    TALPA_DEFAULT_ACCOUNTING_OPERATION_AREA=(str, ""),
    TALPA_DEFAULT_ACCOUNTING_MAIN_LEDGER_ACCOUNT=(str, ""),
    KAMI_URL=(str, "https://kartta.hel.fi/ws/geoserver/avoindata/wfs"),
    OPEN_CITY_PROFILE_GRAPHQL_API=(str, "https://profile-api.test.hel.ninja/graphql/"),
    TOKEN_AUTH_ACCEPTED_AUDIENCE=(list, []),
    TOKEN_AUTH_ACCEPTED_SCOPE_PREFIX=(list, []),
    TOKEN_AUTH_AUTHSERVER_URL=(str, ""),
    TOKEN_AUTH_REQUIRE_SCOPE_PREFIX=(str, ""),
    TOKEN_AUTH_API_AUTHORIZATION_FIELD=(str, ""),
    HELUSERS_BACK_CHANNEL_LOGOUT_ENABLED=(bool, False),
    HELUSERS_USER_MIGRATE_ENABLED=(bool, False),
    GDPR_API_QUERY_SCOPE=(str, ""),
    GDPR_API_DELETE_SCOPE=(str, ""),
    PARKKIHUBI_DOMAIN=(str, ""),
    PARKKIHUBI_PERMIT_SERIES=(str, ""),
    PARKKIHUBI_TOKEN=(str, ""),
    PARKKIHUBI_OPERATOR_ENDPOINT=(str, ""),
    DEBUG_SKIP_PARKKIHUBI_SYNC=(bool, False),
    PERMIT_EXTENSIONS_ENABLED=(bool, False),
    TRAFICOM_MOCK=(bool, False),
    TRAFICOM_ENDPOINT=(str, ""),
    TRAFICOM_USERNAME=(str, ""),
    TRAFICOM_PASSWORD=(str, ""),
    TRAFICOM_SANOMA_TYYPPI=(str, ""),
    TRAFICOM_SOVELLUS=(str, ""),
    TRAFICOM_YMPARISTO=(str, ""),
    TRAFICOM_ASIAKAS=(str, ""),
    TRAFICOM_SOKU_TUNNUS=(str, ""),
    TRAFICOM_PALVELU_TUNNUS=(str, ""),
    TRAFICOM_VERIFY_SSL=(bool, True),
    TRAFICOM_CHECK=(bool, True),
    HELSINKI_ADDRESS_CHECK=(bool, True),
    DVV_PERSONAL_INFO_URL=(str, ""),
    DVV_USERNAME=(str, ""),
    DVV_PASSWORD=(str, ""),
    DVV_SOSONIMI=(str, ""),
    DVV_LOPPUKAYTTAJA=(str, ""),
    EMAIL_USE_TLS=(bool, False),
    EMAIL_HOST=(str, "localhost"),
    EMAIL_HOST_USER=(str, ""),
    EMAIL_HOST_PASSWORD=(str, ""),
    EMAIL_PORT=(int, 25),
    EMAIL_TIMEOUT=(int, 15),
    DEFAULT_FROM_EMAIL=(str, "Pysäköintitunnukset <noreply_pysakointitunnus@hel.fi>"),
    THIRD_PARTY_PARKING_PROVIDER_EMAILS=(list, []),
    MAILER_USE_FILE_LOCK=(bool, False),
    MAILER_LOCK_PATH=(str, "/tmp"),
    MAILER_EMAIL_MAX_BATCH=(int, 200),
    MAILER_EMAIL_THROTTLE=(int, 1),
    FIELD_ENCRYPTION_KEYS=(str, ""),
    SENTRY_DSN=(str, ""),
    SENTRY_ENVIRONMENT=(str, ""),
)

if path.exists(".env"):
    environ.Env().read_env(".env")

BASE_DIR = Path(__file__).resolve().parent.parent
DEBUG = env("DEBUG")
SECRET_KEY = env("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")

AUTH_USER_MODEL = "users.User"

SRID = 4326
KAMI_URL = env("KAMI_URL")
OPEN_CITY_PROFILE_GRAPHQL_API = env("OPEN_CITY_PROFILE_GRAPHQL_API")

INSTALLED_APPS = [
    "helusers.apps.HelusersConfig",
    "helusers.apps.HelusersAdminConfig",
    "django.contrib.gis",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    # disable Django’s static file handling during development so that whitenoise can take over
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "ariadne_django",
    "django_extensions",
    "corsheaders",
    "parking_permits",
    "users",
    "rest_framework",
    "django_db_logger",
    "audit_logger",
    "drf_yasg",
    "django_crontab",
    "encrypted_fields",
    "mailer",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoiseMiddleware should be above all and just below SecurityMiddleware
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

FIELD_ENCRYPTION_KEYS = [env("FIELD_ENCRYPTION_KEYS")]

ROOT_URLCONF = "project.urls"

LOCALE_PATHS = [path.join(BASE_DIR, "locale")]

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

WSGI_APPLICATION = "project.wsgi.application"

DATABASES = {"default": dj_database_url.parse(env("DATABASE_URL"))}


AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


LANGUAGE_CODE = "fi"

TIME_ZONE = "Europe/Helsinki"

USE_I18N = True

USE_TZ = True


STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "static-files"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# SESSIONS/CSRF
CSRF_USE_SESSIONS = True
SESSION_COOKIE_SECURE = True

# FOR TALPA
NAMESPACE = env("TALPA_NAMESPACE")
TALPA_MERCHANT_EXPERIENCE_API = env("TALPA_MERCHANT_EXPERIENCE_API")
TALPA_PRODUCT_EXPERIENCE_API = env("TALPA_PRODUCT_EXPERIENCE_API")
TALPA_ORDER_EXPERIENCE_API = env("TALPA_ORDER_EXPERIENCE_API")
TALPA_API_KEY = env("TALPA_API_KEY")
TALPA_SUBSCRIPTION_PERIOD_UNIT = env("TALPA_SUBSCRIPTION_PERIOD_UNIT")
TALPA_ORDER_PAYMENT_MAX_PERIOD_MINS = env("TALPA_ORDER_PAYMENT_MAX_PERIOD_MINS")
TALPA_ORDER_PAYMENT_WEBHOOK_WAIT_BUFFER_MINS = env(
    "TALPA_ORDER_PAYMENT_WEBHOOK_WAIT_BUFFER_MINS"
)
TALPA_WEBHOOK_WAIT_BUFFER_SECONDS = env("TALPA_WEBHOOK_WAIT_BUFFER_SECONDS")
TALPA_DEFAULT_ACCOUNTING_COMPANY_CODE = env("TALPA_DEFAULT_ACCOUNTING_COMPANY_CODE")
TALPA_DEFAULT_ACCOUNTING_VAT_CODE = env("TALPA_DEFAULT_ACCOUNTING_VAT_CODE")
TALPA_DEFAULT_ACCOUNTING_INTERNAL_ORDER = env("TALPA_DEFAULT_ACCOUNTING_INTERNAL_ORDER")
TALPA_DEFAULT_ACCOUNTING_PROFIT_CENTER = env("TALPA_DEFAULT_ACCOUNTING_PROFIT_CENTER")
TALPA_DEFAULT_ACCOUNTING_BALANCE_PROFIT_CENTER = env(
    "TALPA_DEFAULT_ACCOUNTING_BALANCE_PROFIT_CENTER"
)
TALPA_DEFAULT_ACCOUNTING_PROJECT = env("TALPA_DEFAULT_ACCOUNTING_PROJECT")
TALPA_DEFAULT_ACCOUNTING_OPERATION_AREA = env("TALPA_DEFAULT_ACCOUNTING_OPERATION_AREA")
TALPA_DEFAULT_ACCOUNTING_MAIN_LEDGER_ACCOUNT = env(
    "TALPA_DEFAULT_ACCOUNTING_MAIN_LEDGER_ACCOUNT"
)

# PARKKIHUBI
PARKKIHUBI_DOMAIN = env("PARKKIHUBI_DOMAIN")
PARKKIHUBI_PERMIT_SERIES = env("PARKKIHUBI_PERMIT_SERIES")
PARKKIHUBI_TOKEN = env("PARKKIHUBI_TOKEN")
PARKKIHUBI_OPERATOR_ENDPOINT = env("PARKKIHUBI_OPERATOR_ENDPOINT")

# TRAFICOM
TRAFICOM_MOCK = env("TRAFICOM_MOCK")
TRAFICOM_ENDPOINT = env("TRAFICOM_ENDPOINT")
TRAFICOM_USERNAME = env("TRAFICOM_USERNAME")
TRAFICOM_PASSWORD = env("TRAFICOM_PASSWORD")
TRAFICOM_SANOMA_TYYPPI = env("TRAFICOM_SANOMA_TYYPPI")
TRAFICOM_SOVELLUS = env("TRAFICOM_SOVELLUS")
TRAFICOM_YMPARISTO = env("TRAFICOM_YMPARISTO")
TRAFICOM_ASIAKAS = env("TRAFICOM_ASIAKAS")
TRAFICOM_SOKU_TUNNUS = env("TRAFICOM_SOKU_TUNNUS")
TRAFICOM_PALVELU_TUNNUS = env("TRAFICOM_PALVELU_TUNNUS")
TRAFICOM_VERIFY_SSL = env("TRAFICOM_VERIFY_SSL")
TRAFICOM_CHECK = env("TRAFICOM_CHECK")
HELSINKI_ADDRESS_CHECK = env("HELSINKI_ADDRESS_CHECK")

# PARKING PERMIT EXTENSIONS
PERMIT_EXTENSIONS_ENABLED = env("PERMIT_EXTENSIONS_ENABLED")

# CORS
CORS_ALLOWED_ORIGINS = env("CORS_ALLOWED_ORIGINS")
CORS_ALLOW_HEADERS = list(default_headers) + [
    "x-authorization",  # for passing Helsinki Profile API token form frontend
]

# OIDC auth
OIDC_API_TOKEN_AUTH = {
    "AUDIENCE": env("TOKEN_AUTH_ACCEPTED_AUDIENCE"),
    "API_SCOPE_PREFIX": env("TOKEN_AUTH_ACCEPTED_SCOPE_PREFIX"),
    "ISSUER": env("TOKEN_AUTH_AUTHSERVER_URL"),
    "REQUIRE_API_SCOPE_FOR_AUTHENTICATION": env("TOKEN_AUTH_REQUIRE_SCOPE_PREFIX"),
    "API_AUTHORIZATION_FIELD": env("TOKEN_AUTH_API_AUTHORIZATION_FIELD"),
}
HELUSERS_BACK_CHANNEL_LOGOUT_ENABLED = env("HELUSERS_BACK_CHANNEL_LOGOUT_ENABLED")
HELUSERS_USER_MIGRATE_ENABLED = env("HELUSERS_USER_MIGRATE_ENABLED")

MAX_ALLOWED_USER_PERMIT = 2
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s"
        },
        "simple": {"format": "%(levelname)s %(asctime)s %(message)s"},
    },
    "handlers": {
        "db_log": {
            "level": "DEBUG",
            "class": "django_db_logger.db_log_handler.DatabaseLogHandler",
        },
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
        "audit_log": {
            "class": "audit_logger.db_log_handler.AuditLogHandler",
            "level": "DEBUG",
        },
    },
    "loggers": {
        "db": {"handlers": ["db_log"], "level": "DEBUG"},
        "django": {"handlers": ["console"], "level": "INFO"},
        "helusers": {"handlers": ["console"], "level": "DEBUG"},
        "audit": {"handlers": ["audit_log"], "level": "DEBUG"},
    },
}

CRONJOBS = [
    ("22 00 * * *", "parking_permits.cron.automatic_expiration_of_permits"),
    ("59 23 * * *", "parking_permits.cron.automatic_remove_obsolete_customer_data"),
    ("*/30 * * * *", "parking_permits.cron.automatic_syncing_of_permits_to_parkkihubi"),
    (
        "0 8 * * 1",
        "parking_permits.cron.automatic_expiration_remind_notification_of_permits",
    ),
]

# GDPR API
GDPR_API_MODEL = "parking_permits.Customer"
GDPR_API_QUERY_SCOPE = env("GDPR_API_QUERY_SCOPE")
GDPR_API_DELETE_SCOPE = env("GDPR_API_DELETE_SCOPE")


# DVV integration
DVV_PERSONAL_INFO_URL = env("DVV_PERSONAL_INFO_URL")
DVV_USERNAME = env("DVV_USERNAME")
DVV_PASSWORD = env("DVV_PASSWORD")
DVV_SOSONIMI = env("DVV_SOSONIMI")
DVV_LOPPUKAYTTAJA = env("DVV_LOPPUKAYTTAJA")

# Email configuration
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS")
EMAIL_HOST = env("EMAIL_HOST")
EMAIL_HOST_USER = env("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")
EMAIL_PORT = env.int("EMAIL_PORT")
EMAIL_TIMEOUT = env.int("EMAIL_TIMEOUT")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL")
THIRD_PARTY_PARKING_PROVIDER_EMAILS = env("THIRD_PARTY_PARKING_PROVIDER_EMAILS")
EMAIL_BACKEND = "mailer.backend.DbBackend"
MAILER_USE_FILE_LOCK = env("MAILER_USE_FILE_LOCK")
MAILER_LOCK_PATH = env("MAILER_LOCK_PATH")
MAILER_EMAIL_MAX_BATCH = env("MAILER_EMAIL_MAX_BATCH")
MAILER_EMAIL_THROTTLE = env("MAILER_EMAIL_THROTTLE")

sentry_sdk.init(
    dsn=env.str("SENTRY_DSN"),
    environment=env.str("SENTRY_ENVIRONMENT"),
    traces_sample_rate=1.0,
    send_default_pii=True,
    integrations=[DjangoIntegration()],
)

# Debug

# Skip Parkkihubi sync on permit create/update.
DEBUG_SKIP_PARKKIHUBI_SYNC = env("DEBUG_SKIP_PARKKIHUBI_SYNC")

if DEBUG:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
