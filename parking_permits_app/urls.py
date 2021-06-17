from django.urls import path
from rest_framework.routers import DefaultRouter

from parking_permits_app import graphql, views

from .url_utils import versioned_url

router = DefaultRouter()
router.register(r"cart", views.ProductViewSet, basename="cart")

app_name = "parking_permit"
urlpatterns = [
    path("graphql/", graphql.view, name="graphql"),
    path(
        "api/talpa/resolve-availability/",
        views.TalpaResolveAvailability.as_view(),
        name="talpa-availability",
    ),
    versioned_url("v1", router.urls),
]
