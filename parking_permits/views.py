import csv
import datetime
import json
import logging
import time
import uuid

from ariadne import convert_camel_case_to_snake
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.db import transaction
from django.http import (
    Http404,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseNotFound,
)
from django.utils import timezone as tz
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_safe
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from helsinki_gdpr.views import DryRunSerializer, GDPRAPIView, GDPRScopesPermission
from rest_framework import generics, mixins
from rest_framework.response import Response
from rest_framework.views import APIView

import audit_logger as audit
from audit_logger import AuditMsg

from .constants import Origin
from .customer_permit import CustomerPermit
from .decorators import require_preparators
from .exceptions import (
    OrderValidationError,
    ParkkihubiPermitError,
    SubscriptionValidationError,
)
from .exporters import DataExporter, PdfExporter
from .forms import (
    OrderSearchForm,
    PdfExportForm,
    PermitSearchForm,
    ProductSearchForm,
    RefundSearchForm,
)
from .models import Customer, Order, OrderItem, Product
from .models.common import SourceSystem
from .models.order import (
    OrderPaymentType,
    OrderStatus,
    OrderType,
    OrderValidator,
    Subscription,
    SubscriptionStatus,
    SubscriptionValidator,
)
from .models.parking_permit import (
    ParkingPermit,
    ParkingPermitEndType,
    ParkingPermitEventFactory,
    ParkingPermitStatus,
)
from .serializers import (
    MessageResponseSerializer,
    OrderSerializer,
    PaymentSerializer,
    ProductSerializer,
    ResolveAvailabilityRequestSerializer,
    ResolveAvailabilityResponseSerializer,
    ResolvePriceRequestSerializer,
    ResolvePriceResponseSerializer,
    ResolveProductRequestSerializer,
    ResolveProductResponseSerializer,
    RightOfPurchaseResponseSerializer,
    SubscriptionSerializer,
    TalpaPayloadSerializer,
)
from .services.mail import (
    PermitEmailType,
    send_permit_email,
    send_vehicle_low_emission_discount_email,
)
from .talpa.order import TalpaOrderManager
from .utils import (
    get_end_time,
    get_meta_item,
    get_meta_value,
    get_user_from_api_view_method_args,
    snake_to_camel_dict,
)

logger = logging.getLogger("db")

audit_logger = audit.getAuditLoggerAdapter(
    "audit",
    dict(
        event_type=audit.EventType.APP,
    ),
    autolog_config={
        "autostatus": True,
        "kwarg_name": "audit_msg",
    },
)


def ok_response(message):
    logger.info(message)
    return Response({"message": message}, status=200)


def bad_request_response(message):
    logger.error(message)
    return Response({"message": message}, status=400)


def not_found_response(message):
    logger.info(message)
    return Response({"message": message}, status=404)


class ProductList(mixins.ListModelMixin, generics.GenericAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer

    @swagger_auto_schema(
        operation_description="Retrieve all products.",
        responses={
            200: openapi.Response(
                "Retrieve all products.",
                ProductSerializer,
            )
        },
        tags=["Product"],
    )
    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)


class ProductDetail(mixins.RetrieveModelMixin, generics.GenericAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer

    @swagger_auto_schema(
        operation_description="Retrieve a single product with id.",
        responses={
            200: openapi.Response(
                "Retrieve a single product with id.",
                ProductSerializer,
            )
        },
        tags=["Product"],
    )
    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)


class TalpaResolveAvailability(APIView):
    @swagger_auto_schema(
        operation_description="Resolve product availability.",
        request_body=ResolveAvailabilityRequestSerializer,
        responses={
            200: openapi.Response(
                "Product is always available for purchase.",
                ResolveAvailabilityResponseSerializer,
            )
        },
        tags=["ResolveAvailability"],
    )
    def post(self, request, format=None):
        logger.info(
            f"Data received for resolve availability = {json.dumps(request.data, default=str)}"
        )
        shared_product_id = request.data.get("productId")
        res = snake_to_camel_dict({"product_id": shared_product_id, "value": True})
        logger.info(f"Resolve availability response = {json.dumps(res, default=str)}")
        return Response(res)


class TalpaResolveProduct(APIView):
    @swagger_auto_schema(
        operation_description="Resolve product for subscription.",
        request_body=ResolveProductRequestSerializer,
        responses={
            200: openapi.Response("Resolve product", ResolveProductResponseSerializer)
        },
        tags=["ResolveProduct"],
    )
    def post(self, request, format=None):
        logger.info(
            f"Data received for resolve product = {json.dumps(request.data, default=str)}"
        )
        subscription_id = request.data.get("subscriptionId")
        if not subscription_id:
            return bad_request_response("Subscription id is missing from request data")
        user_id = request.data.get("userId")
        if not user_id:
            return bad_request_response("User id is missing from request data")
        order_item_data = request.data.get("orderItem")
        if not order_item_data:
            return bad_request_response("Order item data is missing from request data")
        meta = order_item_data.get("meta")
        if not meta:
            return bad_request_response(
                "Order item metadata is missing from request data"
            )
        permit_id = get_meta_value(meta, "permitId")
        if not permit_id:
            return bad_request_response(
                "No permitId key available in meta list of key-value pairs"
            )

        try:
            permit = ParkingPermit.objects.get(pk=permit_id)
            # If permit is open ended and it is the only permit for the customer, set it as primary vehicle
            if (
                permit.is_open_ended
                and not permit.primary_vehicle
                and not permit.customer.permits.active().exclude(id=permit.id).exists()
            ):
                permit.primary_vehicle = True
                permit.save()

            products_with_quantity = permit.get_products_with_quantities()
            if not products_with_quantity:
                return bad_request_response("No products found for permit")
            product_with_quantity = products_with_quantity[0]
            if not product_with_quantity:
                return bad_request_response(
                    "Product with quantity not found for permit"
                )
            product = product_with_quantity[0]
            if not product:
                return bad_request_response("Product not found")

            order_item_response_data = {"meta": []}
            order_item = permit.order_items.first()
            if order_item:
                order_item_response_data.get("meta").append(
                    {
                        "key": "sourceOrderItemId",
                        "value": str(order_item.id),
                        "visibleInCheckout": False,
                        "ordinal": 0,
                    }
                )
                TalpaOrderManager.append_detail_meta(
                    order_item_response_data,
                    permit,
                    fixed_end_time=tz.localtime(permit.end_time)
                    + relativedelta(months=1),
                )

            response = {
                "subscriptionId": subscription_id,
                "userId": user_id,
                "productId": str(product.talpa_product_id),
                "productName": product.name,
                "productLabel": permit.vehicle.description,
                "orderItemMetas": order_item_response_data.get("meta"),
            }
        except Exception as e:
            response = {
                "errorMessage": str(e),
                "subscriptionId": subscription_id,
                "userId": user_id,
            }
        logger.info(f"Resolve product response = {json.dumps(response, default=str)}")
        return Response(response)


class TalpaResolvePrice(APIView):
    @swagger_auto_schema(
        operation_description="Resolve price of product from an order item.",
        request_body=ResolvePriceRequestSerializer,
        responses={
            200: openapi.Response("Resolve price", ResolvePriceResponseSerializer)
        },
        tags=["ResolvePrice"],
    )
    def post(self, request, format=None):
        logger.info(
            f"Data received for resolve price = {json.dumps(request.data, default=str)}"
        )
        subscription_id = request.data.get("subscriptionId")
        if not subscription_id:
            return bad_request_response("Subscription id is missing from request data")
        user_id = request.data.get("userId")
        if not user_id:
            return bad_request_response("User id is missing from request data")
        order_item_data = request.data.get("orderItem")
        if not order_item_data:
            return bad_request_response("Order item data is missing from request data")
        order_item_id = order_item_data.get("orderItemId")
        if not order_item_id:
            return bad_request_response("Order item id is missing from request data")
        meta = order_item_data.get("meta")
        if not meta:
            return bad_request_response(
                "Order item metadata is missing from request data"
            )
        permit_id = get_meta_value(meta, "permitId")
        if not permit_id:
            return bad_request_response(
                "No permitId key available in meta list of key-value pairs"
            )

        try:
            permit = ParkingPermit.objects.get(pk=permit_id)
            products_with_quantity = permit.get_products_with_quantities()
            if not products_with_quantity:
                return bad_request_response("No products found for permit")
            product_with_quantity = products_with_quantity[0]
            if not product_with_quantity:
                return bad_request_response(
                    "Product with quantity not found for permit"
                )
            product = product_with_quantity[0]
            if not product:
                return bad_request_response("Product not found")
            response = snake_to_camel_dict(
                {
                    "subscription_id": subscription_id,
                    "user_id": user_id,
                    **product.get_talpa_pricing(
                        permit.vehicle.is_low_emission,
                        permit.is_secondary_vehicle,
                    ),
                }
            )
        except Exception as e:
            response = snake_to_camel_dict(
                {
                    "error_message": str(e),
                    "subscription_id": subscription_id,
                    "user_id": user_id,
                }
            )
        logger.info(f"Resolve price response = {json.dumps(response, default=str)}")
        return Response(response)


class TalpaResolveRightOfPurchase(APIView):
    @swagger_auto_schema(
        operation_description="Used as an webhook by Talpa in order to send an order notification.",
        request_body=TalpaPayloadSerializer,
        responses={
            200: openapi.Response(
                "Right of purchase response", RightOfPurchaseResponseSerializer
            )
        },
        tags=["RightOfPurchase"],
    )
    def post(self, request):
        logger.info(
            f"Data received for resolve right of purchase = {json.dumps(request.data, default=str)}"
        )
        order_item_data = request.data.get("orderItem")
        if not order_item_data:
            return bad_request_response("Order item data is missing from request data")
        order_item_id = order_item_data.get("orderItemId")
        if not order_item_id:
            return bad_request_response(
                "Talpa order item id is missing from request data"
            )
        meta = order_item_data.get("meta")
        if not meta:
            return bad_request_response(
                "Order item metadata is missing from request data"
            )
        permit_id = get_meta_value(meta, "permitId")
        if not permit_id:
            return bad_request_response(
                "No permitId key available in meta list of key-value pairs"
            )
        user_id = request.data.get("userId")
        if not user_id:
            return bad_request_response("User id is missing from request data")

        try:
            # Temporarily disabled traficom checks
            permit = ParkingPermit.objects.get(pk=permit_id)  # noqa: F841
            # customer = permit.customer
            # if settings.TRAFICOM_CHECK:
            #    customer.fetch_driving_licence_detail(permit)
            #    is_driving_licence_active = customer.driving_licence.active
            # else:
            #     is_driving_licence_active = True
            # vehicle = customer.fetch_vehicle_detail(
            #     permit.vehicle.registration_number, permit
            # )
            # is_user_of_vehicle = customer.is_user_of_vehicle(vehicle)
            # has_valid_driving_licence = customer.has_valid_driving_licence_for_vehicle(
            #     vehicle
            # )
            order_item = OrderItem.objects.get(talpa_order_item_id=order_item_id)
            is_valid_subscription = (
                order_item.subscription.status == SubscriptionStatus.CONFIRMED
            )
            right_of_purchase = (
                is_valid_subscription
                # and is_user_of_vehicle
                # and is_driving_licence_active
                # and has_valid_driving_licence
            )
            res = snake_to_camel_dict(
                {
                    "error_message": "",
                    "right_of_purchase": right_of_purchase,
                    "user_id": user_id,
                }
            )
        except Exception as e:
            res = snake_to_camel_dict(
                {
                    "error_message": str(e),
                    "right_of_purchase": False,
                    "user_id": user_id,
                }
            )

        logger.info(
            f"Resolve right of purchase response = {json.dumps(res, default=str)}"
        )
        return Response(res)


class PaymentView(APIView):
    @swagger_auto_schema(
        operation_description="Process payment notifications.",
        request_body=PaymentSerializer,
        security=[],
        responses={
            200: openapi.Response(
                "Payment received response", MessageResponseSerializer
            )
        },
        tags=["Payment"],
    )
    @transaction.atomic
    def post(self, request, format=None):
        logger.info(f"Payment received. Data = {json.dumps(request.data, default=str)}")
        talpa_order_id = request.data.get("orderId")
        event_type = request.data.get("eventType")
        if not talpa_order_id:
            return bad_request_response("Talpa order id is missing from request data")
        try:
            order = Order.objects.get(talpa_order_id=talpa_order_id)
        except Order.DoesNotExist:
            return not_found_response(f"Order {talpa_order_id} does not exist")

        if event_type == "PAYMENT_PAID":
            logger.info(
                f"Payment paid event received for order: {talpa_order_id}. Processing payment ..."
            )
            order.status = OrderStatus.CONFIRMED
            order.payment_type = OrderPaymentType.ONLINE_PAYMENT
            order.paid_time = tz.now()
            order.save()

            for (
                ext_request
            ) in order.get_pending_permit_extension_requests().select_related("permit"):
                ext_request.approve()
                ParkingPermitEventFactory.make_approve_ext_request_event(ext_request)
                send_permit_email(PermitEmailType.EXTENDED, ext_request.permit)

            for permit in order.permits.all():
                permit.status = ParkingPermitStatus.VALID

                # Subscription renewed type order has always only one permit
                if order.type == OrderType.SUBSCRIPTION_RENEWED:
                    permit.renew_open_ended_permit()
                    send_permit_email(PermitEmailType.UPDATED, permit)

                if order.type == OrderType.VEHICLE_CHANGED:
                    if (
                        permit.consent_low_emission_accepted
                        and permit.vehicle.is_low_emission
                    ):
                        send_vehicle_low_emission_discount_email(
                            PermitEmailType.VEHICLE_LOW_EMISSION_DISCOUNT_DEACTIVATED,
                            permit,
                        )
                    if permit.next_vehicle:
                        permit.vehicle = permit.next_vehicle
                        permit.next_vehicle = None
                        permit.save()
                        send_permit_email(PermitEmailType.UPDATED, permit)

                if order.type == OrderType.ADDRESS_CHANGED:
                    if (
                        permit.consent_low_emission_accepted
                        and permit.vehicle.is_low_emission
                    ):
                        send_vehicle_low_emission_discount_email(
                            PermitEmailType.VEHICLE_LOW_EMISSION_DISCOUNT_DEACTIVATED,
                            permit,
                        )
                    permit.parking_zone = permit.next_parking_zone
                    permit.next_parking_zone = None
                    permit.address = permit.next_address
                    permit.next_address = None
                    permit.save()
                    send_permit_email(PermitEmailType.UPDATED, permit)

                if order.type == OrderType.CREATED:
                    permit.save()
                    send_permit_email(PermitEmailType.CREATED, permit)

                if (
                    permit.consent_low_emission_accepted
                    and permit.vehicle.is_low_emission
                ):
                    send_vehicle_low_emission_discount_email(
                        PermitEmailType.VEHICLE_LOW_EMISSION_DISCOUNT_ACTIVATED, permit
                    )
                try:
                    permit.update_parkkihubi_permit()
                except ParkkihubiPermitError:
                    permit.create_parkkihubi_permit()

            logger.info(f"{order} is confirmed and order permits are set to VALID ")
            return Response({"message": "Payment received"}, status=200)
        else:
            order.permit_extension_requests.cancel_pending()
            return bad_request_response(f"Unknown payment event type {event_type}")


class OrderView(APIView):
    @swagger_auto_schema(
        operation_description="Process order notifications.",
        request_body=OrderSerializer,
        security=[],
        responses={
            200: openapi.Response("Order received response", MessageResponseSerializer)
        },
        tags=["Order"],
    )
    @transaction.atomic
    def post(self, request, format=None):
        logger.info(f"Order received. Data = {json.dumps(request.data, default=str)}")
        talpa_order_id = request.data.get("orderId")
        talpa_subscription_id = request.data.get("subscriptionId")
        event_type = request.data.get("eventType")

        if not talpa_order_id:
            return bad_request_response("Talpa order id is missing from request data")

        if event_type == "ORDER_CANCELLED":
            try:
                order = Order.objects.get(talpa_order_id=talpa_order_id)
                order_permits = order.permits.filter(
                    status__in=[
                        ParkingPermitStatus.DRAFT,
                        ParkingPermitStatus.PAYMENT_IN_PROGRESS,
                        ParkingPermitStatus.VALID,
                    ],
                    end_type=ParkingPermitEndType.IMMEDIATELY,
                )
                if order_permits:
                    logger.info(f"Cancelling order: {talpa_order_id}")
                    order.status = OrderStatus.CANCELLED
                    order.save()
                    order_permits.update(
                        status=ParkingPermitStatus.CANCELLED, modified_at=tz.now()
                    )
                    logger.info(
                        f"{order} is cancelled and order permits are set to CANCELLED-status"
                    )
                elif ext_requests := order.get_pending_permit_extension_requests():
                    for ext_request in ext_requests:
                        ext_request.cancel()
                        ParkingPermitEventFactory.make_cancel_ext_request_event(
                            ext_request
                        )
                    logger.info(f"Cancelling order: {talpa_order_id}")
                    order.status = OrderStatus.CANCELLED
                    order.save()
                    logger.info(
                        f"{order} is cancelled and permit extensions set to CANCELLED-status"
                    )

            except Order.DoesNotExist:
                return not_found_response(f"Order {talpa_order_id} does not exist")
            return Response({"message": "Order cancel event processed"}, status=200)

        if not talpa_subscription_id:
            return bad_request_response(
                "Talpa subscription id is missing from request data"
            )

        # Subscriptipn renewal process
        if event_type == "SUBSCRIPTION_RENEWAL_ORDER_CREATED":
            logger.info(f"Renewing subscription: {talpa_subscription_id}")
            try:
                subscription = Subscription.objects.get(
                    talpa_subscription_id=talpa_subscription_id
                )
            except Subscription.DoesNotExist:
                return not_found_response(
                    f"Subscription {talpa_subscription_id} does not exist"
                )
            if Order.objects.filter(talpa_order_id=talpa_order_id).exists():
                return ok_response(
                    f"Subscription {talpa_subscription_id} already renewed with order {talpa_order_id}"
                )
            order_item = subscription.order_items.first()
            permit = order_item.permit

            if not permit or not permit.customer or not permit.customer.user:
                return bad_request_response(
                    f"Permit {permit} or customer {permit.customer} or user {permit.customer.user} is missing"
                )
            try:
                validated_order_data = OrderValidator.validate_order(
                    talpa_order_id, permit.customer.user.uuid
                )
            except OrderValidationError as e:
                return bad_request_response(
                    f"Order validation failed. Error = {str(e)}"
                )

            order = Order.objects.create(
                talpa_order_id=validated_order_data.get("orderId"),
                talpa_checkout_url=validated_order_data.get("checkoutUrl"),
                talpa_logged_in_checkout_url=validated_order_data.get(
                    "loggedInCheckoutUrl"
                ),
                talpa_receipt_url=validated_order_data.get("receiptUrl"),
                payment_type=OrderPaymentType.ONLINE_PAYMENT,
                customer=permit.customer,
                status=OrderStatus.DRAFT,
                address_text=str(permit.full_address),
                parking_zone_name=permit.parking_zone.name,
                vehicles=[permit.vehicle.registration_number],
                type=OrderType.SUBSCRIPTION_RENEWED,
            )
            order.permits.add(permit)
            order.save()

            validated_order_item_data = (
                validated_order_data.get("items")
                and validated_order_data.get("items")[0]
            )

            product = Product.objects.get(
                talpa_product_id=validated_order_item_data.get("productId")
            )

            start_time = tz.make_aware(
                datetime.datetime.strptime(
                    validated_order_item_data.get("startDate"), "%Y-%m-%dT%H:%M:%S.%f"
                )
            )
            end_time = get_end_time(start_time, 1)

            OrderItem.objects.create(
                talpa_order_item_id=validated_order_item_data.get("orderItemId"),
                order=order,
                subscription=subscription,
                product=product,
                permit=permit,
                unit_price=validated_order_item_data.get("priceGross"),
                payment_unit_price=validated_order_item_data.get("rowPriceTotal"),
                vat=validated_order_item_data.get("vatPercentage"),
                quantity=validated_order_item_data.get("quantity"),
                start_time=start_time,
                end_time=end_time,
            )
            logger.info(
                f"{subscription} is renewed and new order {order} is created with order item {order_item}"
            )
            return Response({"message": "Subscription renewal completed"}, status=200)
        else:
            return bad_request_response(f"Unknown order event type {event_type}")


class SubscriptionView(APIView):
    @swagger_auto_schema(
        operation_description="Process subscription notifications.",
        request_body=SubscriptionSerializer,
        security=[],
        responses={
            200: openapi.Response(
                "Subscription event received response", MessageResponseSerializer
            )
        },
        tags=["Subscription"],
    )
    @transaction.atomic
    def post(self, request, format=None):
        # Safety sleep to make sure that previous tasks are finished
        wait_buffer = settings.TALPA_WEBHOOK_WAIT_BUFFER_SECONDS
        if wait_buffer and wait_buffer > 0:
            time.sleep(wait_buffer)
        logger.info(
            f"Subscription event received. Data = {json.dumps(request.data, default=str)}"
        )
        talpa_order_id = request.data.get("orderId")
        talpa_order_item_id = request.data.get("orderItemId")
        talpa_subscription_id = request.data.get("subscriptionId")
        event_type = request.data.get("eventType")
        event_timestamp = request.data.get("eventTimestamp")
        event_time = None
        if event_timestamp:
            event_time = parse_datetime(event_timestamp[:-1])

        if not talpa_order_id:
            return bad_request_response("Talpa order id is missing from request data")

        if not talpa_order_item_id:
            return bad_request_response(
                "Talpa order item id is missing from request data"
            )

        if not talpa_subscription_id:
            return bad_request_response(
                "Talpa subscription id is missing from request data"
            )

        if not event_type:
            return bad_request_response(
                "Talpa subscription event type is missing from request data"
            )

        try:
            order = Order.objects.get(talpa_order_id=talpa_order_id)
        except Order.DoesNotExist:
            return not_found_response(f"Order {talpa_order_id} does not exist")
        if not order.customer or not order.customer.user:
            return bad_request_response(
                f"Order {talpa_order_id} customer or user is missing"
            )
        try:
            OrderValidator.validate_order(talpa_order_id, order.customer.user.uuid)
        except OrderValidationError as e:
            return bad_request_response(
                f"Subscription order validation failed. Error = {str(e)}"
            )

        if event_type == "SUBSCRIPTION_CREATED":
            logger.info(f"Creating new subscription: {talpa_subscription_id}")
            try:
                validated_subscription_data = (
                    SubscriptionValidator.validate_subscription(
                        str(order.customer.user.uuid),
                        talpa_subscription_id,
                        talpa_order_id,
                        talpa_order_item_id,
                    )
                )
            except SubscriptionValidationError as e:
                return bad_request_response(
                    f"Subscription validation failed. Error = {e}"
                )

            meta = validated_subscription_data.get("meta")
            meta_item = get_meta_item(meta, "permitId")
            permit_id = meta_item.get("value") if meta_item else None
            if not permit_id:
                return bad_request_response(
                    "No permitId key available in meta list of key-value pairs"
                )

            order_item_qs = OrderItem.objects.filter(
                order__talpa_order_id=talpa_order_id,
                permit_id=permit_id,
            )
            order_item = order_item_qs.first()
            if not order_item:
                return not_found_response(
                    f"Order item for order {order.talpa_order_id} and permit {permit_id} not found"
                )

            subscription = Subscription.objects.create(
                talpa_subscription_id=talpa_subscription_id,
                status=SubscriptionStatus.CONFIRMED,
                created_by=order.customer.user,
            )
            subscription.created_at = event_time or tz.localtime(tz.now())
            subscription.save()
            order_item.talpa_order_item_id = talpa_order_item_id
            order_item.subscription = subscription
            order_item.save()
            logger.info(
                f"Subscription {subscription} created and order item {order_item} updated"
            )
            return Response({"message": "Subscription created"}, status=200)
        elif event_type == "SUBSCRIPTION_CANCELLED":
            logger.info(f"Cancelling subscription: {talpa_subscription_id}")
            if order.status == OrderStatus.CANCELLED:
                return ok_response(f"Order {talpa_order_id} is already cancelled")
            try:
                subscription = Subscription.objects.get(
                    talpa_subscription_id=talpa_subscription_id
                )
            except Subscription.DoesNotExist:
                return not_found_response(
                    f"Subscription {talpa_subscription_id} does not exist"
                )
            if subscription.status == SubscriptionStatus.CANCELLED:
                return ok_response(
                    f"Subscription {talpa_subscription_id} is already cancelled"
                )
            order_item = subscription.order_items.first()
            permit = order_item.permit
            if permit.status == ParkingPermitStatus.CLOSED:
                return ok_response(
                    f"Subscription {talpa_subscription_id} permit {permit.id} is already closed"
                )
            CustomerPermit(permit.customer_id).end(
                [permit.id],
                ParkingPermitEndType.AFTER_CURRENT_PERIOD,
                iban="",
                subscription_cancel_reason=request.data.get("reason"),
                cancel_from_talpa=False,
                force_end=True,
            )
            logger.info(
                f"Subscription {talpa_subscription_id} cancelled and permit ended after current period"
            )
            return Response(
                {"message": f"Subscription {talpa_subscription_id} cancelled"},
                status=200,
            )
        else:
            return bad_request_response(f"Unknown subscription event type {event_type}")


class ParkingPermitGDPRScopesPermission(GDPRScopesPermission):
    def has_object_permission(self, request, view, obj):
        if request.user.is_super_admin:
            return True
        return super().has_object_permission(request, view, obj)


class ParkingPermitGDPRAPIView(GDPRAPIView):
    permission_classes = [ParkingPermitGDPRScopesPermission]


class ParkingPermitsGDPRAPIView(ParkingPermitGDPRAPIView):
    @audit_logger.autolog(
        AuditMsg(
            "Admin downloaded customer data from the GDPR API.",
            origin=Origin.ADMIN_UI,
            operation=audit.Operation.READ,
            reason=audit.Reason.ADMIN_SERVICE,
        ),
        autoactor=get_user_from_api_view_method_args,
        add_kwarg=True,
    )
    def get(self, request, *args, audit_msg: AuditMsg = None, **kwargs):
        customer = self.get_object()
        if not customer:
            logger.info(f"Customer {customer} not found")
            return Response(status=204)
        audit_msg.target = customer
        return Response(customer.serialize(), status=200)

    def get_object(self):
        try:
            user_id = self.kwargs["id"]
            if not self.is_valid_uuid(user_id):
                return None
            customer = Customer.objects.get(
                source_system=SourceSystem.HELSINKI_PROFILE,
                user__uuid=user_id,
            )
        except Customer.DoesNotExist:
            return None
        else:
            self.check_object_permissions(self.request, customer)
            return customer

    def _delete(self):
        customer = self.get_object()
        if not customer:
            logger.info(f"Customer {customer} not found")
            return Response(status=204)
        if not customer.can_be_deleted:
            logger.info(f"Customer {customer} cannot be deleted.")
            return Response(status=403)
        customer.delete_all_data()

    def delete(self, request, *args, **kwargs):
        dry_run_serializer = DryRunSerializer(data=request.data)
        dry_run_serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            self._delete()
            if dry_run_serializer.data["dry_run"]:
                transaction.set_rollback(True)
        return Response(status=204)

    def is_valid_uuid(self, value):
        try:
            uuid.UUID(str(value))
            return True
        except (AttributeError, ValueError):
            return False


@require_preparators
@require_safe
def csv_export(request, data_type):
    form_class = {
        "permits": PermitSearchForm,
        "refunds": RefundSearchForm,
        "orders": OrderSearchForm,
        "products": ProductSearchForm,
    }.get(data_type)
    if not form_class:
        raise Http404

    converted_params = {
        convert_camel_case_to_snake(k): v for k, v in request.GET.items()
    }
    form = form_class(converted_params)
    if not form.is_valid():
        return HttpResponseBadRequest()

    response = HttpResponse(
        content_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{data_type}.csv"'},
    )

    # Needs to be at least preparators in order to download full permits data
    # with customer information.
    if data_type == "permits" and not request.user.is_preparators:
        data_type = "limited_permits"

    data_exporter = DataExporter(data_type, form.get_queryset())
    writer = csv.writer(response)
    writer.writerow(data_exporter.get_headers())
    writer.writerows(data_exporter.get_rows())
    return response


@require_preparators
@require_safe
def pdf_export(request):
    form = PdfExportForm(request.GET)
    if not form.is_valid():
        return HttpResponseBadRequest()

    pdf_exporter = PdfExporter(
        form.cleaned_data["data_type"],
        form.cleaned_data["object_id"],
    )

    pdf = pdf_exporter.get_pdf()
    if not pdf:
        return HttpResponseNotFound()

    filename = f'{form.cleaned_data["data_type"]}_{form.cleaned_data["object_id"]}'
    response = HttpResponse(
        content_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}.pdf"'},
        content=pdf.output(dest="S").encode("latin-1"),
    )
    return response
