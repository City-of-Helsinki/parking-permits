import json
import logging

import numpy as np
import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from parking_permits.exceptions import OrderCreationFailed
from parking_permits.utils import DefaultOrderedDict, date_time_to_utc

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
    def _get_label(cls, permit):
        registration_number = permit.vehicle.registration_number
        manufacturer = permit.vehicle.manufacturer
        model = permit.vehicle.model
        car_info = f"Ajoneuvo: {registration_number} {manufacturer} {model}"
        return car_info

    @classmethod
    def _get_product_description(cls, order_item):
        if order_item.start_date and order_item.end_date:
            start_time = order_item.start_date.strftime(DATE_FORMAT)
            end_time = order_item.end_date.strftime(DATE_FORMAT)
            return f"{start_time} - {end_time}"
        return ""

    @classmethod
    def _create_item_data(cls, order, order_item):
        item = {
            "productId": str(order_item.product.talpa_product_id),
            "productName": order_item.product.name,
            "productDescription": cls._get_product_description(order_item),
            "unit": "kk",
            "startDate": date_time_to_utc(order_item.permit.start_time),
            "quantity": order_item.quantity,
            "priceNet": cls.round_up(float(order_item.payment_unit_price_net)),
            "priceVat": cls.round_up(float(order_item.payment_unit_price_vat)),
            "priceGross": cls.round_up(float(order_item.payment_unit_price)),
            "vatPercentage": cls.round_int(float(order_item.vat_percentage)),
            "rowPriceNet": cls.round_up(float(order_item.total_payment_price_net)),
            "rowPriceVat": cls.round_up(float(order_item.total_payment_price_vat)),
            "rowPriceTotal": cls.round_up(float(order_item.total_payment_price)),
            "meta": [
                {
                    "key": "sourceOrderItemId",
                    "value": str(order_item.id),
                    "visibleInCheckout": False,
                    "ordinal": 0,
                },
            ],
        }
        if order_item.permit.is_open_ended:
            item.update(
                {
                    "periodUnit": TALPA_SUBSCRIPTION_PERIOD_UNIT,
                    "periodFrequency": "1",
                }
            )
        return item

    @classmethod
    def _append_detail_meta(cls, item, permit):
        start_time = timezone.localtime(permit.start_time).strftime(DATE_FORMAT)
        item["meta"] += [
            {"key": "permitId", "value": str(permit.id), "visibleInCheckout": False},
            {
                "key": "permitDuration",
                "label": _("Duration of parking permit"),
                "value": _("Fixed period %(month)d kk") % {"month": permit.month_count},
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
                    "* The permit is valid from the selected start date once the payment has been accepted"
                ),
                "visibleInCheckout": True,
                "ordinal": 4,
            },
        ]
        if permit.end_time:
            end_time = timezone.localtime(permit.end_time).strftime(TIME_FORMAT)
            item["meta"].append(
                {
                    "key": "endDate",
                    "label": _("Parking permit expiration date"),
                    "value": end_time,
                    "visibleInCheckout": True,
                    "ordinal": 3,
                }
            )
        return item

    @classmethod
    def _create_customer_data(cls, customer):
        return {
            "firstName": customer.first_name,
            "lastName": customer.last_name,
            "email": customer.email,
        }

    @classmethod
    def _create_order_data(cls, order):
        items = []
        order_items = (
            order.order_items.all()
            .order_by("permit", "pk")
            .select_related("product", "permit")
        )
        order_items_by_permit = DefaultOrderedDict(list)
        for order_item in order_items:
            order_items_by_permit[order_item.permit].append(order_item)

        for permit in sorted(
            set([item.permit for item in order_items]),
            key=lambda p: p.is_secondary_vehicle,
        ):
            order_items_of_single_permit = []
            for index, order_item in enumerate(order_items_by_permit[permit]):
                if order_item.quantity:
                    item = cls._create_item_data(order, order_item)
                    if index == 0:
                        item.update(
                            {
                                "productLabel": cls._get_label(order_item.permit),
                            }
                        )
                    order_items_of_single_permit.append(item)

            # Append details of permit only to the last order item of permit.
            cls._append_detail_meta(order_items_of_single_permit[-1], permit)
            items += order_items_of_single_permit

        customer = cls._create_customer_data(order.customer)
        return {
            "namespace": settings.NAMESPACE,
            "user": str(order.customer.id),
            "priceNet": cls.round_up(float(order.total_payment_price_net)),
            "priceVat": cls.round_up(float(order.total_payment_price_vat)),
            "priceTotal": cls.round_up(float(order.total_payment_price)),
            "customer": customer,
            "items": items,
        }

    @classmethod
    def round_int(cls, v):
        return "{:0.0f}".format(np.round(v))

    @classmethod
    def round_up(cls, v):
        return "{:0.2f}".format(np.round(v, 3))

    @classmethod
    def send_to_talpa(cls, order):
        order_data = cls._create_order_data(order)
        order_data_raw = json.dumps(order_data, default=str)
        logger.info(f"Order data sent to talpa: {order_data_raw}")
        response = requests.post(cls.url, data=order_data_raw, headers=cls.headers)
        if response.status_code >= 300:
            logger.error(
                f"Create talpa order failed for order {order}. Error: {response.text}"
            )
            raise OrderCreationFailed(_("Failed to create the order"))

        response_data = response.json()
        logger.info(
            f"Sending order to talpa completed. Talpa order id: {response_data.get('orderId')}"
        )

        with transaction.atomic():
            order.talpa_order_id = response_data.get("orderId")
            order.talpa_subscription_id = response_data.get("subscriptionId")
            order.talpa_checkout_url = response_data.get("checkoutUrl")
            order.talpa_receipt_url = response_data.get("receiptUrl")
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
        return response_data.get("checkoutUrl")
