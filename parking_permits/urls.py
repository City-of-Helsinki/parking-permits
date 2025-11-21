from django.urls import path

from parking_permits import graphql, views

app_name = "parking_permits"
urlpatterns = [
    path("graphql/", graphql.view, name="graphql"),
    path("admin-graphql/", graphql.admin_view, name="admin-graphql"),
    path(
        "api/talpa/product/",
        views.ProductList.as_view(),
        name="product-list",
    ),
    path(
        "api/talpa/product/<int:pk>/",
        views.ProductDetail.as_view(),
        name="product-details",
    ),
    path(
        "api/talpa/resolve-availability/",
        views.TalpaResolveAvailability.as_view(),
        name="talpa-availability",
    ),
    path(
        "api/talpa/resolve-product/",
        views.TalpaResolveProduct.as_view(),
        name="talpa-product",
    ),
    path(
        "api/talpa/resolve-price/",
        views.TalpaResolvePrice.as_view(),
        name="talpa-price",
    ),
    path(
        "api/talpa/resolve-right-of-purchase/",
        views.TalpaResolveRightOfPurchase.as_view(),
        name="talpa-right-of-purchase",
    ),
    path(
        "api/talpa/payment/",
        views.PaymentView.as_view(),
        name="payment-notify",
    ),
    path(
        "api/talpa/order/",
        views.OrderView.as_view(),
        name="order-notify",
    ),
    path(
        "api/talpa/subscription/",
        views.SubscriptionView.as_view(),
        name="subscription-notify",
    ),
    path(
        "gdpr-api/v1/profiles/<str:id>",
        views.ParkingPermitsGDPRAPIView.as_view(),
        name="gdpr_v1",
    ),
    path(
        "api/reporting/permit-count-snapshots",
        views.PermitCountSnapshotView.as_view(),
        name="permit-count-snapshot-list",
    ),
    path("export/<str:data_type>", views.csv_export, name="export"),
    path("export_pdf", views.pdf_export, name="export_pdf"),
]
