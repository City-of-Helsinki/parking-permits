from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path
from django.views.generic import RedirectView
from drf_yasg import openapi
from drf_yasg.views import get_schema_view


def healthz(*args, **kwargs):
    """Returns status code 200 if the server is alive."""
    return HttpResponse(status=200)


def readiness(*args, **kwargs):
    """
    Returns status code 200 if the server is ready to perform its duties.

    This goes through each database connection and perform a standard SQL
    query without requiring any particular tables to exist.
    """
    from django.db import connections

    for name in connections:
        cursor = connections[name].cursor()
        cursor.execute("SELECT 1;")
        cursor.fetchone()

    return HttpResponse(status=200)


schema_view = get_schema_view(
    openapi.Info(
        title="Parking permits API",
        default_version="v1",
        description="Parking permits API",
        terms_of_service="https://www.hel.fi/static/liitteet/kaupunkiymparisto/"
        "liikenne-ja-kartat/pysakointi/pysakointitunnusten-ohjeet.pdf",
        contact=openapi.Contact(
            name="City of Helsinki - Urban environment and traffic"
        ),
    ),
    public=True,
)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", RedirectView.as_view(url="/admin/")),
    path("healthz/", healthz),
    path("readiness/", readiness),
    path("", include("parking_permits.urls")),
    path(
        "swagger/",
        schema_view.with_ui("swagger", cache_timeout=0),
        name="schema-swagger-ui",
    ),
    path("redoc/", schema_view.with_ui("redoc", cache_timeout=0), name="schema-redoc"),
]
