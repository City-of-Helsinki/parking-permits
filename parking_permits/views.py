import csv
import datetime
import json
import logging

from ariadne import convert_camel_case_to_snake
from dateutil.relativedelta import relativedelta
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

from .constants import Origin, ParkingPermitEndType
from .customer_permit import CustomerPermit
from .decorators import require_preparators
from .exceptions import (
    DeletionNotAllowed,
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
from .models.parking_permit import ParkingPermit, ParkingPermitStatus
from .serializers import (
    MessageResponseSerializer,
    OrderSerializer,
    PaymentSerializer,
    ProductSerializer,
    ResolveAvailabilityResponseSerializer,
    ResolveAvailabilitySerializer,
    ResolvePriceResponseSerializer,
    RightOfPurchaseResponseSerializer,
    SubscriptionSerializer,
    TalpaPayloadSerializer,
)
from .services.mail import (
    PermitEmailType,
    send_permit_email,
    send_vehicle_low_emission_discount_email,
)
from .utils import (
    get_end_time,
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
        request_body=ResolveAvailabilitySerializer,
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


class TalpaResolvePrice(APIView):
    @swagger_auto_schema(
        operation_description="Resolve price of product from an order item.",
        request_body=TalpaPayloadSerializer,
        responses={
            200: openapi.Response("Resolve price", ResolvePriceResponseSerializer)
        },
        tags=["ResolvePrice"],
    )
    def post(self, request, format=None):
        logger.info(
            f"Data received for resolve price = {json.dumps(request.data, default=str)}"
        )
        meta = request.data.get("orderItem").get("meta")
        permit_id = get_meta_value(meta, "permitId")

        if permit_id is None:
            return Response(
                {
                    "message": "No permitId key available in meta list of key-value pairs"
                },
                status=400,
            )

        try:
            permit = ParkingPermit.objects.get(pk=permit_id)
            products_with_quantity = permit.get_products_with_quantities()
            product, quantity, date_range = products_with_quantity[0]
            price = product.get_modified_unit_price(
                permit.vehicle.is_low_emission, permit.is_secondary_vehicle
            )
            vat = product.vat
            price_vat = price * vat
        except Exception as e:
            logger.error(f"Resolve price error = {str(e)}")
            return Response({"message": str(e)}, status=400)

        response = snake_to_camel_dict(
            {
                "row_price_net": float(price - price_vat),
                "row_price_vat": float(price_vat),
                "row_price_total": float(price),
                "price_net": float(price - price_vat),
                "price_vat": float(price_vat),
                "price_gross": float(price),
                "vat_percentage": float(product.vat_percentage),
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
        order_item_id = order_item_data.get("orderItemId")
        meta = order_item_data.get("meta")
        permit_id = get_meta_value(meta, "permitId")
        user_id = request.data.get("userId")

        try:
            permit = ParkingPermit.objects.get(pk=permit_id)
            customer = permit.customer
            customer.fetch_driving_licence_detail()
            vehicle = customer.fetch_vehicle_detail(permit.vehicle.registration_number)
            is_user_of_vehicle = customer.is_user_of_vehicle(vehicle)
            has_valid_driving_licence = customer.has_valid_driving_licence_for_vehicle(
                vehicle
            )
            order_item = OrderItem.objects.get(talpa_order_item_id=order_item_id)
            is_valid_subscription = (
                order_item.subscription.status == SubscriptionStatus.CONFIRMED
            )
            right_of_purchase = (
                is_valid_subscription
                and is_user_of_vehicle
                and customer.driving_licence.active
                and has_valid_driving_licence
                and not vehicle.is_due_for_inspection()
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
            logger.error("Talpa order id is missing from request data")
            return Response(
                {"message": "No order id is provided"},
                status=400,
            )
        if event_type == "PAYMENT_PAID":
            logger.info(
                f"Payment paid event received for order: {talpa_order_id}. Processing payment ..."
            )
            order = Order.objects.get(talpa_order_id=talpa_order_id)
            order.status = OrderStatus.CONFIRMED
            order.payment_type = OrderPaymentType.ONLINE_PAYMENT
            order.paid_time = tz.now()
            order.save()
            for permit in order.permits.all():
                permit.status = ParkingPermitStatus.VALID

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
            logger.error(f"Unknown payment event type {event_type}")
            return Response(
                {"message": "Unknown payment event type"},
                status=400,
            )


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
            logger.error("Talpa order id is missing from request data")
            return Response(
                {"message": "No order id is provided"},
                status=400,
            )
        if not talpa_subscription_id:
            logger.error("Talpa subscription id is missing from request data")
            return Response(
                {"message": "No subscription id is provided"},
                status=400,
            )

        # Subscriptipn renewal process
        if event_type == "SUBSCRIPTION_RENEWAL_ORDER_CREATED":
            logger.info(f"Renewing subscription: {talpa_subscription_id}")
            subscription = Subscription.objects.get(
                talpa_subscription_id=talpa_subscription_id
            )
            order_item = subscription.order_items.first()
            permit = order_item.permit
            permit.end_time = permit.end_time + relativedelta(months=1)
            permit.save()

            try:
                validated_order_data = OrderValidator.validate_order(
                    talpa_order_id, permit.customer.user.uuid
                )
            except OrderValidationError as e:
                logger.error(f"Order validation failed. Error = {e}")
                return Response({"message": str(e)}, status=400)

            paid_time = tz.make_aware(
                datetime.datetime.strptime(
                    validated_order_data.get("lastValidPurchaseDateTime"),
                    "%Y-%m-%dT%H:%M:%S.%fZ",
                )
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
                status=OrderStatus.CONFIRMED,
                paid_time=paid_time,
                address_text=str(permit.full_address),
                parking_zone_name=permit.parking_zone.name,
                vehicles=[permit.vehicle.registration_number],
                type=OrderType.CREATED,
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
                    validated_order_item_data.get("startDate"), "%Y-%m-%dT%H:%M:%S"
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

            send_permit_email(PermitEmailType.UPDATED, permit)
            try:
                permit.update_parkkihubi_permit()
            except ParkkihubiPermitError:
                permit.create_parkkihubi_permit()
            logger.info(
                f"{subscription} is renewed and permit end time is set to {permit.end_time}"
            )
            return Response({"message": "Subscription renewal completed"}, status=200)
        else:
            logger.error(f"Unknown order event type {event_type}")
            return Response(
                {"message": "Unknown order event type"},
                status=400,
            )


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
            logger.error("Talpa order id is missing from request data")
            return Response(
                {"message": "No order id is provided"},
                status=400,
            )
        if not talpa_order_item_id:
            logger.error("Talpa order item id is missing from request data")
            return Response(
                {"message": "No order item id is provided"},
                status=400,
            )
        if not talpa_subscription_id:
            logger.error("Talpa subscription id is missing from request data")
            return Response(
                {"message": "No subscription id is provided"},
                status=400,
            )
        if not event_type:
            logger.error("Talpa subscription event type is missing from request data")
            return Response(
                {"message": "No subscription event type is provided"},
                status=400,
            )

        order = Order.objects.get(talpa_order_id=talpa_order_id)
        try:
            OrderValidator.validate_order(talpa_order_id, order.customer.user.uuid)
        except OrderValidationError as e:
            logger.error(f"Subscription order validation failed. Error = {e}")
            return Response({"message": str(e)}, status=400)

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
                logger.error(f"Subscription validation failed. Error = {e}")
                return Response({"message": str(e)}, status=400)

            permit_id = validated_subscription_data.get("value")
            order_item_qs = OrderItem.objects.filter(
                order__talpa_order_id=talpa_order_id,
                permit_id=permit_id,
            )
            order_item = order_item_qs.first()
            if not order_item:
                message = f"Order item for order {order.talpa_order_id} and permit {permit_id} not found"
                logger.error(message)
                return Response({"message": message}, status=400)
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
            subscription = Subscription.objects.get(
                talpa_subscription_id=talpa_subscription_id
            )
            order_item = subscription.order_items.first()
            permit = order_item.permit
            CustomerPermit(permit.customer_id).end(
                [permit.id],
                ParkingPermitEndType.AFTER_CURRENT_PERIOD,
                subscription_cancel_reason=request.data.get("reason"),
                cancel_from_talpa=False,
            )
            logger.info(
                f"Subscription {subscription} cancelled and permit ended after current period"
            )
            return Response({"message": "Subscription cancelled"}, status=200)
        else:
            logger.error(f"Unknown subscription event type {event_type}")
            return Response(
                {"message": "Unknown subscription event type"},
                status=400,
            )


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
        obj = self.get_object()
        audit_msg.target = obj
        return Response(obj.serialize(), status=200)

    def get_object(self) -> Customer:
        try:
            customer = Customer.objects.get(
                source_system=SourceSystem.HELSINKI_PROFILE, source_id=self.kwargs["id"]
            )
        except Customer.DoesNotExist:
            raise Http404
        else:
            self.check_object_permissions(self.request, customer)
            return customer

    def _delete(self):
        customer = self.get_object()
        if not customer.can_be_deleted:
            raise DeletionNotAllowed()
        customer.delete_all_data()

    def delete(self, request, *args, **kwargs):
        dry_run_serializer = DryRunSerializer(data=request.data)
        dry_run_serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            self._delete()
            if dry_run_serializer.data["dry_run"]:
                transaction.set_rollback(True)
        return Response(status=204)


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
