from rest_framework import serializers


class MetaItemSerializer(serializers.Serializer):
    key = serializers.CharField(help_text="Meta id")
    value = serializers.CharField(help_text="Meta value")


class OrderItemSerializer(serializers.Serializer):
    meta = MetaItemSerializer(many=True)


class TalpaPayloadSerializer(serializers.Serializer):
    userId = serializers.CharField(help_text="User id")
    orderItem = OrderItemSerializer()


class RightOfPurchaseResponseSerializer(serializers.Serializer):
    errorMessage = serializers.CharField(help_text="Error if exists", default="")
    rightOfPurchase = serializers.BooleanField(help_text="Has rights to purchase")
    userId = serializers.CharField(help_text="User id")


class ResolvePriceResponseSerializer(serializers.Serializer):
    rowPriceNet = serializers.FloatField(help_text="Row price net")
    rowPriceVat = serializers.FloatField(help_text="Row price vat")
    rowPriceTotal = serializers.FloatField(help_text="Row price total")
    priceNet = serializers.FloatField(help_text="Total net price")
    priceVat = serializers.FloatField(help_text="Total vat")
    priceGross = serializers.FloatField(help_text="Gross price")
    vatPercentage = serializers.FloatField(help_text="Vat percentage")


class OrderSerializer(serializers.Serializer):
    orderId = serializers.CharField(help_text="Id of a generated order")
    eventType = serializers.ChoiceField(
        help_text="Event types", choices=["PAYMENT_PAID"], default="PAYMENT_PAID"
    )


class ResolveAvailabilitySerializer(serializers.Serializer):
    productId = serializers.CharField(help_text="Shared product id")


class ResolveAvailabilityResponseSerializer(ResolveAvailabilitySerializer):
    value = serializers.BooleanField(default=True)


class MessageResponseSerializer(serializers.Serializer):
    message = serializers.CharField(help_text="Success or error message")
