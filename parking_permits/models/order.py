import logging

from django.db import models, transaction
from django.utils.translation import gettext_lazy as _

from parking_permits.mixins import TimestampedModelMixin, UUIDPrimaryKeyMixin

from ..exceptions import OrderCreationFailed
from .customer import Customer
from .parking_permit import ContractType, ParkingPermit, ParkingPermitStatus
from .product import Product

logger = logging.getLogger(__name__)


class OrderType(models.TextChoices):
    ORDER = "ORDER", _("Order")
    SUBSCRIPTION = "SUBSCRIPTION", _("Subscription")


class OrderStatus(models.TextChoices):
    DRAFT = "DRAFT", _("Draft")
    CONFIRMED = "CONFIRMED", _("Confirmed")
    CANCELLED = "CANCELLED", _("Cancelled")


class OrderManager(models.Manager):
    @transaction.atomic
    def create_for_customer(self, customer):
        permits = ParkingPermit.objects.filter(
            customer=customer, status=ParkingPermitStatus.DRAFT
        )

        if len(permits) > 2:
            raise OrderCreationFailed("More than 2 draft permits found")
        if len(permits) == 2 and permits[0].contract_type != permits[1].contract_type:
            raise OrderCreationFailed("Permit contract types do not match")

        if permits[0].contract_type == ContractType.OPEN_ENDED:
            order_type = OrderType.SUBSCRIPTION
        else:
            order_type = OrderType.ORDER

        order = Order.objects.create(customer=customer, order_type=order_type)
        for permit in permits:
            products_with_quantity = permit.get_products_with_quantities()
            for product, quantity in products_with_quantity:
                OrderItem.objects.create(
                    order=order,
                    product=product,
                    permit=permit,
                    unit_price=product.unit_price,
                    vat=product.vat,
                    quantity=quantity,
                )

        return order


class Order(TimestampedModelMixin, UUIDPrimaryKeyMixin):
    talpa_order_id = models.UUIDField(
        _("Talpa order id"), unique=True, editable=False, null=True, blank=True
    )
    talpa_subscription_id = models.UUIDField(
        _("Talpa subscription id"), unique=True, editable=False, null=True, blank=True
    )
    talpa_checkout_url = models.URLField(_("Talpa checkout url"), blank=True)
    talpa_receipt_url = models.URLField(_("Talpa receipt_url"), blank=True)
    customer = models.ForeignKey(
        Customer,
        verbose_name=_("Customer"),
        related_name="orders",
        on_delete=models.PROTECT,
    )
    order_type = models.CharField(
        _("Order type"),
        max_length=50,
        choices=OrderType.choices,
        default=OrderType.ORDER,
    )
    status = models.CharField(
        _("Order status"),
        max_length=50,
        choices=OrderStatus.choices,
        default=OrderStatus.DRAFT,
    )
    objects = OrderManager()

    class Meta:
        verbose_name = _("Order")
        verbose_name_plural = _("Orders")

    def __str__(self):
        return f"Order: {self.id} ({self.order_type})"

    @property
    def total_price(self):
        return sum([item.total_price for item in self.order_items.all()])

    @property
    def total_price_net(self):
        return sum([item.total_price_net for item in self.order_items.all()])

    @property
    def total_price_vat(self):
        return sum([item.total_price_vat for item in self.order_items.all()])


class OrderItem(TimestampedModelMixin, UUIDPrimaryKeyMixin):
    talpa_order_item_id = models.UUIDField(
        _("Talpa order item id"), unique=True, editable=False, null=True, blank=True
    )
    order = models.ForeignKey(
        Order,
        verbose_name=_("Order"),
        related_name="order_items",
        on_delete=models.PROTECT,
    )
    product = models.ForeignKey(
        Product, verbose_name=_("Product"), on_delete=models.PROTECT
    )
    permit = models.ForeignKey(
        ParkingPermit,
        verbose_name=_("Parking permit"),
        related_name="order_item",
        on_delete=models.PROTECT,
    )
    unit_price = models.DecimalField(_("Unit price"), max_digits=6, decimal_places=2)
    vat = models.DecimalField(_("VAT"), max_digits=6, decimal_places=4)
    quantity = models.IntegerField(_("Quantity"))

    class Meta:
        verbose_name = _("Order item")
        verbose_name_plural = _("Order items")

    def __str__(self):
        return f"Order item: {self.id}"

    @property
    def vat_percentage(self):
        return self.vat * 100

    @property
    def unit_price_net(self):
        return self.unit_price * (1 - self.vat)

    @property
    def unit_price_vat(self):
        return self.unit_price * self.vat

    @property
    def total_price(self):
        return self.quantity * self.unit_price

    @property
    def total_price_net(self):
        return self.total_price * (1 - self.vat)

    @property
    def total_price_vat(self):
        return self.total_price * self.vat
