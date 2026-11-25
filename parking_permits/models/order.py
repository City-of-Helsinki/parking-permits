import logging
from datetime import datetime
from decimal import Decimal
from urllib.parse import urljoin

import requests
from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models, transaction
from django.utils import timezone as tz
from django.utils.translation import gettext_lazy as _
from helsinki_gdpr.models import SerializableMixin

from parking_permits.services.mail import (
    PermitEmailType,
    send_permit_email,
)
from parking_permits.services.parkkihubi import sync_with_parkkihubi

from ..exceptions import (
    OrderCancelError,
    OrderCreationFailedError,
    OrderValidationError,
    SubscriptionCancelError,
    SubscriptionValidationError,
)
from ..permit_rules import CONTRACT_TYPE_MISMATCH
from ..utils import (
    calc_net_price,
    calc_vat_price,
    diff_months_ceil,
    end_date_to_datetime,
    get_meta_item,
    start_date_to_datetime,
)
from .common import OrderStatus, OrderType
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
                    f"Talpa order user id {order['userId']} "
                    f"does not match with user id {user_id}"
                )
                raise OrderValidationError(
                    f"Talpa order user id {order['userId']} "
                    f"does not match with user id {user_id}"
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
                    msg = (
                        f"Subscription id does not match with the "
                        f"requested subscription id value {subscription_id}"
                    )
                    logger.error(msg)
                    raise SubscriptionValidationError(msg)
                if meta_order_id is None or meta_order_id != str(order_id):
                    msg = (
                        f"Order id does not match with the "
                        f"requested order id value: {order_id}"
                    )
                    logger.error(msg)
                    raise SubscriptionValidationError(msg)
                if meta_order_item_id is None or meta_order_item_id != str(
                    order_item_id
                ):
                    msg = (
                        f"Order item id does not match with the "
                        f"requested order item id value: {order_item_id}"
                    )
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


class OrderManager(SerializableMixin.SerializableManager):
    def _validate_permits(self, permits):
        if len(permits) > 2:
            raise OrderCreationFailedError("More than 2 draft permits found")
        if len(permits) == 2:
            if permits[0].contract_type != permits[1].contract_type:
                raise OrderCreationFailedError("Permits contract types do not match")
            if permits[0].customer_id != permits[1].customer_id:
                raise OrderCreationFailedError("Permits customer do not match")

    @transaction.atomic
    def create_for_permits(self, permits, status=OrderStatus.DRAFT, **kwargs):
        self._validate_permits(permits)
        first_permit = permits[0]
        if first_permit.has_conflicting_contract_type():
            raise OrderCreationFailedError(CONTRACT_TYPE_MISMATCH)
        for permit in permits:
            permit.validate_purchase()

        paid_time = tz.now() if status == OrderStatus.CONFIRMED else None
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
                    regular, discounted = product.tariff_prices(
                        permit.is_secondary_vehicle
                    )
                    unit_price = (
                        discounted if permit.vehicle.is_low_emission else regular
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
                        regular_unit_price=regular,
                        discounted_unit_price=discounted,
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
        permit.validate_extension(month_count)
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

        order_items = []
        for item in permit.get_price_list_for_extended_permit(month_count=month_count):
            product = item["product"]
            regular, discounted = product.tariff_prices(permit.is_secondary_vehicle)
            order_items.append(
                OrderItem(
                    order=order,
                    permit=permit,
                    product=product,
                    quantity=item["month_count"],
                    regular_unit_price=regular,
                    discounted_unit_price=discounted,
                    unit_price=item["unit_price"],
                    payment_unit_price=item["unit_price"],
                    vat=product.vat,
                    start_time=item["start_date"],
                    end_time=item["end_date"],
                )
            )

        OrderItem.objects.bulk_create(order_items)

        start_time, end_time = (
            min([order.start_time for order in order_items]),
            max([order.end_time for order in order_items]),
        )

        ParkingPermitEventFactory.make_create_ext_request_order_event(
            permit,
            order,
            datetime.combine(start_time, datetime.min.time()),
            datetime.combine(end_time, datetime.max.time()),
            created_by=kwargs.get("user", None),
        )

        return order

    def _validate_customer_permits(self, permits, order_type):
        date_ranges = []
        for permit in permits:
            if permit.status != ParkingPermitStatus.VALID:
                raise OrderCreationFailedError(
                    "Cannot create renewal order for non-valid permits"
                )
            if (
                permit.is_open_ended
                and order_type not in self.model.OPEN_ENDED_RENEWABLE_ORDER_TYPES
            ):
                raise OrderCreationFailedError(
                    "Cannot create renewal order for open ended permits"
                )

            start_date = permit.next_period_start_time
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
        price_changes=None,
        **kwargs,
    ):
        """
        Create new order for updated permits information that affect
        permit prices, e.g. change address or change vehicle.
        """
        customer_permits = ParkingPermit.objects.filter(
            customer=customer, status=ParkingPermitStatus.VALID
        )
        if price_changes is not None:
            customer_permits = customer_permits.filter(pk__in=price_changes)
            if len(customer_permits) != len(price_changes):
                raise OrderCreationFailedError(
                    "Permit is no longer valid for a price change"
                )
        self._validate_customer_permits(customer_permits, order_type)

        try:
            first_permit = customer_permits[0]
        except IndexError:
            raise OrderCreationFailedError("No valid permits found for renewal order")
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
            if permit.is_fixed_period:
                if price_changes is None:
                    lines = permit.fixed_period_price_changes(
                        permit.next_parking_zone or permit.parking_zone,
                        vehicle.is_low_emission,
                        use_item_price=True,
                    )
                else:
                    lines = price_changes[permit.pk]
                for line in lines:
                    regular, discounted = line["tariff_prices"]
                    OrderItem.objects.create(
                        order=new_order,
                        permit=permit,
                        product=line["tariff_product"],
                        regular_unit_price=regular,
                        discounted_unit_price=discounted,
                        unit_price=line["new_price"],
                        payment_unit_price=line["price_change"],
                        vat=line["price_change_vat_percent"] / 100,
                        quantity=line["month_count"],
                        start_time=start_date_to_datetime(line["start_date"]),
                        end_time=end_date_to_datetime(line["end_date"]),
                    )
            else:
                self._create_open_ended_renewal_items(new_order, permit, vehicle)

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

    def _create_open_ended_renewal_items(self, order, permit, vehicle):
        if permit.next_period_start_time >= tz.localdate(permit.end_time):
            return
        product, _, _ = permit.get_products_with_quantities()[0]
        for item, _, (start, end) in permit.get_unused_order_items():
            price = product.get_modified_unit_price(
                is_low_emission=vehicle.is_low_emission,
                is_secondary=permit.is_secondary_vehicle,
            )
            OrderItem.objects.create(
                order=order,
                permit=permit,
                product=product,
                unit_price=price,
                payment_unit_price=price - item.unit_price,
                vat=product.vat,
                quantity=diff_months_ceil(start, end),
                start_time=start_date_to_datetime(start),
                end_time=end_date_to_datetime(end),
            )


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
        choices=OrderPaymentType,
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
        choices=OrderStatus,
        default=OrderStatus.DRAFT,
    )
    paid_time = models.DateTimeField(_("Paid time"), blank=True, null=True)
    payment_processed_at = models.DateTimeField(
        _("Payment notification processed at"), null=True, blank=True, editable=False
    )
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
        choices=OrderType,
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

    def process_order_extension_requests(self) -> None:
        """
        Approve the latest pending permit extension request of the
        order if such exists. Any possible remaining pending permit
        extension requests of the order are cancelled after the
        approval.
        """

        ext_request = (
            self.get_pending_permit_extension_requests().select_related("permit").last()
        )
        # NOTE: early return if there are no matching requests to pick
        # the last one from as there will be nothing left to cancel.
        if ext_request is None:
            return

        ext_request.approve()
        ParkingPermitEventFactory.make_approve_ext_request_event(ext_request)
        sync_with_parkkihubi(ext_request.permit)
        send_permit_email(PermitEmailType.EXTENDED, ext_request.permit)
        logger.info(
            f"Permit {ext_request.permit.pk} extended, new permit validity period is:"
            f" {ext_request.permit.start_time} - {ext_request.permit.end_time}"
        )

        # NOTE: While the data model would allow for an order to have
        # multiple extension requests that would be linked to different
        # permit-instances, this _should_ not happen in practice. All
        # GraphQL-resolvers handling extension request creation logic
        # also create a new order that the request will be linked to.
        # Hence we assume that all the earlier extension requests
        # linked to the order can be cancelled. (These should not even
        # exist due to the reason above.)
        self.permit_extension_requests.cancel_pending()


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
    status = models.CharField(_("Status"), max_length=20, choices=SubscriptionStatus)
    cancel_reason = models.CharField(
        _("Cancel reason"),
        max_length=20,
        choices=SubscriptionCancelReason,
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
                f"Talpa subscription cancelling successful: "
                f"{self.talpa_subscription_id}"
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

    def cancel(self, cancel_reason, cancel_from_talpa=True, ignore_talpa_errors=False):
        """
        Cancel the subscription locally and, if `cancel_from_talpa`, in Talpa.

        Talpa errors raise `SubscriptionCancelError` so that the caller's
        transaction rolls back. With `ignore_talpa_errors` they are only
        logged, e.g. so that expired permits still end in the daily cron.
        Refunds are not handled here; see `resolver_utils.end_permits`.
        """
        logger.info(
            f"Subscription cancel process started: {self.talpa_subscription_id}"
        )

        order_item = self.order_items.first()
        order = order_item.order
        talpa_order_id = order.talpa_order_id
        permit = order_item.permit
        customer_id = permit.customer.user.uuid

        # Without cancel_from_talpa, Talpa has already cancelled the subscription.
        if cancel_from_talpa:
            try:
                if talpa_order_id and customer_id:
                    OrderValidator.validate_order(talpa_order_id, customer_id)
                self._cancel_talpa_subcription(customer_id)
            except (
                OrderValidationError,
                SubscriptionCancelError,
                requests.RequestException,
            ) as e:
                logger.exception(
                    "Talpa subscription %s cancelling failed.",
                    self.talpa_subscription_id,
                )
                if not ignore_talpa_errors:
                    raise SubscriptionCancelError(
                        _(
                            "Subscription could not be cancelled. "
                            "Please try again later."
                        )
                    ) from e

        self.status = SubscriptionStatus.CANCELLED
        self.cancel_reason = cancel_reason
        self.save()

        remaining_valid_order_subscriptions = Subscription.objects.filter(
            order_items__order__talpa_order_id__exact=talpa_order_id,
            status=SubscriptionStatus.CONFIRMED,
        )
        # Mark the order as cancelled if it has no active subscriptions left
        if not remaining_valid_order_subscriptions.exists():
            try:
                order.cancel(cancel_from_talpa=cancel_from_talpa)
            except requests.RequestException as e:
                logger.exception("Order %s cancelling failed.", talpa_order_id)
                if not ignore_talpa_errors:
                    raise SubscriptionCancelError(
                        _(
                            "Subscription could not be cancelled. "
                            "Please try again later."
                        )
                    ) from e

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
    regular_unit_price = models.DecimalField(max_digits=7, decimal_places=2, null=True)
    discounted_unit_price = models.DecimalField(
        max_digits=7, decimal_places=2, null=True
    )

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

    @staticmethod
    def _vehicle_change_tariff_pair(item, history):
        if item.order.type != OrderType.VEHICLE_CHANGED or not item.payment_unit_price:
            return None
        previous = item.unit_price - item.payment_unit_price
        has_previous = any(
            row.order_id < item.order_id
            and row.unit_price == previous
            and row.start_time <= item.end_time
            and row.end_time >= item.start_time
            for row in history
        )
        if not has_previous:
            return None
        return tuple(sorted((previous, item.unit_price), reverse=True))

    def _historical_tariff_matches(self):
        # Only contemporaneous records for this product and permit can
        # establish the two prices for an already purchased billing period.
        history = self.permit._confirmed_fixed_period_items().filter(
            product_id=self.product_id,
            start_time__lte=self.end_time,
            end_time__gte=self.start_time,
        )
        matches = set()
        for item in history:
            if item.regular_unit_price is not None:
                pair = (item.regular_unit_price, item.discounted_unit_price)
            else:
                pair = self._vehicle_change_tariff_pair(item, history)
            if pair and self.unit_price in pair:
                matches.add(pair)
        return matches

    # noinspection unreachable-code
    def tariff_prices(self, is_secondary):
        if self.regular_unit_price is not None:
            return self.regular_unit_price, self.discounted_unit_price

        prices = self.product.tariff_prices(is_secondary)
        if self.product.modified_at <= self.created_at and self.unit_price in prices:
            return prices

        matches = self._historical_tariff_matches()
        if len(matches) == 1:
            return matches.pop()
        if not matches and self.unit_price in prices:
            return prices
        return self.unit_price, self.unit_price

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
        Custom timeframe used to make sure subsequent
        order items don't have gaps in days
        """
        if start_time and self.end_time:
            start_time = tz.localtime(start_time).strftime(DATE_FORMAT)
            end_time = tz.localtime(self.end_time).strftime(DATE_FORMAT)
            return f"{start_time} - {end_time}"
        return ""
