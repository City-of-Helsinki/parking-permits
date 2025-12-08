import json
import logging

import numpy as np
import requests
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.db import transaction
from django.utils import timezone as tz
from django.utils.translation import gettext_lazy as _

from parking_permits.exceptions import OrderCreationFailedError, SetTalpaFlowStepsError
from parking_permits.models.order import OrderPaymentType, OrderType
from parking_permits.talpa.pricing import Pricing
from parking_permits.utils import (
    DefaultOrderedDict,
    date_time_to_helsinki,
    format_local_time,
    round_up,
)

logger = logging.getLogger("db")
DATE_FORMAT = "%d.%m.%Y"
TIME_FORMAT = "%d.%m.%Y %H:%M"
TALPA_SUBSCRIPTION_PERIOD_UNIT = settings.TALPA_SUBSCRIPTION_PERIOD_UNIT


class TalpaOrderManager:
    url = settings.TALPA_ORDER_EXPERIENCE_API
    headers = {
        "api-key": settings.TALPA_API_KEY,
        "namespace": settings.NAMESPACE,
        "Content-type": "application/json",
    }

    @classmethod
    def create_item_data(cls, order, order_item, previous_end_time=False):
        unit_pricing = Pricing.calculate(
            order_item.payment_unit_price,
            order_item.vat,
        )

        row_pricing = Pricing.calculate(
            order_item.total_payment_price,
            order_item.vat,
        )

        timeframe = order_item.timeframe
        # Send fake start time in metadata to make sure there is
        # no gaps in days visible to customer.
        # This happens only if there is multiple products within
        # the time range for the permit
        if previous_end_time:
            new_start_time = previous_end_time + relativedelta(days=1)
            timeframe = order_item.adjusted_timeframe(new_start_time)

        item = {
            "productId": str(order_item.product.talpa_product_id),
            "productName": order_item.product.name,
            "productDescription": timeframe,
            "unit": _("pcm"),
            "startDate": date_time_to_helsinki(order_item.permit.start_time),
            "quantity": order_item.quantity,
            "vatPercentage": cls.round_up(float(order_item.vat_percentage)),
            "priceNet": unit_pricing.format_net(),
            "priceVat": unit_pricing.format_vat(),
            "priceGross": unit_pricing.format_gross(),
            "rowPriceNet": row_pricing.format_net(),
            "rowPriceVat": row_pricing.format_vat(),
            "rowPriceTotal": row_pricing.format_gross(),
            "meta": [
                {
                    "key": "sourceOrderItemId",
                    "value": str(order_item.id),
                    "visibleInCheckout": False,
                    "ordinal": 0,
                },
            ],
        }
        # Include periodUnit and periodFrequency only for new open ended permits.
        if order_item.permit.is_open_ended and order.type == OrderType.CREATED:
            item.update(
                {
                    "periodUnit": TALPA_SUBSCRIPTION_PERIOD_UNIT,
                    "periodFrequency": "1",
                }
            )
        return item, row_pricing

    @classmethod
    def append_detail_meta(cls, item, permit, fixed_end_time=None, ext_request=None):
        start_time = tz.localtime(permit.start_time).strftime(DATE_FORMAT)
        if ext_request:
            permit_type = _("Fixed period, extension %(month)d months") % {
                "month": ext_request.month_count
            }
        elif permit.is_fixed_period:
            permit_type = _("Fixed period %(month)d months") % {
                "month": permit.month_count
            }
        else:
            permit_type = _("Open ended 1 month")

        item["meta"] += [
            {
                "key": "permitId",
                "value": str(permit.id),
                "visibleInCheckout": False,
            },
            {
                "key": "permitType",
                "label": _("Parking permit type"),
                "value": permit_type,
                "visibleInCheckout": True,
                "ordinal": 1,
            },
            {
                "key": "startDate",
                "label": _("Parking permit start date*"),
                "value": start_time,
                "visibleInCheckout": True,
                "ordinal": 2,
            },
            {
                "key": "terms",
                "label": "",
                "value": _(
                    "* Parking permit is valid from the start date of your choice, "
                    "once the payment has been accepted"
                ),
                "visibleInCheckout": True,
                "ordinal": 4,
            },
            {
                "key": "copyright",
                "label": "",
                "value": _("Source: Transport register, Traficom"),
                "visibleInCheckout": True,
                "ordinal": 5,
            },
        ]
        if ext_request:
            permit_end_time = ext_request.get_end_time()
        else:
            permit_end_time = fixed_end_time or permit.end_time

        if permit_end_time:
            end_time = tz.localtime(permit_end_time).strftime(TIME_FORMAT)
            item["meta"].append(
                {
                    "key": "endDate",
                    "label": (
                        _("Parking permit expiration date")
                        if permit.is_fixed_period
                        else _("Parking permit period expiration date")
                    ),
                    "value": end_time,
                    "visibleInCheckout": True,
                    "ordinal": 3,
                }
            )
        return item

    @classmethod
    def create_customer_data(cls, customer):
        return {
            "firstName": customer.first_name,
            "lastName": customer.last_name,
            "email": customer.email,
        }

    @classmethod
    def create_order_data(cls, order, ext_request=None):
        items = []
        order_items = (
            order.order_items.all()
            .order_by("permit", "pk")
            .select_related("product", "permit")
        )
        order_items_by_permit = DefaultOrderedDict(list)
        for order_item in order_items:
            order_items_by_permit[order_item.permit].append(order_item)

        total_pricing = Pricing()

        for permit in sorted(
            set([item.permit for item in order_items]),
            key=lambda p: p.is_secondary_vehicle,
        ):
            order_items_of_single_permit = []
            previous_end_time = False
            for index, order_item in enumerate(order_items_by_permit[permit]):
                if order_item.quantity:
                    item, pricing = cls.create_item_data(
                        order, order_item, previous_end_time
                    )
                    previous_end_time = order_item.end_time
                    if index == 0:
                        item.update(
                            {
                                "productLabel": order_item.permit.vehicle.description,
                            }
                        )
                    order_items_of_single_permit.append(item)
                    total_pricing += pricing

            # Append details of permit only to the last order item of permit.
            if len(order_items_of_single_permit) > 0:
                cls.append_detail_meta(
                    order_items_of_single_permit[-1],
                    permit,
                    ext_request=ext_request,
                )
                items += order_items_of_single_permit

        customer = cls.create_customer_data(order.customer)
        last_valid_purchase_date_time = (
            format_local_time(order.talpa_last_valid_purchase_time)
            if order.talpa_last_valid_purchase_time
            else ""
        )

        return {
            "namespace": settings.NAMESPACE,
            "user": str(order.customer.user.uuid),
            "lastValidPurchaseDateTime": last_valid_purchase_date_time,
            "priceNet": total_pricing.format_net(),
            "priceVat": total_pricing.format_vat(),
            "priceTotal": total_pricing.format_gross(),
            "customer": customer,
            "items": items,
        }

    @classmethod
    def round_int(cls, v):
        return "{:0.0f}".format(np.round(v))

    @classmethod
    def round_up(cls, v):
        return round_up(v)

    @classmethod
    def set_flow_steps(cls, order_id, user_id):
        data = {
            "activeStep": 4,
            "totalSteps": 7,
        }
        headers = {
            "user": user_id,
            "Content-Type": "application/json",
        }
        response = requests.post(
            f"{settings.TALPA_ORDER_EXPERIENCE_API}{order_id}/flowSteps",
            data=json.dumps(data, default=str),
            headers=headers,
        )

        if response.status_code == 200:
            logger.info("Talpa flow steps set successfully")
        else:
            logger.error(
                "Failed to set Talpa flow steps."
                f"Error: {response.status_code} {response.reason}. "
                f"Detail: {response.text}"
            )
            raise SetTalpaFlowStepsError(
                "Cannot set Talpa flow steps."
                f"Error: {response.status_code} {response.reason}."
            )

    @classmethod
    def set_order_details(cls, order):
        payment_period = settings.TALPA_ORDER_PAYMENT_MAX_PERIOD_MINS
        order.talpa_last_valid_purchase_time = tz.localtime(
            tz.now() + tz.timedelta(minutes=payment_period)
        )
        order.payment_type = OrderPaymentType.ONLINE_PAYMENT
        order.save(update_fields=["talpa_last_valid_purchase_time", "payment_type"])

    @classmethod
    def send_to_talpa(cls, order, ext_request=None):
        cls.set_order_details(order)
        order_data = cls.create_order_data(order, ext_request)
        order_data_raw = json.dumps(order_data, default=str)
        logger.info(f"Order data sent to talpa: {order_data_raw}")
        response = requests.post(cls.url, data=order_data_raw, headers=cls.headers)
        if response.status_code >= 300:
            logger.error(
                f"Create talpa order failed for order {order}. Error: {response.text}"
            )
            raise OrderCreationFailedError(_("Failed to create the order"))

        response_data = response.json()
        logger.info(
            f"Sending order to talpa completed. "
            f"Talpa order id: {response_data.get('orderId')}"
        )

        with transaction.atomic():
            order.talpa_order_id = response_data.get("orderId")
            order.talpa_subscription_id = response_data.get("subscriptionId")
            order.talpa_checkout_url = response_data.get("checkoutUrl")
            order.talpa_logged_in_checkout_url = response_data.get(
                "loggedInCheckoutUrl"
            )
            order.talpa_receipt_url = response_data.get("receiptUrl")
            order.talpa_update_card_url = response_data.get("updateCardUrl", "")
            order.save()
            talpa_order_item_id_mapping = {
                item["meta"][0]["value"]: item["orderItemId"]
                for item in response_data.get("items")
            }
            for order_item in order.order_items.select_related("product"):
                order_item.talpa_order_item_id = talpa_order_item_id_mapping.get(
                    str(order_item.id)
                )
                order_item.save()

        cls.set_flow_steps(order.talpa_order_id, str(order.customer.user.uuid))

        return response_data.get("loggedInCheckoutUrl")
