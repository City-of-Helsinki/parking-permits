import uuid

import pytest
from django.core.management import call_command

from parking_permits.models.order import OrderStatus
from parking_permits.tests.factories.order import OrderFactory


@pytest.mark.django_db()
def test_update_missing():
    order_id = uuid.uuid4()
    order = OrderFactory(
        talpa_order_id=order_id,
        talpa_receipt_url=_receipt_url(order_id),
        status=OrderStatus.CONFIRMED,
    )
    _run_command()

    order.refresh_from_db()
    assert order.talpa_update_card_url
    assert "/update-card?user=" in order.talpa_update_card_url


@pytest.mark.django_db()
def test_not_missing():
    order_id = uuid.uuid4()
    order = OrderFactory(
        talpa_order_id=order_id,
        talpa_receipt_url=_receipt_url(order_id),
        talpa_update_card_url="https://example.com",
        status=OrderStatus.CONFIRMED,
    )
    _run_command()

    order.refresh_from_db()
    assert order.talpa_update_card_url == "https://example.com"


@pytest.mark.django_db()
def test_order_not_confirmed():
    order_id = uuid.uuid4()
    order = OrderFactory(
        talpa_order_id=order_id,
        talpa_receipt_url=_receipt_url(order_id),
        status=OrderStatus.CANCELLED,
    )
    _run_command()

    order.refresh_from_db()
    assert not order.talpa_update_card_url


@pytest.mark.django_db()
def test_no_receipt_url():
    order_id = uuid.uuid4()
    order = OrderFactory(
        talpa_order_id=order_id,
        talpa_receipt_url="",
        status=OrderStatus.CONFIRMED,
    )
    _run_command()

    order.refresh_from_db()
    assert not order.talpa_update_card_url


def _run_command():
    call_command("set_order_talpa_update_card_urls")


def _receipt_url(order_id):
    return f"https://checkout-test.test.hel.ninja/{order_id}/receipt?user=9f8ce067-ac1c-4b01-84a0-7dc3146f52f2"
