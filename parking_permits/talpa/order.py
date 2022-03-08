import json
import logging
from collections import defaultdict

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from parking_permits.exceptions import OrderCreationFailed
from parking_permits.models.order import OrderType
from parking_permits.utils import date_time_to_utc

logger = logging.getLogger("db")
DATE_FORMAT = "%d.%m.%Y"
TIME_FORMAT = "%d.%m.%Y %H:%M"


class TalpaOrderManager:
    url = settings.TALPA_ORDER_EXPERIENCE_API
    headers = {
        "api-key": settings.TALPA_API_KEY,
        "namespace": settings.NAMESPACE,
        "Content-type": "application/json",
    }

    @classmethod
    def _get_label(cls, permit, permit_index, has_multiple_permit):
        registration_number = permit.vehicle.registration_number
        manufacturer = permit.vehicle.manufacturer
        model = permit.vehicle.model
        car_info = f"{registration_number} {manufacturer} {model}"
        permit_info = f"{permit_index + 1}. Ajoneuvo, "
        return (permit_info + car_info) if has_multiple_permit else car_info

    @classmethod
    def _get_product_description(cls, product):
        start_time = product.start_date.strftime(DATE_FORMAT)
        end_time = product.end_date.strftime(DATE_FORMAT)
        return f"{start_time} - {end_time}"

    @classmethod
    def _create_item_data(cls, order, order_item):
        item = {
            "productId": str(order_item.product.talpa_product_id),
            "productName": order_item.product.name,
            "productDescription": cls._get_product_description(order_item.product),
            "unit": "kk",
            "startDate": date_time_to_utc(order_item.permit.start_time),
            "quantity": order_item.quantity,
            "priceNet": float(order_item.unit_price_net),
            "priceVat": float(order_item.unit_price_vat),
            "priceGross": float(order_item.unit_price),
            "vatPercentage": float(order_item.vat_percentage),
            "rowPriceNet": float(order_item.total_price_net),
            "rowPriceVat": float(order_item.total_price_vat),
            "rowPriceTotal": float(order_item.total_price),
            "meta": [
                {
                    "key": "sourceOrderItemId",
                    "value": str(order_item.id),
                    "visibleInCheckout": False,
                    "ordinal": 0,
                },
            ],
        }
        if order.order_type == OrderType.SUBSCRIPTION:
            item.update(
                {
                    "periodUnit": "monthly",
                    "periodFrequency": "1",
                }
            )
        return item

    @classmethod
    def _append_detail_meta(cls, item, permit):
        start_time = timezone.localtime(permit.start_time).strftime(DATE_FORMAT)
        item["meta"] += [
            {"key": "permitId", "value": str(permit.id), "visible": False},
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
        order_items = order.order_items.all().select_related("product", "permit")
        order_items_by_permit = defaultdict(list)
        for order_item in order_items:
            order_items_by_permit[order_item.permit].append(order_item)

        for permit in set([item.permit for item in order_items]):
            order_items_of_single_permit = []
            for index, order_item in enumerate(order_items_by_permit[permit]):
                if order_item.quantity:
                    item = cls._create_item_data(order, order_item)
                    item.update(
                        {
                            "productLabel": cls._get_label(
                                order_item.permit,
                                index,
                                len(order_items_by_permit[permit]) > 1,
                            ),
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
            "priceNet": float(order.total_price_net),
            "priceVat": float(order.total_price_vat),
            "priceTotal": float(order.total_price),
            "customer": customer,
            "items": items,
        }

    @classmethod
    def send_to_talpa(cls, order):
        order_data = cls._create_order_data(order)
        response = requests.post(
            cls.url, data=json.dumps(order_data), headers=cls.headers
        )
        if response.status_code >= 300:
            logger.error(
                f"Create talpa order failed for order {order}. Error: {response.text}"
            )
            raise OrderCreationFailed(_("Failed to create the order"))

        response_data = response.json()
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
