from os import path
from pathlib import Path

import dj_database_url
import environ

env = environ.Env(
    DEBUG=(bool, False),
    DJANGO_SECRET_KEY=(str, ""),
    ALLOWED_HOSTS=(list, ["*"]),
    DATABASE_URL=(str, "sqlite:////tmp/my-tmp-sqlite.db"),
    TALPA_PRODUCT_EXPERIENCE_API=(
        str,
        "https://talpa-verkkokauppa-product-experience-api-dev.agw.arodevtest.hel.fi",
    ),
    OPEN_CITY_PROFILE_GRAPHQL_API=(str, "https://profile-api.test.hel.ninja/graphql/"),
    KMO_URL=(str, "https://kartta.hel.fi/ws/geoserver/avoindata/wfs"),
)

if path.exists(".env"):
    environ.Env().read_env(".env")

BASE_DIR = Path(__file__).resolve().parent.parent
DEBUG = env("DEBUG")
SECRET_KEY = env("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

AUTH_USER_MODEL = "users_app.CustomUser"

SRID = 4326
KMO_URL = env("KMO_URL")
OPEN_CITY_PROFILE_GRAPHQL_API = env("OPEN_CITY_PROFILE_GRAPHQL_API")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.gis",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    # disable Django’s static file handling during development so that whitenoise can take over
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "ariadne.contrib.django",
    "django_extensions",
    "corsheaders",
    "parking_permits_app",
    "users_app",
    "rest_framework",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoiseMiddleware should be above all and just below SecurityMiddleware
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "project.urls"

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


LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_L10N = True

USE_TZ = True


STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "static-files"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# FOR TALPA
NAMESPACE = "parkingPermits"
TALPA_PRODUCT_EXPERIENCE_API = env("TALPA_PRODUCT_EXPERIENCE_API")

CORS_ORIGIN_ALLOW_ALL = True
