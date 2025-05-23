import logging
from decimal import Decimal
from urllib.parse import urljoin

import requests
from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models, transaction
from django.utils import timezone as tz
from django.utils.translation import gettext_lazy as _
from helsinki_gdpr.models import SerializableMixin

from ..constants import DEFAULT_VAT
from ..exceptions import (
    OrderCancelError,
    OrderCreationFailed,
    OrderValidationError,
    SubscriptionCancelError,
    SubscriptionValidationError,
)
from ..utils import (
    calc_net_price,
    calc_vat_price,
    diff_months_ceil,
    end_date_to_datetime,
    get_meta_item,
    start_date_to_datetime,
)
from .customer import Customer
from .mixins import TimestampedModelMixin, UserStampedModelMixin
from .parking_permit import (
    ParkingPermit,
    ParkingPermitEventFactory,
    ParkingPermitStatus,
)
from .product import Product

logger = logging.getLogger("db")

DATE_FORMAT = "%d.%m.%Y"


class OrderValidator:
    @staticmethod
    def validate_order(order_id, user_id):
        headers = {
            "api-key": settings.TALPA_API_KEY,
            "namespace": settings.NAMESPACE,
            "Content-Type": "application/json",
        }
        response = requests.get(
            urljoin(settings.TALPA_ORDER_EXPERIENCE_API, f"admin/{order_id}"),
            headers=headers,
        )
        if response.ok:
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


class SubscriptionValidator:
    @staticmethod
    def get_subscription_info(data, subscription_id, order_id, order_item_id):
        for subscription in data.get("subscriptions"):
            if subscription.get("subscriptionId") == str(subscription_id):
                meta = subscription.get("meta")
                meta_item = get_meta_item(meta, "permitId")
                if not meta_item:
                    msg = "No permitId key available in meta list of key-value pairs"
                    logger.error(msg)
                    raise SubscriptionValidationError(msg)
                meta_permit_id = meta_item.get("value")
                meta_subscription_id = meta_item.get("subscriptionId")
                meta_order_id = meta_item.get("orderId")
                meta_order_item_id = meta_item.get("orderItemId")
                if meta_permit_id is None:
                    msg = "No permitId key available in meta list of key-value pairs"
                    logger.error(msg)
                    raise SubscriptionValidationError(msg)
                if meta_subscription_id is None or meta_subscription_id != str(
                    subscription_id
                ):
                    msg = f"Subscription id does not match with the requested subscription id value {subscription_id}"
                    logger.error(msg)
                    raise SubscriptionValidationError(msg)
                if meta_order_id is None or meta_order_id != str(order_id):
                    msg = f"Order id does not match with the requested order id value: {order_id}"
                    logger.error(msg)
                    raise SubscriptionValidationError(msg)
                if meta_order_item_id is None or meta_order_item_id != str(
                    order_item_id
                ):
                    msg = f"Order item id does not match with the requested order item id value: {order_item_id}"
                    logger.error(msg)
                    raise SubscriptionValidationError(msg)
                logger.info("Talpa subscription is valid")
                return subscription
        msg = f"Talpa subscription {subscription_id} not found for order {order_id}"
        logger.error(msg)
        raise SubscriptionValidationError(msg)

    @staticmethod
    def validate_subscription(user_id, subscription_id, order_id, order_item_id):
        headers = {
            "api-key": settings.TALPA_API_KEY,
            "namespace": settings.NAMESPACE,
            "user": user_id,
            "Content-Type": "application/json",
        }
        response = requests.get(
            urljoin(
                settings.TALPA_ORDER_EXPERIENCE_API,
                f"subscriptions/get-by-order-id/{order_id}",
            ),
            headers=headers,
        )
        if response.ok:
            return SubscriptionValidator.get_subscription_info(
                response.json(), subscription_id, order_id, order_item_id
            )
        else:
            msg = f"Failed to retrieve order {order_id} subscriptions from Talpa"
            logger.error(msg)
            raise SubscriptionValidationError(msg)


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
    SUBSCRIPTION_RENEWED = "SUBSCRIPTION_RENEWED", _("Subscription renewed")


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
            address_text=str(first_permit.full_address) if first_permit else None,
            parking_zone_name=first_permit.parking_zone.name if first_permit else None,
        )

        for permit in permits:
            order.vehicles.append(permit.vehicle.registration_number)
            order.save()
            first_order_item = True
            products_with_quantity = permit.get_products_with_quantities()
            for product, quantity, date_range in products_with_quantity:
                if quantity > 0:
                    unit_price = product.get_modified_unit_price(
                        permit.vehicle.is_low_emission, permit.is_secondary_vehicle
                    )
                    start_date, end_date = date_range
                    if permit.is_open_ended:
                        end_date = tz.localdate(
                            permit.current_period_end_time_with_fixed_months(1)
                        )
                    OrderItem.objects.create(
                        order=order,
                        product=product,
                        permit=permit,
                        unit_price=unit_price,
                        payment_unit_price=unit_price,
                        vat=product.vat,
                        quantity=quantity,
                        start_time=(
                            permit.start_time
                            if first_order_item
                            else start_date_to_datetime(start_date)
                        ),
                        end_time=end_date_to_datetime(end_date),
                    )
                    first_order_item = False
            ParkingPermitEventFactory.make_create_order_event(
                permit, order, created_by=kwargs.get("user", None)
            )

        order.permits.add(*permits)
        return order

    def create_for_extended_permit(
        self,
        permit,
        month_count,
        status=OrderStatus.CONFIRMED,
        **kwargs,
    ):
        paid_time = tz.now() if status == OrderStatus.CONFIRMED else None

        order = self.create(
            customer=permit.customer,
            status=status,
            paid_time=paid_time,
            address_text=str(permit.full_address),
            parking_zone_name=permit.parking_zone.name,
            vehicles=[permit.vehicle.registration_number],
            **kwargs,
        )
        order.permits.add(permit)

        order_items = [
            OrderItem(
                order=order,
                permit=permit,
                quantity=item["month_count"],
                product=item["product"],
                unit_price=item["unit_price"],
                payment_unit_price=item["unit_price"],
                vat=item["product"].vat,
                start_time=item["start_date"],
                end_time=item["end_date"],
            )
            for item in permit.get_price_list_for_extended_permit(month_count)
        ]

        OrderItem.objects.bulk_create(order_items)

        start_time, end_time = min([order.start_time for order in order_items]), max(
            [order.end_time for order in order_items]
        )

        ParkingPermitEventFactory.make_create_ext_request_order_event(
            permit, order, start_time, end_time, created_by=kwargs.get("user", None)
        )

        return order

    def _validate_customer_permits(self, permits, order_type):
        date_ranges = []
        for permit in permits:
            if permit.status != ParkingPermitStatus.VALID:
                raise OrderCreationFailed(
                    "Cannot create renewal order for non-valid permits"
                )
            if (
                permit.is_open_ended
                and order_type not in self.model.OPEN_ENDED_RENEWABLE_ORDER_TYPES
            ):
                raise OrderCreationFailed(
                    "Cannot create renewal order for open ended permits"
                )

            start_date = tz.localdate(permit.next_period_start_time)
            end_date = tz.localdate(permit.end_time)
            date_ranges.append([start_date, end_date])

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
        customer_permits = ParkingPermit.objects.filter(
            customer=customer, status=ParkingPermitStatus.VALID
        )
        self._validate_customer_permits(customer_permits, order_type)

        try:
            first_permit = customer_permits[0]
        except IndexError:
            raise OrderCreationFailed("No valid permits found for renewal order")
        new_order = Order.objects.create(
            customer=customer,
            status=status,
            type=order_type,
            payment_type=payment_type,
            address_text=str(first_permit.full_address) if first_permit else None,
            parking_zone_name=first_permit.parking_zone.name if first_permit else None,
        )
        if order_type == OrderType.CREATED:
            new_order.paid_time = tz.now()
            new_order.save()

        for permit in customer_permits:
            vehicle = permit.next_vehicle if permit.next_vehicle else permit.vehicle
            new_order.vehicles.append(vehicle.registration_number)
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
                product, _, product_date_range = product_detail
                product_start_date, product_end_date = product_date_range
                (
                    order_item,
                    _,
                    order_item_date_range,
                ) = order_item_detail
                order_item_start_date, order_item_end_date = order_item_date_range
                product_end_date = product_end_date or order_item_end_date
                # find the period in which the months have the same payment price
                period_start_date = max(product_start_date, order_item_start_date)
                period_end_date = min(product_end_date, order_item_end_date)
                period_quantity = diff_months_ceil(period_start_date, period_end_date)

                if period_quantity and period_start_date >= period_end_date:
                    raise ValueError(
                        "Error on product date ranges or order item date ranges"
                    )

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
                    start_time=start_date_to_datetime(period_start_date),
                    end_time=end_date_to_datetime(period_end_date),
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
    OPEN_ENDED_RENEWABLE_ORDER_TYPES = (
        OrderType.ADDRESS_CHANGED,
        OrderType.VEHICLE_CHANGED,
    )
    talpa_order_id = models.UUIDField(
        _("Talpa order id"), unique=True, editable=False, null=True, blank=True
    )
    talpa_checkout_url = models.URLField(_("Talpa checkout url"), blank=True)
    talpa_logged_in_checkout_url = models.URLField(
        _("Talpa logged in checkout url"), blank=True
    )
    talpa_receipt_url = models.URLField(_("Talpa receipt_url"), blank=True)

    talpa_update_card_url = models.URLField(_("Talpa update card url"), blank=True)

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
        return f"Order: {self.id} ({self.status})"

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

    @property
    def vat_values(self):
        # gather distinct vat values from all order items
        return set([item.vat for item in self.order_items.all()])

    @property
    def vat(self):
        return self.order_items.first().vat if self.order_items.exists() else Decimal(0)

    @property
    def vat_percent(self):
        return self.vat * 100

    def _cancel_talpa_order(self):
        headers = {
            "api-key": settings.TALPA_API_KEY,
            "namespace": settings.NAMESPACE,
            "user": str(self.customer.user.uuid),
            "Content-Type": "application/json",
        }
        response = requests.post(
            urljoin(
                settings.TALPA_ORDER_EXPERIENCE_API, f"{self.talpa_order_id}/cancel"
            ),
            headers=headers,
        )
        if response.status_code == 200:
            logger.info(f"Talpa order cancelling successful: {self.talpa_order_id}")
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

    def cancel(self, cancel_from_talpa=True):
        logger.info(f"Order cancel process started: {self.talpa_order_id}")
        if (
            self.talpa_order_id
            and self.customer
            and self.customer.user
            and self.customer.user.uuid
        ):
            try:
                OrderValidator.validate_order(
                    self.talpa_order_id, self.customer.user.uuid
                )
            except OrderValidationError as e:
                logger.error(f"Order validation failed. Error = {e}")
                return False
            # Try to cancel order from Talpa as well
            if cancel_from_talpa:
                try:
                    self._cancel_talpa_order()
                except OrderCancelError:
                    logger.warning(
                        "Talpa order cancelling failed. Continuing the cancel process.."
                    )
        self.status = OrderStatus.CANCELLED
        self.save()
        logger.info(f"Order {self.talpa_order_id} cancel process done")
        return True

    def get_pending_permit_extension_requests(self):
        return self.permit_extension_requests.pending()


class SubscriptionStatus(models.TextChoices):
    CONFIRMED = "CONFIRMED", _("Confirmed")
    CANCELLED = "CANCELLED", _("Cancelled")


class SubscriptionCancelReason(models.TextChoices):
    RENEWAL_FAILED = "RENEWAL_FAILED", _("Renewal failed")
    USER_CANCELLED = "USER_CANCELLED", _("User cancelled")
    PERMIT_EXPIRED = "PERMIT_EXPIRED", _("Permit expired")


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
        return f"Subscription: {self.talpa_subscription_id}"

    def _cancel_talpa_subcription(self, customer_id):
        headers = {
            "api-key": settings.TALPA_API_KEY,
            "namespace": settings.NAMESPACE,
            "user": str(customer_id),
            "Content-Type": "application/json",
        }
        response = requests.post(
            urljoin(
                settings.TALPA_ORDER_EXPERIENCE_API,
                f"subscription/{self.talpa_subscription_id}/cancel",
            ),
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

    def cancel(self, cancel_reason, cancel_from_talpa=True, iban=""):
        logger.info(
            f"Subscription cancel process started: {self.talpa_subscription_id}"
        )

        order_item = self.order_items.first()
        order = order_item.order
        talpa_order_id = order.talpa_order_id
        permit = order_item.permit
        customer_id = permit.customer.user.uuid

        if talpa_order_id and customer_id:
            try:
                OrderValidator.validate_order(talpa_order_id, customer_id)
            except OrderValidationError as e:
                logger.error(f"Order validation failed. Error = {e}")
                return False

        self.status = SubscriptionStatus.CANCELLED
        self.cancel_reason = cancel_reason
        self.save()

        if permit.can_be_refunded:
            logger.info(f"Creating Refund for permit {str(permit.id)}")
            from ..resolver_utils import create_refund

            create_refund(
                user=permit.customer.user,
                permits=[permit],
                orders=[order],
                amount=permit.total_refund_amount,
                iban=iban,
                vat=(order.vat if order.vat else DEFAULT_VAT),
                description=f"Refund for ending permit {str(permit.id)}",
            )
            # Mark the order item as refunded
            order_item.is_refunded = True
            order_item.save()
            logger.info(f"Refund for permit {str(permit.id)} created successfully")

        # Try to cancel subscription from Talpa as well
        if cancel_from_talpa:
            try:
                self._cancel_talpa_subcription(customer_id)
            except SubscriptionCancelError:
                logger.warning(
                    "Talpa subscription cancelling failed. Continuing the cancel process.."
                )

        remaining_valid_order_subscriptions = Subscription.objects.filter(
            order_items__order__talpa_order_id__exact=talpa_order_id,
            status=SubscriptionStatus.CONFIRMED,
        )
        # Mark the order as cancelled if it has no active subscriptions left
        if not remaining_valid_order_subscriptions.exists():
            order.cancel(cancel_from_talpa=cancel_from_talpa)

        logger.info(f"Subscription {self.talpa_subscription_id} cancel process done")
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
    is_refunded = models.BooleanField(default=False, verbose_name=_("Is refunded"))

    serialize_fields = (
        {"name": "product", "accessor": lambda x: str(x)},
        {"name": "unit_price"},
        {"name": "vat_percentage"},
        {"name": "quantity"},
        {"name": "start_time"},
        {"name": "end_time"},
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
        return calc_net_price(self.unit_price, self.vat)

    @property
    def unit_price_vat(self):
        return calc_vat_price(self.unit_price, self.vat)

    @property
    def total_price(self):
        return self.quantity * self.unit_price

    @property
    def total_price_net(self):
        return calc_net_price(self.total_price, self.vat)

    @property
    def total_price_vat(self):
        return calc_vat_price(self.total_price, self.vat)

    @property
    def payment_unit_price_net(self):
        return calc_net_price(self.payment_unit_price, self.vat)

    @property
    def payment_unit_price_vat(self):
        return calc_vat_price(self.payment_unit_price, self.vat)

    @property
    def total_payment_price(self):
        return self.quantity * self.payment_unit_price

    @property
    def total_payment_price_net(self):
        return calc_net_price(self.total_payment_price, self.vat)

    @property
    def total_payment_price_vat(self):
        return calc_vat_price(self.total_payment_price, self.vat)

    @property
    def timeframe(self):
        if self.start_time and self.end_time:
            start_time = tz.localtime(self.start_time).strftime(DATE_FORMAT)
            end_time = tz.localtime(self.end_time).strftime(DATE_FORMAT)
            return f"{start_time} - {end_time}"
        return ""

    def adjusted_timeframe(self, start_time):
        """
        Custom timeframe used to make sure subsequent order items don't have gaps in days
        """
        if start_time and self.end_time:
            start_time = tz.localtime(start_time).strftime(DATE_FORMAT)
            end_time = tz.localtime(self.end_time).strftime(DATE_FORMAT)
            return f"{start_time} - {end_time}"
        return ""
