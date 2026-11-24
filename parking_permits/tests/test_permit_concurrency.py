"""Exercise real PostgreSQL lock waits with independent committed connections."""

from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from threading import Event
from time import monotonic, sleep
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from dateutil.relativedelta import relativedelta
from django.db import IntegrityError, connection, connections, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import RequestFactory
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from parking_permits.customer_permit import CustomerPermit
from parking_permits.exceptions import DuplicatePermitError, OrderCreationFailedError
from parking_permits.models import Customer, Order, ParkingPermit, Refund
from parking_permits.models.order import OrderStatus, OrderType
from parking_permits.models.parking_permit import ContractType, ParkingPermitStatus
from parking_permits.resolvers import resolve_create_order
from parking_permits.tests.factories.customer import CustomerFactory
from parking_permits.tests.factories.order import OrderFactory
from parking_permits.tests.factories.parking_permit import ParkingPermitFactory
from parking_permits.tests.factories.permit_extension_request import (
    ParkingPermitExtensionRequestFactory,
)
from parking_permits.tests.factories.product import ProductFactory
from parking_permits.tests.factories.vehicle import VehicleFactory
from parking_permits.utils import get_end_time
from parking_permits.views import PaymentView

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def postgres_only(settings):
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL row locks and partial unique indexes")
    settings.TRAFICOM_MOCK = True
    settings.TRAFICOM_CHECK = False


def contend(operation, second_operation=None):
    """Hold the first operation uncommitted until PostgreSQL blocks the second.

    Unlike a timing-only thread launch, this establishes that the second request
    really runs while the first transaction still owns its locks.
    """
    ready = Event()
    release = Event()
    pids = Queue()

    def worker(first):
        connections.close_all()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET statement_timeout = '10s'")
                cursor.execute("SELECT pg_backend_pid()")
                pids.put((first, cursor.fetchone()[0]))
            try:
                with transaction.atomic():
                    result = (operation if first else second_operation or operation)()
                    if first:
                        ready.set()
                        assert release.wait(10), "First transaction was not released"
                return result
            except (DuplicatePermitError, OrderCreationFailedError) as exc:
                return exc
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(worker, True)
        try:
            assert ready.wait(10), "First operation failed before holding its locks"
            second = pool.submit(worker, False)
            backend_pids = dict(pids.get(timeout=10) for _ in range(2))
            deadline = monotonic() + 5
            while monotonic() < deadline:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_blocking_pids(%s)", [backend_pids[False]])
                    if backend_pids[True] in cursor.fetchone()[0]:
                        break
                if second.done():
                    pytest.fail(f"Second operation did not wait: {second.result()!r}")
                sleep(0.01)
            else:
                pytest.fail("Second connection did not block on the first")
        finally:
            release.set()
        return first.result(timeout=10), second.result(timeout=10)


def test_concurrent_customer_permit_creation():
    customer = CustomerFactory()
    vehicle = VehicleFactory()

    def create(address_id):
        return CustomerPermit(customer.pk).create(
            address_id, vehicle.registration_number
        )

    # Address.zone writes the address row. Use two eligible addresses so that
    # incidental lock cannot serialize the requests before the permit insert.
    first, second = contend(
        lambda: create(customer.primary_address_id),
        lambda: create(customer.other_address_id),
    )

    assert isinstance(first, ParkingPermit)
    assert isinstance(second, DuplicatePermitError)
    assert ParkingPermit.objects.filter(customer=customer, vehicle=vehicle).count() == 1


def test_second_purchase_inherits_concurrent_primary_type_change():
    customer = CustomerFactory()
    primary = ParkingPermitFactory(
        customer=customer,
        address=customer.primary_address,
        contract_type=ContractType.OPEN_ENDED,
        status=ParkingPermitStatus.DRAFT,
    )
    vehicle = VehicleFactory()
    _, secondary = contend(
        lambda: CustomerPermit(customer.pk).update(
            {"contract_type": ContractType.FIXED_PERIOD, "month_count": 3}, primary.pk
        ),
        lambda: CustomerPermit(customer.pk).create(
            customer.primary_address_id, vehicle.registration_number
        ),
    )
    primary.refresh_from_db()
    assert secondary.contract_type == primary.contract_type == ContractType.FIXED_PERIOD


def test_constraint_protects_bulk_status_changes():
    permit = ParkingPermitFactory()
    historical = ParkingPermitFactory(
        customer=permit.customer,
        vehicle=permit.vehicle,
        status=ParkingPermitStatus.CLOSED,
    )
    # Bulk updates bypass save() and must still respect the invariant.
    with pytest.raises(IntegrityError), transaction.atomic():
        ParkingPermit.objects.filter(pk=historical.pk).update(
            status=ParkingPermitStatus.VALID
        )
    historical.refresh_from_db()
    assert historical.status == ParkingPermitStatus.CLOSED


def test_concurrent_checkout():
    permit = ParkingPermitFactory()
    ProductFactory(
        zone=permit.parking_zone,
        start_date=timezone.localdate() - relativedelta(years=1),
        end_date=timezone.localdate() + relativedelta(years=1),
    )

    def checkout():
        request = RequestFactory().post("/")
        request.user = Customer.objects.get(pk=permit.customer_id).user
        return resolve_create_order(None, SimpleNamespace(context={"request": request}))

    with (
        patch(
            "helusers.oidc.RequestJWTAuthentication.authenticate",
            side_effect=lambda request: SimpleNamespace(user=request.user),
        ),
        patch(
            "parking_permits.resolvers.TalpaOrderManager.send_to_talpa",
            return_value="https://checkout.example",
        ) as send,
    ):
        first, second = contend(checkout)

    assert first == {"checkout_url": "https://checkout.example"}
    assert isinstance(second, OrderCreationFailedError)
    assert Order.objects.filter(permits=permit).count() == 1
    assert send.call_count == 1
    permit.refresh_from_db()
    assert permit.status == ParkingPermitStatus.PAYMENT_IN_PROGRESS


def notify(order):
    request = APIRequestFactory().post(
        "/",
        {"eventType": "PAYMENT_PAID", "orderId": str(order.talpa_order_id)},
        format="json",
    )
    return PaymentView.as_view()(request).status_code


@pytest.fixture
def payment_effects():
    # Keep network/email delivery out of the transaction tests, but count calls.
    with (
        patch("parking_permits.views.send_permit_email") as email,
        patch("parking_permits.views.sync_with_parkkihubi") as sync,
        patch("parking_permits.models.order.send_permit_email"),
        patch("parking_permits.models.order.sync_with_parkkihubi"),
    ):
        yield email, sync


def renewal():
    start = timezone.now().replace(day=5)
    permit = ParkingPermitFactory(
        status=ParkingPermitStatus.VALID,
        contract_type=ContractType.OPEN_ENDED,
        start_time=start,
        end_time=get_end_time(start, 1),
    )
    # CONFIRMED and paid_time are deliberately populated before the callback.
    order = OrderFactory(
        customer=permit.customer,
        type=OrderType.SUBSCRIPTION_RENEWED,
        status=OrderStatus.CONFIRMED,
        paid_time=timezone.now(),
    )
    order.permits.add(permit)
    return permit, order


@pytest.mark.parametrize("concurrent", [False, True])
def test_payment_retry_renews_once(concurrent, payment_effects):
    permit, order = renewal()
    expected_end = get_end_time(permit.start_time, 2)

    if concurrent:
        assert contend(lambda: notify(order)) == (200, 200)
    else:
        assert notify(order) == 200
        assert notify(order) == 200

    permit.refresh_from_db()
    order.refresh_from_db()
    assert permit.end_time == expected_end
    assert order.payment_processed_at is not None
    email, sync = payment_effects
    assert email.call_count == sync.call_count == 1


def test_different_orders_serialize_renewals(payment_effects):
    permit, order = renewal()
    other = OrderFactory(customer=permit.customer, type=OrderType.SUBSCRIPTION_RENEWED)
    other.permits.add(permit)
    expected_end = get_end_time(permit.start_time, 3)

    assert contend(lambda: notify(order), lambda: notify(other)) == (200, 200)

    permit.refresh_from_db()
    assert permit.end_time == expected_end


@pytest.mark.parametrize("concurrent", [False, True])
def test_reconciliation_retry_creates_one_refund(concurrent, payment_effects):
    start = timezone.now()
    primary = ParkingPermitFactory(
        status=ParkingPermitStatus.VALID,
        contract_type=ContractType.FIXED_PERIOD,
        start_time=start,
        end_time=start + relativedelta(months=1),
    )
    secondary = ParkingPermitFactory(
        customer=primary.customer,
        primary_vehicle=False,
        status=ParkingPermitStatus.VALID,
        contract_type=ContractType.FIXED_PERIOD,
        start_time=start,
        end_time=primary.end_time,
    )
    extension = ParkingPermitExtensionRequestFactory(permit=secondary, month_count=1)
    order = extension.order

    if concurrent:
        assert contend(lambda: notify(order)) == (400, 200)
    else:
        assert notify(order) == 400
        assert notify(order) == 200

    order.refresh_from_db()
    extension.refresh_from_db()
    secondary.refresh_from_db()
    assert order.payment_processed_at is not None
    assert extension.is_cancelled()
    assert secondary.end_time == primary.end_time
    assert Refund.objects.filter(orders=order).count() == 1


def test_failed_payment_processing_can_retry(payment_effects):
    permit, order = renewal()
    expected_end = get_end_time(permit.start_time, 2)
    email, sync = payment_effects
    sync.side_effect = RuntimeError("Simulated processing failure")

    with pytest.raises(RuntimeError, match="Simulated processing failure"):
        notify(order)
    order.refresh_from_db()
    permit.refresh_from_db()
    assert order.payment_processed_at is None
    assert permit.end_time == get_end_time(permit.start_time, 1)

    sync.side_effect = None
    assert notify(order) == 200
    permit.refresh_from_db()
    assert permit.end_time == expected_end


def test_concurrent_extension_payment_retries(payment_effects):
    start = timezone.now().replace(day=5)
    permit = ParkingPermitFactory(
        status=ParkingPermitStatus.VALID,
        contract_type=ContractType.FIXED_PERIOD,
        start_time=start,
        end_time=get_end_time(start, 1),
        month_count=1,
    )
    extension = ParkingPermitExtensionRequestFactory(permit=permit, month_count=1)

    assert contend(lambda: notify(extension.order)) == (200, 200)

    extension.refresh_from_db()
    permit.refresh_from_db()
    assert extension.is_approved()
    assert permit.month_count == 2
    assert permit.end_time == get_end_time(start, 2)


def test_migration_refuses_duplicates_without_removing_history():
    previous = [("parking_permits", "0079_delete_lowemissioncriteria_and_more")]
    target = [("parking_permits", "0080_prevent_duplicate_permits_and_payments")]
    permit = ParkingPermitFactory()
    historical = ParkingPermitFactory(
        customer=permit.customer,
        vehicle=permit.vehicle,
        status=ParkingPermitStatus.CLOSED,
    )
    executor = MigrationExecutor(connection)
    executor.migrate(previous)
    old_permits = executor.loader.project_state(previous).apps.get_model(
        "parking_permits", "ParkingPermit"
    )
    try:
        old_permits.objects.filter(pk=historical.pk).update(status="DRAFT")
        with pytest.raises(
            RuntimeError, match="Active customer/vehicle permit duplicates"
        ):
            MigrationExecutor(connection).migrate(target)
        assert (
            old_permits.objects.filter(
                pk__in=[permit.pk, historical.pk], status="DRAFT"
            ).count()
            == 2
        )
    finally:
        # Restore the schema even if the assertion fails, for subsequent tests.
        old_permits.objects.filter(pk=historical.pk).update(status="CLOSED")
        MigrationExecutor(connection).migrate(target)

    assert ParkingPermit.objects.filter(pk__in=[permit.pk, historical.pk]).count() == 2
    with pytest.raises(IntegrityError), transaction.atomic():
        ParkingPermit.objects.filter(pk=historical.pk).update(status="DRAFT")


def pending_checkout():
    customer = CustomerFactory()
    permit = ParkingPermitFactory(
        customer=customer,
        address=customer.primary_address,
        status=ParkingPermitStatus.PAYMENT_IN_PROGRESS,
    )
    ProductFactory(
        zone=permit.parking_zone,
        start_date=timezone.localdate() - relativedelta(years=1),
        end_date=timezone.localdate() + relativedelta(years=1),
    )
    order = OrderFactory(
        customer=customer,
        talpa_last_valid_purchase_time=timezone.now() - relativedelta(hours=1),
    )
    order.permits.add(permit)
    return permit, order


def test_timeout_does_not_overwrite_concurrent_payment(payment_effects, settings):
    settings.TALPA_ORDER_PAYMENT_WEBHOOK_WAIT_BUFFER_MINS = 0
    permit, order = pending_checkout()

    paid, fetched = contend(
        lambda: notify(order), lambda: CustomerPermit(permit.customer_id).get()
    )

    assert paid == 200
    order.refresh_from_db()
    permit.refresh_from_db()
    assert order.status == OrderStatus.CONFIRMED
    assert order.paid_time is not None
    assert order.payment_processed_at is not None
    assert permit.status == ParkingPermitStatus.VALID
    assert fetched[0].status == ParkingPermitStatus.VALID
    # Cancellation must not erase the replay guard and allow another delivery.
    assert notify(order) == 200
    email, sync = payment_effects
    assert email.call_count == sync.call_count == 1


@pytest.mark.parametrize("paid_field", ["paid_time", "payment_processed_at"])
def test_timeout_preserves_paid_draft_order(paid_field, settings):
    settings.TALPA_ORDER_PAYMENT_WEBHOOK_WAIT_BUFFER_MINS = 0
    permit, order = pending_checkout()
    recorded_at = timezone.now()
    Order.objects.filter(pk=order.pk).update(**{paid_field: recorded_at})

    fetched = CustomerPermit(permit.customer_id).get()

    order.refresh_from_db()
    permit.refresh_from_db()
    assert order.status == OrderStatus.DRAFT
    assert getattr(order, paid_field) == recorded_at
    assert permit.status == ParkingPermitStatus.PAYMENT_IN_PROGRESS
    assert fetched[0].status == ParkingPermitStatus.PAYMENT_IN_PROGRESS


@pytest.mark.parametrize("expired", [False, True])
def test_timeout_cancels_only_expired_unpaid_checkout(expired, settings):
    settings.TALPA_ORDER_PAYMENT_WEBHOOK_WAIT_BUFFER_MINS = 0 if expired else 120
    permit, order = pending_checkout()

    fetched = CustomerPermit(permit.customer_id).get()

    order.refresh_from_db()
    permit.refresh_from_db()
    assert order.status == (OrderStatus.CANCELLED if expired else OrderStatus.DRAFT)
    assert permit.status == (
        ParkingPermitStatus.CANCELLED
        if expired
        else ParkingPermitStatus.PAYMENT_IN_PROGRESS
    )
    assert fetched[0].status == permit.status
    assert order.paid_time is None
    assert order.payment_processed_at is None
