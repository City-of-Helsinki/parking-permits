from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from parking_permits.models import ParkingPermit, ParkingPermitExtensionRequest
from parking_permits.models.parking_permit import ParkingPermitStatus
from parking_permits.tests.factories.parking_permit import ParkingPermitFactory
from parking_permits.tests.factories.permit_extension_request import (
    ParkingPermitExtensionRequestFactory,
)


@pytest.mark.django_db()
def test_approved_ext_requests_not_cancelled():
    ext_request = ParkingPermitExtensionRequestFactory(
        status=ParkingPermitExtensionRequest.Status.APPROVED
    )
    ParkingPermitExtensionRequest.objects.update(
        created_at=timezone.localtime() - timedelta(minutes=40)
    )
    call_command("delete_draft_permits")
    ext_request.refresh_from_db()
    assert ext_request.is_approved()


@pytest.mark.django_db()
def test_recent_pending_ext_requests_not_cancelled():
    ext_request = ParkingPermitExtensionRequestFactory(
        status=ParkingPermitExtensionRequest.Status.PENDING
    )
    ParkingPermitExtensionRequest.objects.update(
        created_at=timezone.localtime() - timedelta(minutes=10)
    )
    call_command("delete_draft_permits")
    ext_request.refresh_from_db()
    assert ext_request.is_pending()


@pytest.mark.django_db()
def test_pending_ext_requests_cancelled():
    ext_request = ParkingPermitExtensionRequestFactory(
        status=ParkingPermitExtensionRequest.Status.PENDING
    )
    ParkingPermitExtensionRequest.objects.update(
        created_at=timezone.localtime() - timedelta(minutes=40)
    )
    call_command("delete_draft_permits")
    ext_request.refresh_from_db()
    assert ext_request.is_cancelled()


@pytest.mark.django_db()
def test_valid_permits_not_deleted():
    ParkingPermitFactory(status=ParkingPermitStatus.VALID)
    ParkingPermit.objects.update(
        created_at=timezone.localtime() - timedelta(minutes=40)
    )
    call_command("delete_draft_permits")
    assert ParkingPermit.objects.exists()


@pytest.mark.django_db()
def test_draft_permits_deleted():
    ParkingPermitFactory(
        status=ParkingPermitStatus.DRAFT,
    )
    ParkingPermit.objects.update(
        created_at=timezone.localtime() - timedelta(minutes=40)
    )
    call_command("delete_draft_permits")
    assert not ParkingPermit.objects.exists()


@pytest.mark.django_db()
def test_recent_draft_permits_not_deleted():
    ParkingPermitFactory(
        status=ParkingPermitStatus.DRAFT,
    )
    ParkingPermit.objects.update(
        created_at=timezone.localtime() - timedelta(minutes=10)
    )
    call_command("delete_draft_permits")
    assert ParkingPermit.objects.exists()


@pytest.mark.django_db()
def test_recent_draft_permits_not_deleted_with_hour_argument():
    ParkingPermitFactory(
        status=ParkingPermitStatus.DRAFT,
    )
    ParkingPermit.objects.update(
        created_at=timezone.localtime() - timedelta(minutes=40)
    )
    call_command("delete_draft_permits", hours=3)
    assert ParkingPermit.objects.exists()
