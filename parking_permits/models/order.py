import logging

import requests
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models, transaction
from django.utils import timezone as tz
from django.utils.translation import gettext_lazy as _
from helsinki_gdpr.models import SerializableMixin

from ..exceptions import (
    OrderCancelError,
    OrderCreationFailed,
    OrderValidationError,
    SubscriptionCancelError,
)
from ..services.mail import RefundEmailType, send_refund_email
from ..utils import diff_months_ceil, end_date_to_datetime, start_date_to_datetime
from .customer import Customer
from .mixins import TimestampedModelMixin, UserStampedModelMixin
from .parking_permit import (
    ContractType,
    ParkingPermit,
    ParkingPermitEventFactory,
    ParkingPermitStatus,
)
from .product import Product
from .refund import Refund

logger = logging.getLogger("db")


class OrderValidator:
    @staticmethod
    def validate_order(order_id, user_id):
        headers = {
            "api-key": settings.TALPA_API_KEY,
            "namespace": settings.NAMESPACE,
            "Content-Type": "application/json",
        }
        response = requests.get(
            f"{settings.TALPA_ORDER_EXPERIENCE_API}/admin/{order_id}",
            headers=headers,
        )
        if response.status_code == 200:
            order = response.json()
            if order["user"] != str(user_id):
                logger.error(
                    f"Talpa order user id {order['userId']} does not match with user id {user_id}"
                )
                raise OrderValidationError(
                    f"Talpa order user id {order['userId']} does not match with user id {user_id}"
                )
            logger.info("Talpa order is valid")
            return order
        else:
            logger.error("Talpa order is not valid")
            raise OrderValidationError("Talpa order is not valid")


class OrderPaymentType(models.TextChoices):
    ONLINE_PAYMENT = "ONLINE_PAYMENT", _("Online payment")
    CASHIER_PAYMENT = "CASHIER_PAYMENT", _("Cashier payment")


class OrderStatus(models.TextChoices):
    DRAFT = "DRAFT", _("Draft")
    CONFIRMED = "CONFIRMED", _("Confirmed")
    CANCELLED = "CANCELLED", _("Cancelled")


class OrderType(models.TextChoices):
    CREATED = "CREATED", _("Created")
    VEHICLE_CHANGED = "VEHICLE_CHANGED", _("Vehicle changed")
    ADDRESS_CHANGED = "ADDRESS_CHANGED", _("Address changed")


class OrderManager(SerializableMixin.SerializableManager):
    def _validate_permits(self, permits):
        if len(permits) > 2:
            raise OrderCreationFailed("More than 2 draft permits found")
        if len(permits) == 2:
            if permits[0].contract_type != permits[1].contract_type:
                raise OrderCreationFailed("Permits contract types do not match")
            if permits[0].customer_id != permits[1].customer_id:
                raise OrderCreationFailed("Permits customer do not match")

    @transaction.atomic
    def create_for_permits(self, permits, status=OrderStatus.DRAFT, **kwargs):
        self._validate_permits(permits)

        paid_time = tz.now() if status == OrderStatus.CONFIRMED else None
        first_permit = permits[0]
        order = Order.objects.create(
            customer=first_permit.customer,
            status=status,
            paid_time=paid_time,
            address_text=str(first_permit.address) if first_permit else None,
            parking_zone_name=first_permit.parking_zone.name if first_permit else None,
        )

        for permit in permits:
            order.vehicles.append(permit.vehicle.registration_number)
            order.save()
            products_with_quantity = permit.get_products_with_quantities()
            for product, quantity, date_range in products_with_quantity:
                if quantity > 0:
                    unit_price = product.get_modified_unit_price(
                        permit.vehicle.is_low_emission, permit.is_secondary_vehicle
                    )
                    start_date, end_date = date_range
                    if permit.is_open_ended:
                        end_date = tz.localdate(permit.current_period_end_time)
                    OrderItem.objects.create(
                        order=order,
                        product=product,
                        permit=permit,
                        unit_price=unit_price,
                        payment_unit_price=unit_price,
                        vat=product.vat,
                        quantity=quantity,
                        start_time=start_date_to_datetime(start_date),
                        end_time=end_date_to_datetime(end_date),
                    )
            ParkingPermitEventFactory.make_create_order_event(
                permit, order, created_by=kwargs.get("user", None)
            )

        order.permits.add(*permits)
        return order

    def _validate_customer_permits(self, permits):
        date_ranges = []
        for permit in permits:
            if permit.status != ParkingPermitStatus.VALID:
                raise OrderCreationFailed(
                    "Cannot create renewal order for non-valid permits"
                )
            if permit.is_open_ended:
                raise OrderCreationFailed(
                    "Cannot create renewal order for open ended permits"
                )

            start_date = tz.localdate(permit.next_period_start_time)
            end_date = tz.localdate(permit.end_time)
            date_ranges.append([start_date, end_date])

        if all([start_date >= end_date for start_date, end_date in date_ranges]):
            raise OrderCreationFailed(
                "Cannot create renewal order. All permits are ending or ended already."
            )

    @transaction.atomic
    def create_renewal_order(
        self,
        customer,
        status=OrderStatus.DRAFT,
        order_type=OrderType.CREATED,
        payment_type=OrderPaymentType.ONLINE_PAYMENT,
        create_renew_order_event=True,
        **kwargs,
    ):
        """
        Create new order for updated permits information that affect
        permit prices, e.g. change address or change vehicle.
        """
        customer_permits = ParkingPermit.objects.active().filter(
            contract_type=ContractType.FIXED_PERIOD, customer=customer
        )
        self._validate_customer_permits(customer_permits)

        first_permit = customer_permits.first()
        new_order = Order.objects.create(
            customer=customer,
            status=status,
            type=order_type,
            payment_type=payment_type,
            address_text=str(first_permit.address) if first_permit else None,
            parking_zone_name=first_permit.parking_zone.name if first_permit else None,
        )
        if order_type == OrderType.CREATED:
            new_order.paid_time = tz.now()
            new_order.save()

        for permit in customer_permits:
            new_order.vehicles.append(permit.vehicle.registration_number)
            new_order.save()
            start_date = tz.localdate(permit.next_period_start_time)
            end_date = tz.localdate(permit.end_time)
            if start_date >= end_date:
                # permit already ended or will be ended after current month period
                continue

            order_item_detail_list = permit.get_unused_order_items()
            product_detail_list = permit.get_products_with_quantities()

            order_item_detail_iter = iter(order_item_detail_list)
            product_detail_iter = iter(product_detail_list)

            order_item_detail = next(order_item_detail_iter, None)
            product_detail = next(product_detail_iter, None)

            while order_item_detail and product_detail:
                product, product_quantity, product_date_range = product_detail
                product_start_date, product_end_date = product_date_range
                (
                    order_item,
                    order_item_quantity,
                    order_item_date_range,
                ) = order_item_detail
                order_item_start_date, order_item_end_date = order_item_date_range

                # find the period in which the months have the same payment price
                period_start_date = max(product_start_date, order_item_start_date)
                period_end_date = min(product_end_date, order_item_end_date)
                period_quantity = diff_months_ceil(period_start_date, period_end_date)

                if period_quantity and period_start_date >= period_end_date:
                    raise ValueError(
                        "Error on product date ranges or order item date ranges"
                    )

                vehicle = permit.next_vehicle if permit.next_vehicle else permit.vehicle
                is_low_emission = vehicle.is_low_emission
                unit_price = product.get_modified_unit_price(
                    is_low_emission, permit.is_secondary_vehicle
                )
                if vehicle._is_low_emission != is_low_emission:
                    vehicle._is_low_emission = is_low_emission
                    vehicle.save()

                # the price the customer needs to pay after deducting the price
                # that the customer has already paid in previous order for this
                # order item
                payment_unit_price = unit_price - order_item.unit_price
                OrderItem.objects.create(
                    order=new_order,
                    product=product,
                    permit=permit,
                    unit_price=unit_price,
                    payment_unit_price=payment_unit_price,
                    vat=product.vat,
                    quantity=period_quantity,
                    start_time=start_date_to_datetime(start_date),
                    end_time=end_date_to_datetime(end_date),
                )

                if product_end_date < order_item_end_date:
                    # current product ended but order item is not
                    product_detail = next(product_detail_iter, None)
                elif product_end_date > order_item_end_date:
                    # current order item is ended but product is not
                    order_item_detail = next(order_item_detail_iter, None)
                else:
                    # when the end dates from product and order items are the same
                    product_detail = next(product_detail_iter, None)
                    order_item_detail = next(order_item_detail_iter, None)

            if create_renew_order_event:
                ParkingPermitEventFactory.make_renew_order_event(
                    permit,
                    new_order,
                    created_by=kwargs.get("user", None),
                )

        # permits should be added to new order after all
        # calculation and processing are done
        new_order.permits.add(*customer_permits)

        return new_order


class Order(SerializableMixin, TimestampedModelMixin, UserStampedModelMixin):
    talpa_order_id = models.UUIDField(
        _("Talpa order id"), unique=True, editable=False, null=True, blank=True
    )
    talpa_checkout_url = models.URLField(_("Talpa checkout url"), blank=True)
    talpa_logged_in_checkout_url = models.URLField(
        _("Talpa logged in checkout url"), blank=True
    )
    talpa_receipt_url = models.URLField(_("Talpa receipt_url"), blank=True)
    talpa_last_valid_purchase_time = models.DateTimeField(
        _("Talpa last valid purchase time"), blank=True, null=True
    )
    payment_type = models.CharField(
        _("Payment type"),
        max_length=50,
        choices=OrderPaymentType.choices,
        default=OrderPaymentType.CASHIER_PAYMENT,
    )
    customer = models.ForeignKey(
        Customer,
        verbose_name=_("Customer"),
        related_name="orders",
        on_delete=models.PROTECT,
    )
    status = models.CharField(
        _("Order status"),
        max_length=50,
        choices=OrderStatus.choices,
        default=OrderStatus.DRAFT,
    )
    paid_time = models.DateTimeField(_("Paid time"), blank=True, null=True)
    permits = models.ManyToManyField(
        ParkingPermit, verbose_name=_("permits"), related_name="orders"
    )
    address_text = models.CharField(_("Address"), max_length=64, blank=True, null=True)
    parking_zone_name = models.CharField(
        _("Parking zone"), max_length=32, blank=True, null=True
    )
    vehicles = ArrayField(
        models.CharField(max_length=24), verbose_name=_("Vehicles"), default=list
    )
    type = models.CharField(
        _("Order type"),
        max_length=50,
        choices=OrderType.choices,
        default=OrderType.CREATED,
    )
    objects = OrderManager()

    serialize_fields = (
        {"name": "id"},
        {"name": "status"},
        {"name": "order_items"},
    )

    class Meta:
        verbose_name = _("Order")
        verbose_name_plural = _("Orders")

    def __str__(self):
        return f"Order #{self.id} ({self.status})"

    @property
    def is_confirmed(self):
        return self.status == OrderStatus.CONFIRMED

    @property
    def order_permits(self):
        return self.permits.all()

    @property
    def order_items_content(self):
        return self.order_items.all()

    @property
    def total_price(self):
        return sum([item.total_price for item in self.order_items.all()])

    @property
    def total_price_net(self):
        return sum([item.total_price_net for item in self.order_items.all()])

    @property
    def total_price_vat(self):
        return sum([item.total_price_vat for item in self.order_items.all()])

    @property
    def total_payment_price(self):
        return sum([item.total_payment_price for item in self.order_items.all()])

    @property
    def total_payment_price_net(self):
        return sum([item.total_payment_price_net for item in self.order_items.all()])

    @property
    def total_payment_price_vat(self):
        return sum([item.total_payment_price_vat for item in self.order_items.all()])

    def _cancel_talpa_order(self, talpa_order_id):
        headers = {
            "api-key": settings.TALPA_API_KEY,
            "namespace": settings.NAMESPACE,
            "Content-Type": "application/json",
        }
        response = requests.post(
            f"{settings.TALPA_ORDER_EXPERIENCE_API}/{talpa_order_id}/cancel",
            headers=headers,
        )
        if response.status_code == 200:
            logger.info(f"Talpa order cancelling successful: {talpa_order_id}")
            return True
        else:
            logger.error("Talpa order cancelling failed")
            logger.error(
                "Talpa order cancelling failed."
                f"Error: {response.status_code} {response.reason}. "
                f"Detail: {response.text}"
            )
            raise OrderCancelError(
                "Talpa order cancelling failed."
                f"Error: {response.status_code} {response.reason}."
            )

    @transaction.atomic
    def cancel(self, talpa_order_id=None, cancel_from_talpa=True):
        logger.info(f"Cancelling order: {talpa_order_id}")
        order = Order.objects.get(talpa_order_id=talpa_order_id)

        try:
            OrderValidator.validate_order(talpa_order_id, order.customer.user.uuid)
        except OrderValidationError as e:
            logger.error(f"Order validation failed. Error = {e}")
            return False

        # Try to cancel order from Talpa as well
        if cancel_from_talpa:
            try:
                self._cancel_talpa_order(talpa_order_id)
            except OrderCancelError:
                logger.warning(
                    "Talpa order cancelling failed. Continuing the cancel process.."
                )
        order.status = OrderStatus.CANCELLED
        order.save()
        return True


class SubscriptionStatus(models.TextChoices):
    CONFIRMED = "CONFIRMED", _("Confirmed")
    CANCELLED = "CANCELLED", _("Cancelled")


class SubscriptionCancelReason(models.TextChoices):
    RENEWAL_FAILED = "RENEWAL_FAILED", _("Renewal failed")
    USER_CANCELLED = "USER_CANCELLED", _("User cancelled")


class Subscription(SerializableMixin, TimestampedModelMixin, UserStampedModelMixin):
    talpa_subscription_id = models.UUIDField(
        _("Talpa subscription id"), unique=True, editable=False, null=True, blank=True
    )
    status = models.CharField(
        _("Status"), max_length=20, choices=SubscriptionStatus.choices
    )
    cancel_reason = models.CharField(
        _("Cancel reason"),
        max_length=20,
        choices=SubscriptionCancelReason.choices,
        null=True,
        blank=True,
    )

    serialize_fields = ({"name": "status"},)

    class Meta:
        verbose_name = _("Subscription")
        verbose_name_plural = _("Subscriptions")

    def __str__(self):
        return f"Subscription #{self.talpa_subscription_id}"

    def _cancel_talpa_subcription(self):
        headers = {
            "api-key": settings.TALPA_API_KEY,
            "namespace": settings.NAMESPACE,
            "Content-Type": "application/json",
        }
        response = requests.post(
            f"{settings.TALPA_ORDER_EXPERIENCE_API}/subcription/{self.talpa_subscription_id}/cancel",
            headers=headers,
        )
        if response.status_code == 200:
            logger.info(
                f"Talpa subscription cancelling successful: {self.talpa_subscription_id}"
            )
            return True
        else:
            logger.error("Talpa subscription cancelling failed")
            logger.error(
                "Talpa subscription cancelling failed."
                f"Error: {response.status_code} {response.reason}. "
                f"Detail: {response.text}"
            )
            raise SubscriptionCancelError(
                "Talpa subscription cancelling failed."
                f"Error: {response.status_code} {response.reason}."
            )

    @transaction.atomic
    def cancel(self, cancel_reason, cancel_from_talpa=True):
        logger.info(f"Cancelling subscription: {self.talpa_subscription_id}")

        order_item = self.order_items.first()
        order = order_item.order
        talpa_order_id = order.talpa_order_id
        permit = order_item.permit

        try:
            OrderValidator.validate_order(talpa_order_id, permit.customer.user.uuid)
        except OrderValidationError as e:
            logger.error(f"Order validation failed. Error = {e}")
            return False

        # Try to cancel subscription from Talpa as well
        if cancel_from_talpa:
            try:
                self._cancel_talpa_subcription()
            except SubscriptionCancelError:
                logger.warning(
                    "Talpa subscription cancelling failed. Continuing the cancel process.."
                )

        self.status = SubscriptionStatus.CANCELLED
        self.cancel_reason = cancel_reason
        self.save()

        remaining_valid_order_subscriptions = Subscription.objects.filter(
            order_items__order__talpa_order_id__exact=talpa_order_id,
            status=SubscriptionStatus.CONFIRMED,
        )
        # Mark the order as cancelled if it has no active subscriptions left
        if not remaining_valid_order_subscriptions.exists():
            order.cancel(
                talpa_order_id=talpa_order_id, cancel_from_talpa=cancel_from_talpa
            )

        # Create a refund for a remaining full month period, if it was charged already
        if permit.end_time and permit.end_time - relativedelta(months=1) > tz.now():
            logger.info(f"Creating Refund for permit {str(permit.id)}")
            refund = Refund.objects.create(
                name=permit.customer.full_name,
                order=order,
                amount=order_item.product.unit_price,
                description=f"Refund for ending permit {str(permit.id)}",
            )
            send_refund_email(RefundEmailType.CREATED, permit.customer, refund)
            ParkingPermitEventFactory.make_create_refund_event(
                permit, refund, created_by=permit.customer.user
            )
            logger.info(f"Refund for permit {str(permit.id)} created successfully")

        logger.info(f"Subscription {self} cancelled successfully")
        return True


class OrderItem(SerializableMixin, TimestampedModelMixin):
    talpa_order_item_id = models.UUIDField(
        _("Talpa order item id"), unique=True, editable=False, null=True, blank=True
    )
    order = models.ForeignKey(
        Order,
        verbose_name=_("Order"),
        related_name="order_items",
        on_delete=models.PROTECT,
    )
    subscription = models.ForeignKey(
        Subscription,
        verbose_name=_("Subscription"),
        related_name="order_items",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    product = models.ForeignKey(
        Product, verbose_name=_("Product"), on_delete=models.PROTECT
    )
    permit = models.ForeignKey(
        ParkingPermit,
        verbose_name=_("Parking permit"),
        related_name="order_items",
        on_delete=models.PROTECT,
    )
    unit_price = models.DecimalField(_("Unit price"), max_digits=6, decimal_places=2)
    payment_unit_price = models.DecimalField(
        _("Payment unit price"), max_digits=6, decimal_places=2
    )
    vat = models.DecimalField(_("VAT"), max_digits=6, decimal_places=4)
    quantity = models.IntegerField(_("Quantity"))
    start_time = models.DateTimeField(_("Start time"), null=True, blank=True)
    end_time = models.DateTimeField(_("End time"), blank=True, null=True)

    serialize_fields = (
        {"name": "product", "accessor": lambda x: str(x)},
        {"name": "unit_price"},
        {"name": "vat_percentage"},
        {"name": "quantity"},
        {"name": "start_date"},
        {"name": "end_date"},
    )

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

    @property
    def payment_unit_price_net(self):
        return self.payment_unit_price * (1 - self.vat)

    @property
    def payment_unit_price_vat(self):
        return self.payment_unit_price * self.vat

    @property
    def total_payment_price(self):
        return self.quantity * self.payment_unit_price

    @property
    def total_payment_price_net(self):
        return self.total_payment_price * (1 - self.vat)

    @property
    def total_payment_price_vat(self):
        return self.total_payment_price * self.vat
