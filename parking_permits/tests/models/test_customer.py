from datetime import date, datetime
from decimal import Decimal

import pytest
from django.test import TestCase
from django.utils import timezone
from freezegun import freeze_time

from parking_permits.exceptions import CustomerCannotBeAnonymizedError
from parking_permits.models.company import Company
from parking_permits.models.driving_class import DrivingClass
from parking_permits.models.driving_licence import DrivingLicence
from parking_permits.models.order import SubscriptionStatus
from parking_permits.models.parking_permit import (
    ContractType,
    ParkingPermitEventFactory,
    ParkingPermitStatus,
)
from parking_permits.models.vehicle import VehicleUser
from parking_permits.tests.factories.address import AddressFactory
from parking_permits.tests.factories.customer import CustomerFactory
from parking_permits.tests.factories.order import (
    OrderFactory,
    OrderItemFactory,
    SubscriptionFactory,
)
from parking_permits.tests.factories.parking_permit import ParkingPermitFactory
from parking_permits.tests.factories.product import ProductFactory
from parking_permits.tests.factories.refund import RefundFactory
from parking_permits.tests.factories.vehicle import VehicleFactory


class TestCustomer(TestCase):
    def test_anonymized_customer_cannot_be_anonymized(self):
        with freeze_time(timezone.make_aware(datetime(2020, 12, 31))):
            customer = CustomerFactory(is_anonymized=True)
        with freeze_time(timezone.make_aware(datetime(2022, 12, 31, 0, 0, 1))):
            self.assertFalse(customer.can_be_anonymized)

    def test_customer_modified_more_than_two_years_ago_can_be_anonymized(self):
        with freeze_time(timezone.make_aware(datetime(2020, 12, 31))):
            customer = CustomerFactory()
        with freeze_time(timezone.make_aware(datetime(2022, 12, 31, 0, 0, 1))):
            self.assertTrue(customer.can_be_anonymized)

    def test_customer_modified_recently_can_not_be_deleted(self):
        with freeze_time(timezone.make_aware(datetime(2021, 1, 1))):
            customer = CustomerFactory()
        with freeze_time(timezone.make_aware(datetime(2022, 12, 31))):
            self.assertFalse(customer.can_be_anonymized)

    def test_customer_has_closed_permit_modified_more_than_two_years_ago_can_be_anonymized(
        self,
    ):
        with freeze_time(timezone.make_aware(datetime(2020, 12, 31))):
            customer = CustomerFactory()
            ParkingPermitFactory(customer=customer, status=ParkingPermitStatus.CLOSED)
        with freeze_time(timezone.make_aware(datetime(2022, 12, 31, 0, 0, 1))):
            self.assertTrue(customer.can_be_anonymized)

    def test_customer_has_end_time_recently_can_not_be_anonymized(self):
        with freeze_time(timezone.make_aware(datetime(2020, 12, 31))):
            customer = CustomerFactory()
            ParkingPermitFactory(
                customer=customer,
                status=ParkingPermitStatus.CLOSED,
                end_time=timezone.make_aware(datetime(2021, 12, 31)),
            )
        with freeze_time(timezone.make_aware(datetime(2022, 12, 31, 0, 0, 1))):
            self.assertFalse(customer.can_be_anonymized)

    def test_customer_has_valid_permit_can_not_be_anonymized(self):
        with freeze_time(timezone.make_aware(datetime(2020, 12, 31))):
            customer = CustomerFactory()
            ParkingPermitFactory(customer=customer, status=ParkingPermitStatus.VALID)
        with freeze_time(timezone.make_aware(datetime(2022, 12, 31, 0, 0, 1))):
            self.assertFalse(customer.can_be_anonymized)

    def test_customer_with_confirmed_subscription_can_not_be_anonymized(self):
        with freeze_time(timezone.make_aware(datetime(2020, 12, 31))):
            customer = CustomerFactory()
            subscription = SubscriptionFactory(status=SubscriptionStatus.CONFIRMED)
            order = OrderFactory(customer=customer)
            OrderItemFactory(
                order=order,
                subscription=subscription,
            )
        with freeze_time(timezone.make_aware(datetime(2022, 12, 31, 0, 0, 1))):
            self.assertFalse(customer.can_be_anonymized)


class AnonymizeAllUserDataTestCase(TestCase):
    permit_statistic_fields = (
        "parking_zone",
        "next_parking_zone",
        "start_time",
        "end_time",
        "status",
        "type",
        "contract_type",
        "primary_vehicle",
        "month_count",
    )

    order_statistic_fields = (
        "status",
        "type",
        "payment_type",
        "paid_time",
        "parking_zone_name",
        "created_at",
    )

    order_item_statistic_fields = (
        "unit_price",
        "payment_unit_price",
        "vat",
        "quantity",
        "start_time",
        "end_time",
    )

    subscription_statistic_fields = (
        "status",
        "cancel_reason",
    )

    address_statistic_fields = (
        "street_name",
        "street_number",
        "postal_code",
        "city",
    )

    vehicle_statistic_fields = (
        "power_type",
        "vehicle_class",
        "manufacturer",
        "model",
        "registration_number",
        "emission",
        "emission_type",
        "euro_class",
    )

    refund_statistic_fields = (
        "amount",
        "status",
        "vat",
        "accepted_at",
    )

    def setUp(self):
        with freeze_time(timezone.make_aware(datetime(2020, 12, 31))):
            self.primary_address = AddressFactory()
            self.other_address = AddressFactory()

            self.customer = CustomerFactory(
                primary_address=self.primary_address,
                other_address=self.other_address,
            )

            self.company = Company.objects.create(
                name="Oy Firma Ab",
                business_id="1234567-8",
                company_owner=self.customer,
                address=AddressFactory(),
            )

            self.vehicle = VehicleFactory()
            self.vehicle_user = VehicleUser.objects.create(
                national_id_number=self.customer.national_id_number
            )
            self.vehicle.users.add(self.vehicle_user)

            driving_class = DrivingClass.objects.create(identifier="M1")
            self.driving_licence = DrivingLicence.objects.create(
                customer=self.customer,
                active=True,
                start_date=date(1990, 1, 1),
            )
            self.driving_licence.driving_classes.add(driving_class)

            self.another_customer = CustomerFactory()

            self.another_driving_licence = DrivingLicence.objects.create(
                customer=self.another_customer,
                active=True,
                start_date=date(1980, 1, 1),
            )
            self.another_driving_licence.driving_classes.add(driving_class)

            self.unrelated_vehicle_user = VehicleUser.objects.create(
                national_id_number=self.another_customer.national_id_number
            )
            self.vehicle.users.add(self.unrelated_vehicle_user)

            self.permit = ParkingPermitFactory(
                customer=self.customer,
                vehicle=self.vehicle,
                parking_zone=self.customer.primary_address.zone,
                address=self.customer.primary_address,
                contract_type=ContractType.OPEN_ENDED,
            )

            self.subscription = SubscriptionFactory(status=SubscriptionStatus.CANCELLED)

            self.order = OrderFactory(customer=self.customer)
            self.order.vehicles = [self.vehicle.registration_number]
            self.order.save()

            unit_price = Decimal(30)
            product = ProductFactory(
                unit_price=unit_price,
            )
            self.order_item = OrderItemFactory(
                order=self.order,
                permit=self.permit,
                product=product,
                subscription=self.subscription,
            )

            self.another_vehicle = VehicleFactory()
            self.another_vehicle.users.add(self.vehicle_user)

            self.refunded_permit = ParkingPermitFactory(
                customer=self.customer,
                vehicle=self.another_vehicle,
                parking_zone=self.customer.primary_address.zone,
                address=self.customer.primary_address,
            )

            self.refunded_order = OrderFactory(
                customer=self.customer,
            )
            self.refund = RefundFactory(
                amount=100,
                vat=Decimal(0.24),
                name="Refund name",
                description="Refund description",
            )
            self.refund.orders.add(self.refunded_order)

            self.permit_event = ParkingPermitEventFactory.make_end_permit_event(
                permit=self.refunded_permit
            )

    def refresh_test_objects(self):
        self.customer.refresh_from_db()
        self.customer.user.refresh_from_db()
        self.order.refresh_from_db()
        self.refunded_order.refresh_from_db()
        self.refund.refresh_from_db()
        self.permit.refresh_from_db()
        self.refunded_permit.refresh_from_db()
        self.company.refresh_from_db()
        self.company.address.refresh_from_db()
        self.primary_address.refresh_from_db()
        self.other_address.refresh_from_db()
        self.permit_event.refresh_from_db()

    def create_pre_anon_snapshot(self, object, fields: tuple[str]):
        # Naive helper for creating pre-anon-data dicts.
        # Assumes that the inputed object has all the listed fields.
        return {field: getattr(object, field) for field in fields}

    def test_anonymize_customer_data(self):
        pre_anon_user_uuid = self.customer.user.uuid

        pre_anon_permit_data = self.create_pre_anon_snapshot(
            self.permit, self.permit_statistic_fields
        )
        pre_anon_refunded_permit_data = self.create_pre_anon_snapshot(
            self.refunded_permit, self.permit_statistic_fields
        )

        pre_anon_order_data = self.create_pre_anon_snapshot(
            self.order, self.order_statistic_fields
        )
        pre_anon_refunded_order_data = self.create_pre_anon_snapshot(
            self.refunded_order, self.order_statistic_fields
        )

        pre_anon_order_item_data = self.create_pre_anon_snapshot(
            self.order_item, self.order_item_statistic_fields
        )

        pre_anon_subscription_data = self.create_pre_anon_snapshot(
            self.subscription, self.subscription_statistic_fields
        )

        pre_anon_primary_address_data = self.create_pre_anon_snapshot(
            self.primary_address, self.address_statistic_fields
        )
        pre_anon_secondary_address_data = self.create_pre_anon_snapshot(
            self.other_address, self.address_statistic_fields
        )
        pre_anon_company_address_data = self.create_pre_anon_snapshot(
            self.company.address, self.address_statistic_fields
        )

        pre_anon_vehicle_data = self.create_pre_anon_snapshot(
            self.vehicle, self.vehicle_statistic_fields
        )
        pre_anon_another_vehicle_data = self.create_pre_anon_snapshot(
            self.another_vehicle, self.vehicle_statistic_fields
        )

        pre_anon_refund_data = self.create_pre_anon_snapshot(
            self.refund, self.refund_statistic_fields
        )

        self.customer.anonymize_all_data()

        self.refresh_test_objects()

        self.assert_anonymized_customer_gdpr_fields()
        self.assert_anonymized_user_gdpr_fields(pre_anon_user_uuid=pre_anon_user_uuid)

        self.assert_anonymized_order_gdpr_fields(order=self.order)
        self.assert_anonymized_order_gdpr_fields(order=self.refunded_order)

        self.assert_anonymized_permit_gdpr_fields(permit=self.permit)
        self.assert_anonymized_permit_gdpr_fields(permit=self.refunded_permit)

        self.assert_anonymized_refund_gdpr_fields()
        self.assert_anonymized_company()

        self.assert_related_vehicle_user_is_deleted()
        self.assert_unrelated_vehicle_user_still_exists()

        self.assert_related_driving_licence_is_deleted()
        self.assert_unrelated_driving_licence_still_exists()

        self.assert_anonymization_clears_permit_event_context()

        self.assert_anonymization_preserves_permit_statistical_data(
            permit=self.permit, pre_anon_permit_data=pre_anon_permit_data
        )
        self.assert_anonymization_preserves_permit_statistical_data(
            permit=self.refunded_permit,
            pre_anon_permit_data=pre_anon_refunded_permit_data,
        )

        self.assert_anonymization_preserves_order_statistical_data(
            order=self.order, pre_anon_order_data=pre_anon_order_data
        )
        self.assert_anonymization_preserves_order_statistical_data(
            order=self.refunded_order, pre_anon_order_data=pre_anon_refunded_order_data
        )

        self.assert_anonymization_preserves_order_item_statistical_data(
            pre_anon_order_item_data=pre_anon_order_item_data
        )

        self.assert_anonymization_preserves_subscription_statistical_data(
            pre_anon_subscription_data=pre_anon_subscription_data
        )

        self.assert_anonymization_preserves_vehicle_statistical_data(
            vehicle=self.vehicle, pre_anon_vehicle_data=pre_anon_vehicle_data
        )
        self.assert_anonymization_preserves_vehicle_statistical_data(
            vehicle=self.another_vehicle,
            pre_anon_vehicle_data=pre_anon_another_vehicle_data,
        )

        self.assert_anonymization_preserves_address_statistical_data(
            address=self.primary_address,
            pre_anon_address_data=pre_anon_primary_address_data,
        )
        self.assert_anonymization_preserves_address_statistical_data(
            address=self.other_address,
            pre_anon_address_data=pre_anon_secondary_address_data,
        )
        self.assert_anonymization_preserves_address_statistical_data(
            address=self.company.address,
            pre_anon_address_data=pre_anon_company_address_data,
        )

        self.assert_anonymization_preserves_refund_statistical_data(
            pre_anon_refund_data=pre_anon_refund_data
        )

    def assert_anonymized_customer_gdpr_fields(self):
        customer = self.customer
        self.assertEqual(customer.first_name, "Anonymized")
        self.assertEqual(customer.last_name, "Customer")
        self.assertEqual(customer.national_id_number, f"XX-ANON-{customer.pk:06d}")
        self.assertEqual(customer.email, "")
        self.assertEqual(customer.phone_number, "")
        self.assertEqual(customer.primary_address_apartment, "")
        self.assertEqual(customer.primary_address_apartment_sv, "")
        self.assertEqual(customer.other_address_apartment, "")
        self.assertEqual(customer.other_address_apartment_sv, "")
        self.assertEqual(customer.source_id, "")
        self.assertEqual(customer.is_anonymized, True)

    def assert_anonymized_user_gdpr_fields(self, pre_anon_user_uuid):
        user = self.customer.user
        self.assertEqual(user.first_name, "")
        self.assertEqual(user.last_name, "")
        self.assertEqual(
            user.email, f"anonymized-{self.customer.pk}@anonymized.invalid"
        )
        self.assertEqual(user.username, f"anonymized-{self.customer.pk}")
        self.assertEqual(str(user.uuid), pre_anon_user_uuid)

    def assert_anonymized_order_gdpr_fields(self, order):
        self.assertEqual(order.address_text, "")
        self.assertEqual(order.talpa_checkout_url, "")
        self.assertEqual(order.talpa_logged_in_checkout_url, "")
        self.assertEqual(order.talpa_receipt_url, "")
        self.assertEqual(order.talpa_update_card_url, "")
        self.assertEqual(order.vehicles, [])

    def assert_anonymized_permit_gdpr_fields(self, permit):
        self.assertEqual(permit.address_apartment, "")
        self.assertEqual(permit.address_apartment_sv, "")
        self.assertEqual(permit.next_address_apartment, "")
        self.assertEqual(permit.next_address_apartment_sv, "")
        self.assertEqual(permit.description, "")

    def assert_anonymized_refund_gdpr_fields(self):
        refund = self.refund
        self.assertEqual(refund.name, "")
        self.assertEqual(refund.iban, "")
        self.assertEqual(refund.description, "")

    def assert_anonymized_company(self):
        company = self.company

        self.assertEqual(company.name, f"Anonymized Company {self.customer.pk}")
        self.assertEqual(company.business_id, f"ANON-{self.customer.pk:07d}")

    def assert_related_driving_licence_is_deleted(self):
        licence_exists = DrivingLicence.objects.filter(
            id=self.driving_licence.id
        ).exists()
        self.assertFalse(licence_exists)

    def assert_unrelated_driving_licence_still_exists(self):
        licence_exists = DrivingLicence.objects.filter(
            id=self.another_driving_licence.id
        ).exists()
        self.assertTrue(licence_exists)

    def assert_related_vehicle_user_is_deleted(self):
        vehicle_user_exists = VehicleUser.objects.filter(
            id=self.vehicle_user.id
        ).exists()
        self.assertFalse(vehicle_user_exists)

    def assert_unrelated_vehicle_user_still_exists(self):
        vehicle_user_exists = VehicleUser.objects.filter(
            id=self.unrelated_vehicle_user.id
        ).exists()
        self.assertTrue(vehicle_user_exists)

    def assert_anonymization_clears_permit_event_context(self):
        self.assertEqual(self.permit_event.context, {})

    def assert_anonymization_preserves_permit_statistical_data(
        self, *, permit, pre_anon_permit_data
    ):
        self.assertEqual(permit.parking_zone, pre_anon_permit_data["parking_zone"])
        self.assertEqual(
            permit.next_parking_zone, pre_anon_permit_data["next_parking_zone"]
        )
        self.assertEqual(permit.start_time, pre_anon_permit_data["start_time"])
        self.assertEqual(permit.end_time, pre_anon_permit_data["end_time"])
        self.assertEqual(permit.status, pre_anon_permit_data["status"])
        self.assertEqual(permit.type, pre_anon_permit_data["type"])
        self.assertEqual(permit.contract_type, pre_anon_permit_data["contract_type"])
        self.assertEqual(
            permit.primary_vehicle, pre_anon_permit_data["primary_vehicle"]
        )
        self.assertEqual(permit.month_count, pre_anon_permit_data["month_count"])

    def assert_anonymization_preserves_order_statistical_data(
        self, *, order, pre_anon_order_data
    ):
        self.assertEqual(order.status, pre_anon_order_data["status"])
        self.assertEqual(order.type, pre_anon_order_data["type"])
        self.assertEqual(order.payment_type, pre_anon_order_data["payment_type"])
        self.assertEqual(order.paid_time, pre_anon_order_data["paid_time"])
        self.assertEqual(
            order.parking_zone_name, pre_anon_order_data["parking_zone_name"]
        )
        self.assertEqual(order.created_at, pre_anon_order_data["created_at"])

    def assert_anonymization_preserves_order_item_statistical_data(
        self, *, pre_anon_order_item_data
    ):
        order_item = self.order_item
        self.assertEqual(order_item.unit_price, pre_anon_order_item_data["unit_price"])
        self.assertEqual(
            order_item.payment_unit_price,
            pre_anon_order_item_data["payment_unit_price"],
        )
        self.assertEqual(order_item.vat, pre_anon_order_item_data["vat"])
        self.assertEqual(order_item.quantity, pre_anon_order_item_data["quantity"])
        self.assertEqual(order_item.start_time, pre_anon_order_item_data["start_time"])
        self.assertEqual(order_item.end_time, pre_anon_order_item_data["end_time"])

    def assert_anonymization_preserves_subscription_statistical_data(
        self, *, pre_anon_subscription_data
    ):
        subscription = self.subscription
        self.assertEqual(subscription.status, pre_anon_subscription_data["status"])
        self.assertEqual(
            subscription.cancel_reason, pre_anon_subscription_data["cancel_reason"]
        )

    def assert_anonymization_preserves_vehicle_statistical_data(
        self, *, vehicle, pre_anon_vehicle_data
    ):
        self.assertEqual(vehicle.power_type, pre_anon_vehicle_data["power_type"])
        self.assertEqual(vehicle.vehicle_class, pre_anon_vehicle_data["vehicle_class"])
        self.assertEqual(vehicle.manufacturer, pre_anon_vehicle_data["manufacturer"])
        self.assertEqual(vehicle.model, pre_anon_vehicle_data["model"])
        self.assertEqual(
            vehicle.registration_number, pre_anon_vehicle_data["registration_number"]
        )
        self.assertEqual(vehicle.emission, pre_anon_vehicle_data["emission"])
        self.assertEqual(vehicle.emission_type, pre_anon_vehicle_data["emission_type"])
        self.assertEqual(vehicle.euro_class, pre_anon_vehicle_data["euro_class"])

    def assert_anonymization_preserves_address_statistical_data(
        self, *, address, pre_anon_address_data
    ):
        self.assertEqual(address.street_name, pre_anon_address_data["street_name"])
        self.assertEqual(address.street_number, pre_anon_address_data["street_number"])
        self.assertEqual(address.postal_code, pre_anon_address_data["postal_code"])
        self.assertEqual(address.city, pre_anon_address_data["city"])

    def assert_anonymization_preserves_refund_statistical_data(
        self, *, pre_anon_refund_data
    ):
        refund = self.refund
        self.assertEqual(
            refund.amount, pytest.approx(pre_anon_refund_data["amount"], Decimal(0.01))
        )
        self.assertEqual(refund.status, pre_anon_refund_data["status"])
        self.assertEqual(
            refund.vat, pytest.approx(pre_anon_refund_data["vat"], Decimal(0.01))
        )
        self.assertEqual(refund.accepted_at, pre_anon_refund_data["accepted_at"])


class TestCannotAnonymizeCustomerErrorTestCase(TestCase):
    def test_anonymizing_unanonymizable_customer_raises_exception(self):
        customer = CustomerFactory()
        # Should be unable to anonymize the customer at least due to
        # too new modified-timestamp.
        with self.assertRaises(CustomerCannotBeAnonymizedError):
            customer.anonymize_all_data()
