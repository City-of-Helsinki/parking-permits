from django.urls import path

from parking_permits_app import graphql, views

urlpatterns = [
    path("", graphql.view, name="graphql"),
    path(
        "api/talpa/resolve-availability/",
        views.TalpaResolveAvailability.as_view(),
        name="talpa-availability",
    ),
]
