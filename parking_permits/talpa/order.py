import json
import logging

import requests
from django.conf import settings
from django.db import transaction
from django.utils.translation import gettext as _

from parking_permits.exceptions import OrderCreationFailed
from parking_permits.models.order import OrderType

logger = logging.getLogger(__name__)


class TalpaOrderManager:
    url = settings.TALPA_ORDER_EXPERIENCE_API
    headers = {
        "api-key": settings.TALPA_API_KEY,
        "namespace": settings.NAMESPACE,
        "Content-type": "application/json",
    }

    @classmethod
    def _create_item_data(cls, order, order_item):
        item = {
            "productId": str(order_item.product.talpa_product_id),
            "productName": order_item.product.name,
            "unit": "kk",
            "quantity": order_item.quantity,
            "rowPriceNet": float(order_item.unit_price_net),
            "rowPriceVat": float(order_item.unit_price_vat),
            "rowPriceTotal": float(order_item.unit_price),
            "priceNet": float(order_item.total_price_net),
            "priceVat": float(order_item.total_price_vat),
            "priceGross": float(order_item.total_price),
            "vatPercentage": float(order_item.vat_percentage),
            "meta": [
                {
                    "key": "sourceOrderItemId",
                    "value": str(order_item.id),
                    "visibleInCheckout": False,
                    "ordinal": 0,
                },
                {
                    "key": "vehicle",
                    "label": "Vehicle",
                    "value": str(order_item.permit.vehicle),
                    "visibleInCheckout": True,
                    "ordinal": 1,
                },
            ],
        }
        if order.order_type == OrderType.SUBSCRIPTION:
            item.update(
                {
                    "period_unit": "monthly",
                    "period_frequency": "1",
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
        order_items = order.order_items.all().select_related("product", "permit")
        items = [cls._create_item_data(order, order_item) for order_item in order_items]
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
            order.talpa_order_id = response_data["orderId"]
            order.talpa_subscription_id = response_data["subscriptionId"]
            order.talpa_checkout_url = response_data["checkoutUrl"]
            order.talpa_receipt_url = response_data["receiptUrl"]
            order.save()
            talpa_order_item_id_mapping = {
                item["meta"][0]["value"]: item["orderItemId"]
                for item in response_data["items"]
            }
            for order_item in order.order_items.select_related("product"):
                order_item.talpa_order_item_id = talpa_order_item_id_mapping.get(
                    str(order_item.id)
                )
                order_item.save()
        return response_data["checkoutUrl"]
