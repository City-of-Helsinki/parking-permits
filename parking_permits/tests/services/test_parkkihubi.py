from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone
from freezegun import freeze_time

from parking_permits.exceptions import ParkkihubiPermitError
from parking_permits.models.parking_permit import ContractType, ParkingPermitStatus
from parking_permits.services.parkkihubi import Parkkihubi, sync_with_parkkihubi
from parking_permits.tests.factories.parking_permit import ParkingPermitFactory
from parking_permits.tests.factories.vehicle import TemporaryVehicleFactory
from parking_permits.tests.models.test_product import MockResponse


class TestParkkihubi:
    @pytest.fixture()
    def frozen_time(self):
        with freeze_time(datetime(2024, 3, 15, 0, 0, tzinfo=UTC)):
            yield

    @pytest.fixture()
    def parkkihubi_overrides(self, settings):
        settings.PARKKIHUBI_PERMIT_SERIES = "991"
        settings.PARKKIHUBI_DOMAIN = "HKI_TEST"
        settings.DEBUG_SKIP_PARKKIHUBI_SYNC = False
        yield

    @pytest.fixture()
    def permit(self, frozen_time):
        now = timezone.now()
        return ParkingPermitFactory(
            status=ParkingPermitStatus.VALID,
            contract_type=ContractType.OPEN_ENDED,
            start_time=now - timedelta(days=30),
            end_time=now + timedelta(days=30),
            month_count=1,
            vehicle__registration_number="KEO-432",
            parking_zone__name="Zone A",
        )

    @pytest.mark.django_db()
    @patch("requests.patch", return_value=MockResponse(200))
    def test_sync_with_parkkihubi_debug(
        self,
        mock_patch,
        permit,
        settings,
        parkkihubi_overrides,
    ):
        settings.DEBUG_SKIP_PARKKIHUBI_SYNC = True
        sync_with_parkkihubi(permit)
        mock_patch.assert_not_called()
        permit.refresh_from_db()
        assert not permit.synced_with_parkkihubi

    @pytest.mark.django_db()
    @patch("requests.post", return_value=MockResponse(201))
    @patch("requests.patch", return_value=MockResponse(404))
    def test_sync_with_parkkihubi_is_new(
        self,
        mock_patch,
        mock_post,
        permit,
        parkkihubi_overrides,
    ):
        sync_with_parkkihubi(permit)
        mock_post.assert_called()
        mock_patch.assert_called()
        permit.refresh_from_db()
        assert permit.synced_with_parkkihubi

    @pytest.mark.django_db()
    @patch("requests.post", return_value=MockResponse(201))
    @patch("requests.patch", return_value=MockResponse(200))
    def test_sync_with_parkkihubi_exists(
        self,
        mock_patch,
        mock_post,
        permit,
        parkkihubi_overrides,
    ):
        sync_with_parkkihubi(permit)
        mock_post.assert_not_called()
        mock_patch.assert_called()
        permit.refresh_from_db()
        assert permit.synced_with_parkkihubi

    @pytest.mark.django_db()
    @patch("requests.post", return_value=MockResponse(201))
    def test_create(
        self,
        mock_post,
        permit,
        parkkihubi_overrides,
    ):
        Parkkihubi(permit).create()
        mock_post.assert_called()
        permit.refresh_from_db()
        assert permit.synced_with_parkkihubi

    @pytest.mark.django_db()
    @patch("requests.post", return_value=MockResponse(400))
    def test_create_error(
        self,
        mock_post,
        permit,
        parkkihubi_overrides,
    ):
        with pytest.raises(ParkkihubiPermitError):
            Parkkihubi(permit).create()
        mock_post.assert_called()
        permit.refresh_from_db()
        assert not permit.synced_with_parkkihubi

    @pytest.mark.django_db()
    @patch("requests.patch", return_value=MockResponse(400))
    def test_update_error(
        self,
        mock_patch,
        permit,
        parkkihubi_overrides,
    ):
        with pytest.raises(ParkkihubiPermitError):
            Parkkihubi(permit).update()
        mock_patch.assert_called()
        permit.refresh_from_db()
        assert not permit.synced_with_parkkihubi

    @pytest.mark.django_db()
    def test_get_payload(self, permit, parkkihubi_overrides):
        data = Parkkihubi(permit).get_payload()

        assert data == {
            "series": "991",
            "domain": "HKI_TEST",
            "external_id": str(permit.pk),
            "properties": {"permit_type": "RESIDENT"},
            "subjects": [
                {
                    "start_time": datetime(2024, 2, 14, 0, 0, tzinfo=UTC),
                    "end_time": datetime(2024, 4, 14, 0, 0, tzinfo=UTC),
                    "registration_number": "KEO-432",
                }
            ],
            "areas": [
                {
                    "start_time": datetime(2024, 2, 14, 0, 0, tzinfo=UTC),
                    "end_time": datetime(2024, 4, 14, 0, 0, tzinfo=UTC),
                    "area": "Zone A",
                }
            ],
        }

    @pytest.mark.django_db()
    def test_get_payload_with_temp_vehicle(self, permit, parkkihubi_overrides):
        now = timezone.now()

        temp_vehicle = TemporaryVehicleFactory(
            vehicle__registration_number="IOL-897",
            start_time=now - timedelta(days=3),
            end_time=now + timedelta(days=6),
            is_active=True,
        )
        permit.temp_vehicles.add(temp_vehicle)

        data = Parkkihubi(permit).get_payload()
        assert data == {
            "series": "991",
            "domain": "HKI_TEST",
            "external_id": str(permit.pk),
            "properties": {"permit_type": "RESIDENT"},
            "subjects": [
                {
                    "start_time": datetime(2024, 2, 14, 0, 0, tzinfo=UTC),
                    "end_time": datetime(2024, 3, 12, 0, 0, tzinfo=UTC),
                    "registration_number": "KEO-432",
                },
                {
                    "start_time": datetime(2024, 3, 12, 0, 0, tzinfo=UTC),
                    "end_time": datetime(2024, 3, 21, 0, 0, tzinfo=UTC),
                    "registration_number": "IOL-897",
                },
                {
                    "start_time": datetime(2024, 3, 21, 0, 0, tzinfo=UTC),
                    "end_time": datetime(2024, 4, 14, 0, 0, tzinfo=UTC),
                    "registration_number": "KEO-432",
                },
            ],
            "areas": [
                {
                    "start_time": datetime(2024, 2, 14, 0, 0, tzinfo=UTC),
                    "end_time": datetime(2024, 4, 14, 0, 0, tzinfo=UTC),
                    "area": "Zone A",
                }
            ],
        }

    @pytest.mark.django_db()
    def test_get_payload_with_inactive_temp_vehicle(self, permit, parkkihubi_overrides):
        now = timezone.now()
        temp_vehicle = TemporaryVehicleFactory(
            vehicle__registration_number="IOL-897",
            start_time=now - timedelta(days=3),
            end_time=now + timedelta(days=6),
            is_active=False,
        )
        permit.temp_vehicles.add(temp_vehicle)

        data = Parkkihubi(permit).get_payload()
        assert data == {
            "series": "991",
            "domain": "HKI_TEST",
            "external_id": str(permit.pk),
            "properties": {"permit_type": "RESIDENT"},
            "subjects": [
                {
                    "start_time": datetime(2024, 2, 14, 0, 0, tzinfo=UTC),
                    "end_time": datetime(2024, 4, 14, 0, 0, tzinfo=UTC),
                    "registration_number": "KEO-432",
                },
            ],
            "areas": [
                {
                    "start_time": datetime(2024, 2, 14, 0, 0, tzinfo=UTC),
                    "end_time": datetime(2024, 4, 14, 0, 0, tzinfo=UTC),
                    "area": "Zone A",
                }
            ],
        }

    @pytest.mark.django_db()
    def test_get_payload_with_multiple_temp_vehicles(
        self, permit, parkkihubi_overrides
    ):
        now = timezone.now()
        temp_vehicles = [
            TemporaryVehicleFactory(
                vehicle__registration_number="IOL-897",
                start_time=now - timedelta(days=3),
                end_time=now + timedelta(days=6),
                is_active=True,
            ),
            TemporaryVehicleFactory(
                vehicle__registration_number="KYZ-555",
                start_time=now + timedelta(days=10),
                end_time=now + timedelta(days=12),
                is_active=True,
            ),
        ]
        permit.temp_vehicles.set(temp_vehicles)

        data = Parkkihubi(permit).get_payload()
        assert data == {
            "series": "991",
            "domain": "HKI_TEST",
            "external_id": str(permit.pk),
            "properties": {"permit_type": "RESIDENT"},
            "subjects": [
                {
                    "start_time": datetime(2024, 2, 14, 0, 0, tzinfo=UTC),
                    "end_time": datetime(2024, 3, 12, 0, 0, tzinfo=UTC),
                    "registration_number": "KEO-432",
                },
                {
                    "start_time": datetime(2024, 3, 12, 0, 0, tzinfo=UTC),
                    "end_time": datetime(2024, 3, 21, 0, 0, tzinfo=UTC),
                    "registration_number": "IOL-897",
                },
                {
                    "start_time": datetime(2024, 3, 21, 0, 0, tzinfo=UTC),
                    "end_time": datetime(2024, 3, 25, 0, 0, tzinfo=UTC),
                    "registration_number": "KEO-432",
                },
                {
                    "start_time": datetime(2024, 3, 25, 0, 0, tzinfo=UTC),
                    "end_time": datetime(2024, 3, 27, 0, 0, tzinfo=UTC),
                    "registration_number": "KYZ-555",
                },
                {
                    "start_time": datetime(2024, 3, 27, 0, 0, tzinfo=UTC),
                    "end_time": datetime(2024, 4, 14, 0, 0, tzinfo=UTC),
                    "registration_number": "KEO-432",
                },
            ],
            "areas": [
                {
                    "start_time": datetime(2024, 2, 14, 0, 0, tzinfo=UTC),
                    "end_time": datetime(2024, 4, 14, 0, 0, tzinfo=UTC),
                    "area": "Zone A",
                }
            ],
        }

    @pytest.mark.django_db()
    def test_get_payload_with_multiple_temp_vehicles_overlapping(
        self, permit, parkkihubi_overrides
    ):
        now = timezone.now()
        temp_vehicles = [
            TemporaryVehicleFactory(
                vehicle__registration_number="IOL-897",
                start_time=now - timedelta(days=3),
                end_time=now + timedelta(days=6),
                is_active=True,
            ),
            TemporaryVehicleFactory(
                vehicle__registration_number="KYZ-555",
                start_time=now + timedelta(days=3),
                end_time=now + timedelta(days=8),
                is_active=True,
            ),
        ]
        permit.temp_vehicles.set(temp_vehicles)

        data = Parkkihubi(permit).get_payload()
        assert data == {
            "series": "991",
            "domain": "HKI_TEST",
            "external_id": str(permit.pk),
            "properties": {"permit_type": "RESIDENT"},
            "subjects": [
                {
                    "start_time": datetime(2024, 2, 14, 0, 0, tzinfo=UTC),
                    "end_time": datetime(2024, 3, 12, 0, 0, tzinfo=UTC),
                    "registration_number": "KEO-432",
                },
                {
                    "start_time": datetime(2024, 3, 12, 0, 0, tzinfo=UTC),
                    "end_time": datetime(2024, 3, 18, 0, 0, tzinfo=UTC),
                    "registration_number": "IOL-897",
                },
                {
                    "start_time": datetime(2024, 3, 18, 0, 0, tzinfo=UTC),
                    "end_time": datetime(2024, 3, 23, 0, 0, tzinfo=UTC),
                    "registration_number": "KYZ-555",
                },
                {
                    "start_time": datetime(2024, 3, 23, 0, 0, tzinfo=UTC),
                    "end_time": datetime(2024, 4, 14, 0, 0, tzinfo=UTC),
                    "registration_number": "KEO-432",
                },
            ],
            "areas": [
                {
                    "start_time": datetime(2024, 2, 14, 0, 0, tzinfo=UTC),
                    "end_time": datetime(2024, 4, 14, 0, 0, tzinfo=UTC),
                    "area": "Zone A",
                }
            ],
        }

    @pytest.mark.django_db()
    def test_get_payload_with_temp_vehicle_overlapping_permit_end_date(
        self, permit, parkkihubi_overrides
    ):
        now = timezone.now()
        temp_vehicle = TemporaryVehicleFactory(
            vehicle__registration_number="IOL-897",
            start_time=now - timedelta(days=25),
            end_time=now + timedelta(days=32),
            is_active=True,
        )
        permit.temp_vehicles.add(temp_vehicle)

        data = Parkkihubi(permit).get_payload()

        assert data == {
            "series": "991",
            "domain": "HKI_TEST",
            "external_id": str(permit.pk),
            "properties": {"permit_type": "RESIDENT"},
            "subjects": [
                {
                    "start_time": datetime(2024, 2, 14, 0, 0, tzinfo=UTC),
                    "end_time": datetime(2024, 2, 19, 0, 0, tzinfo=UTC),
                    "registration_number": "KEO-432",
                },
                {
                    "start_time": datetime(2024, 2, 19, 0, 0, tzinfo=UTC),
                    "end_time": datetime(2024, 4, 14, 0, 0, tzinfo=UTC),
                    "registration_number": "IOL-897",
                },
            ],
            "areas": [
                {
                    "start_time": datetime(2024, 2, 14, 0, 0, tzinfo=UTC),
                    "end_time": datetime(2024, 4, 14, 0, 0, tzinfo=UTC),
                    "area": "Zone A",
                }
            ],
        }

    @pytest.mark.django_db()
    def test_get_payload_with_temp_vehicle_starting_after_permit_end_date(
        self, permit, parkkihubi_overrides
    ):
        temp_vehicle = TemporaryVehicleFactory(
            vehicle__registration_number="IOL-897",
            start_time=permit.end_time + timedelta(days=3),
            end_time=permit.end_time + timedelta(days=6),
            is_active=True,
        )
        permit.temp_vehicles.add(temp_vehicle)

        data = Parkkihubi(permit).get_payload()

        assert data == {
            "series": "991",
            "domain": "HKI_TEST",
            "external_id": str(permit.pk),
            "properties": {"permit_type": "RESIDENT"},
            "subjects": [
                {
                    "start_time": datetime(2024, 2, 14, 0, 0, tzinfo=UTC),
                    "end_time": datetime(2024, 4, 14, 0, 0, tzinfo=UTC),
                    "registration_number": "KEO-432",
                }
            ],
            "areas": [
                {
                    "start_time": datetime(2024, 2, 14, 0, 0, tzinfo=UTC),
                    "end_time": datetime(2024, 4, 14, 0, 0, tzinfo=UTC),
                    "area": "Zone A",
                }
            ],
        }
