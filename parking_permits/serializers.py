from django.conf import settings
from rest_framework import serializers

from parking_permits.models.reporting import PermitCountSnapshot


class MetaItemSerializer(serializers.Serializer):
    key = serializers.CharField(help_text="Meta id")
    value = serializers.CharField(help_text="Meta value")


class OrderItemSerializer(serializers.Serializer):
    meta = MetaItemSerializer(many=True)


class TalpaPayloadSerializer(serializers.Serializer):
    userId = serializers.CharField(help_text="User id")  # noqa: N815
    orderItem = OrderItemSerializer()  # noqa: N815


class RightOfPurchaseResponseSerializer(serializers.Serializer):
    rightOfPurchase = serializers.BooleanField(help_text="Has rights to purchase")  # noqa: N815
    userId = serializers.CharField(help_text="User id")  # noqa: N815
    errorMessage = serializers.CharField(help_text="Error if exists", default="")  # noqa: N815


class ResolvePriceRequestSerializer(serializers.Serializer):
    userId = serializers.CharField(help_text="User id")  # noqa: N815
    subscriptionId = serializers.CharField(help_text="Subscription id")  # noqa: N815
    orderItem = OrderItemSerializer()  # noqa: N815


class ResolvePriceResponseSerializer(serializers.Serializer):
    userId = serializers.CharField(help_text="User id")  # noqa: N815
    subscriptionId = serializers.CharField(help_text="Subscription id")  # noqa: N815
    priceNet = serializers.FloatField(help_text="Total net price")  # noqa: N815
    priceVat = serializers.FloatField(help_text="Total vat")  # noqa: N815
    priceGross = serializers.FloatField(help_text="Gross price")  # noqa: N815
    vatPercentage = serializers.FloatField(help_text="Vat percentage")  # noqa: N815
    errorMessage = serializers.CharField(help_text="Error if exists", default="")  # noqa: N815


class ResolveProductRequestSerializer(serializers.Serializer):
    userId = serializers.CharField(help_text="User id")  # noqa: N815
    subscriptionId = serializers.CharField(help_text="Subscription id")  # noqa: N815
    orderItem = OrderItemSerializer()  # noqa: N815


class ResolveProductResponseSerializer(serializers.Serializer):
    userId = serializers.CharField(help_text="User id")  # noqa: N815
    subscriptionId = serializers.CharField(help_text="Subscription id")  # noqa: N815
    productId = serializers.FloatField(help_text="Product id")  # noqa: N815
    productName = serializers.FloatField(help_text="Product name")  # noqa: N815
    productLabel = serializers.FloatField(help_text="Product label")  # noqa: N815
    errorMessage = serializers.CharField(help_text="Error if exists", default="")  # noqa: N815


class PaymentSerializer(serializers.Serializer):
    paymentId = serializers.CharField(help_text="Id of a generated payment")  # noqa: N815
    orderId = serializers.CharField(help_text="Id of a generated order")  # noqa: N815
    eventType = serializers.ChoiceField(  # noqa: N815
        help_text="Event types",
        choices=[
            "PAYMENT_PAID",
        ],
        default="PAYMENT_PAID",
    )
    namespace = serializers.CharField(
        help_text="Application namespace", default=settings.NAMESPACE
    )
    eventTimestamp = serializers.DateTimeField(help_text="Event timestamp")  # noqa: N815


class OrderSerializer(serializers.Serializer):
    orderId = serializers.CharField(help_text="Id of a generated order")  # noqa: N815
    subscriptionId = serializers.CharField(help_text="Id of a generated subscription")  # noqa: N815
    eventType = serializers.ChoiceField(  # noqa: N815
        help_text="Event types",
        choices=[
            "SUBSCRIPTION_RENEWAL_ORDER_CREATED",
        ],
        default="SUBSCRIPTION_RENEWAL_ORDER_CREATED",
    )
    namespace = serializers.CharField(
        help_text="Application namespace", default=settings.NAMESPACE
    )
    eventTimestamp = serializers.DateTimeField(help_text="Event timestamp")  # noqa: N815


class SubscriptionSerializer(serializers.Serializer):
    subscriptionId = serializers.CharField(help_text="Id of a generated subscription")  # noqa: N815
    orderId = serializers.CharField(help_text="Id of a generated order")  # noqa: N815
    namespace = serializers.CharField(  # noqa: N815
        help_text="Application namespace", default=settings.NAMESPACE
    )
    eventType = serializers.ChoiceField(  # noqa: N815
        help_text="Event types",
        choices=["SUBSCRIPTION_CREATED", "SUBSCRIPTION_CANCELLED"],
        default="SUBSCRIPTION_CREATED",
    )
    eventTimestamp = serializers.DateTimeField(help_text="Event timestamp")  # noqa: N815
    reason = serializers.ChoiceField(
        help_text="Reason for cancellation",
        choices=["RENEWAL_FAILED", "USER_CANCELLED"],
        default="RENEWAL_FAILED",
    )


class ProductSerializer(serializers.Serializer):
    id = serializers.IntegerField(help_text="Service product id")
    productId = serializers.CharField(  # noqa: N815
        help_text="Shared product id", source="talpa_product_id"
    )
    name = serializers.CharField(help_text="Product name")
    description = serializers.CharField(help_text="Product description")
    namespace = serializers.CharField(
        help_text="Product namespace", default=settings.NAMESPACE
    )


class ResolveAvailabilityRequestSerializer(serializers.Serializer):
    productId = serializers.CharField(help_text="Shared product id")  # noqa: N815


class ResolveAvailabilityResponseSerializer(ResolveAvailabilityRequestSerializer):
    value = serializers.BooleanField(default=True)


class MessageResponseSerializer(serializers.Serializer):
    message = serializers.CharField(help_text="Success or error message")


class PermitCountSnapshotSerializer(serializers.Serializer):
    permit_count = serializers.IntegerField(read_only=True)
    date = serializers.DateField(read_only=True)
    parking_zone_name = serializers.CharField(read_only=True)
    parking_zone_description = serializers.CharField(read_only=True)
    parking_zone_description_sv = serializers.CharField(read_only=True)
    low_emission = serializers.BooleanField(read_only=True)
    primary_vehicle = serializers.BooleanField(read_only=True)
    contract_type = serializers.CharField(read_only=True)

    class Meta:
        model = PermitCountSnapshot
        fields = (
            "permit_count",
            "date",
            "parking_zone_name",
            "parking_zone_description",
            "parking_zone_description_sv",
            "low_emission",
            "primary_vehicle",
            "contract_type",
        )
