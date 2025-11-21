from django.conf import settings
from rest_framework import serializers

from parking_permits.models.reporting import PermitCountSnapshot


class MetaItemSerializer(serializers.Serializer):
    key = serializers.CharField(help_text="Meta id")
    value = serializers.CharField(help_text="Meta value")


class OrderItemSerializer(serializers.Serializer):
    meta = MetaItemSerializer(many=True)


class TalpaPayloadSerializer(serializers.Serializer):
    userId = serializers.CharField(help_text="User id")
    orderItem = OrderItemSerializer()


class RightOfPurchaseResponseSerializer(serializers.Serializer):
    rightOfPurchase = serializers.BooleanField(help_text="Has rights to purchase")
    userId = serializers.CharField(help_text="User id")
    errorMessage = serializers.CharField(help_text="Error if exists", default="")


class ResolvePriceRequestSerializer(serializers.Serializer):
    userId = serializers.CharField(help_text="User id")
    subscriptionId = serializers.CharField(help_text="Subscription id")
    orderItem = OrderItemSerializer()


class ResolvePriceResponseSerializer(serializers.Serializer):
    userId = serializers.CharField(help_text="User id")
    subscriptionId = serializers.CharField(help_text="Subscription id")
    priceNet = serializers.FloatField(help_text="Total net price")
    priceVat = serializers.FloatField(help_text="Total vat")
    priceGross = serializers.FloatField(help_text="Gross price")
    vatPercentage = serializers.FloatField(help_text="Vat percentage")
    errorMessage = serializers.CharField(help_text="Error if exists", default="")


class ResolveProductRequestSerializer(serializers.Serializer):
    userId = serializers.CharField(help_text="User id")
    subscriptionId = serializers.CharField(help_text="Subscription id")
    orderItem = OrderItemSerializer()


class ResolveProductResponseSerializer(serializers.Serializer):
    userId = serializers.CharField(help_text="User id")
    subscriptionId = serializers.CharField(help_text="Subscription id")
    productId = serializers.FloatField(help_text="Product id")
    productName = serializers.FloatField(help_text="Product name")
    productLabel = serializers.FloatField(help_text="Product label")
    errorMessage = serializers.CharField(help_text="Error if exists", default="")


class PaymentSerializer(serializers.Serializer):
    paymentId = serializers.CharField(help_text="Id of a generated payment")
    orderId = serializers.CharField(help_text="Id of a generated order")
    eventType = serializers.ChoiceField(
        help_text="Event types",
        choices=[
            "PAYMENT_PAID",
        ],
        default="PAYMENT_PAID",
    )
    namespace = serializers.CharField(
        help_text="Application namespace", default=settings.NAMESPACE
    )
    eventTimestamp = serializers.DateTimeField(help_text="Event timestamp")


class OrderSerializer(serializers.Serializer):
    orderId = serializers.CharField(help_text="Id of a generated order")
    subscriptionId = serializers.CharField(help_text="Id of a generated subscription")
    eventType = serializers.ChoiceField(
        help_text="Event types",
        choices=[
            "SUBSCRIPTION_RENEWAL_ORDER_CREATED",
        ],
        default="SUBSCRIPTION_RENEWAL_ORDER_CREATED",
    )
    namespace = serializers.CharField(
        help_text="Application namespace", default=settings.NAMESPACE
    )
    eventTimestamp = serializers.DateTimeField(help_text="Event timestamp")


class SubscriptionSerializer(serializers.Serializer):
    subscriptionId = serializers.CharField(help_text="Id of a generated subscription")
    orderId = serializers.CharField(help_text="Id of a generated order")
    namespace = serializers.CharField(
        help_text="Application namespace", default=settings.NAMESPACE
    )
    eventType = serializers.ChoiceField(
        help_text="Event types",
        choices=["SUBSCRIPTION_CREATED", "SUBSCRIPTION_CANCELLED"],
        default="SUBSCRIPTION_CREATED",
    )
    eventTimestamp = serializers.DateTimeField(help_text="Event timestamp")
    reason = serializers.ChoiceField(
        help_text="Reason for cancellation",
        choices=["RENEWAL_FAILED", "USER_CANCELLED"],
        default="RENEWAL_FAILED",
    )


class ProductSerializer(serializers.Serializer):
    id = serializers.IntegerField(help_text="Service product id")
    productId = serializers.CharField(
        help_text="Shared product id", source="talpa_product_id"
    )
    name = serializers.CharField(help_text="Product name")
    description = serializers.CharField(help_text="Product description")
    namespace = serializers.CharField(
        help_text="Product namespace", default=settings.NAMESPACE
    )


class ResolveAvailabilityRequestSerializer(serializers.Serializer):
    productId = serializers.CharField(help_text="Shared product id")


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
