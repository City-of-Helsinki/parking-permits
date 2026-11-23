from django.db import models
from django.utils.translation import gettext_lazy as _


class SourceSystem(models.TextChoices):
    HELSINKI_PROFILE = "HELSINKI_PROFILE"


class OrderStatus(models.TextChoices):
    DRAFT = "DRAFT", _("Draft")
    CONFIRMED = "CONFIRMED", _("Confirmed")
    CANCELLED = "CANCELLED", _("Cancelled")


class OrderType(models.TextChoices):
    CREATED = "CREATED", _("Created")
    VEHICLE_CHANGED = "VEHICLE_CHANGED", _("Vehicle changed")
    ADDRESS_CHANGED = "ADDRESS_CHANGED", _("Address changed")
    PRICE_ADJUSTED = "PRICE_ADJUSTED", _("Price adjustment")
    SUBSCRIPTION_RENEWED = "SUBSCRIPTION_RENEWED", _("Subscription renewed")
