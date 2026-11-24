from decimal import Decimal

import pytest
from django.contrib import admin

from parking_permits.admin import OrderItemAdmin
from parking_permits.models import OrderItem
from parking_permits.tests.factories.order import OrderItemFactory


@pytest.mark.django_db
def test_order_item_admin_can_save_legacy_item_without_tariff_snapshots(rf):
    item = OrderItemFactory(vat=Decimal("0.2550"))
    form_class = OrderItemAdmin(OrderItem, admin.site).get_form(rf.get("/"), obj=item)
    form = form_class(
        instance=item,
        data={
            "order": item.order_id,
            "subscription": item.subscription_id,
            "product": item.product_id,
            "permit": item.permit_id,
            "unit_price": item.unit_price,
            "payment_unit_price": item.payment_unit_price,
            "vat": item.vat,
            "quantity": 7,
        },
    )

    assert form.is_valid(), form.errors
    form.save()
    item.refresh_from_db()
    assert item.quantity == 7
    assert item.regular_unit_price is None
    assert item.discounted_unit_price is None
