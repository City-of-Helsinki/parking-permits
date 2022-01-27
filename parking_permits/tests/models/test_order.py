from datetime import date, datetime
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from freezegun import freeze_time

from parking_permits.exceptions import OrderCreationFailed
from parking_permits.models import Order
from parking_permits.models.order import OrderStatus
from parking_permits.models.parking_permit import ContractType, ParkingPermitStatus
from parking_permits.models.product import ProductType
from parking_permits.tests.factories.customer import CustomerFactory
from parking_permits.tests.factories.order import OrderFactory, OrderItemFactory
from parking_permits.tests.factories.parking_permit import ParkingPermitFactory
from parking_permits.tests.factories.product import ProductFactory
from parking_permits.tests.factories.vehicle import VehicleFactory
from parking_permits.tests.factories.zone import ParkingZoneFactory
from parking_permits.utils import get_end_time


class TestOrderManager(TestCase):
    def setUp(self):
        self.zone = ParkingZoneFactory()
        ProductFactory(
            zone=self.zone,
            type=ProductType.RESIDENT,
            start_date=date(2021, 1, 1),
            end_date=date(2021, 6, 30),
            unit_price=Decimal(30),
        )
        ProductFactory(
            zone=self.zone,
            type=ProductType.RESIDENT,
            start_date=date(2021, 7, 1),
            end_date=date(2021, 12, 31),
            unit_price=Decimal(50),
        )
        self.customer = CustomerFactory(zone=self.zone)

    def test_create_for_customer_should_create_order_with_items(self):
        start_time = timezone.make_aware(datetime(2021, 3, 15))
        end_time = get_end_time(start_time, 6)  # end at 2021-09-14 23:59
        ParkingPermitFactory(
            parking_zone=self.zone,
            customer=self.customer,
            contract_type=ContractType.FIXED_PERIOD,
            status=ParkingPermitStatus.DRAFT,
            start_time=start_time,
            end_time=end_time,
            month_count=6,
        )
        order = Order.objects.create_for_customer(self.customer)
        order_items = order.order_items.all().order_by("-quantity")
        self.assertEqual(order_items.count(), 2)
        self.assertEqual(order_items[0].unit_price, Decimal(30))
        self.assertEqual(order_items[0].quantity, 4)
        self.assertEqual(order_items[1].unit_price, Decimal(50))
        self.assertEqual(order_items[1].quantity, 2)

    def test_test_create_renewable_order_should_create_renewal_order(self):
        high_emission_vehicle = VehicleFactory(low_emission_vehicle=False)
        low_emission_vehicle = VehicleFactory(low_emission_vehicle=True)
        start_time = timezone.make_aware(datetime(2021, 3, 15))
        end_time = get_end_time(start_time, 6)  # end at 2021-09-14 23:59
        permit = ParkingPermitFactory(
            parking_zone=self.zone,
            vehicle=high_emission_vehicle,
            customer=self.customer,
            contract_type=ContractType.FIXED_PERIOD,
            status=ParkingPermitStatus.DRAFT,
            start_time=start_time,
            end_time=end_time,
            month_count=6,
        )
        order = Order.objects.create_for_customer(self.customer)
        order.status = OrderStatus.CONFIRMED
        order.save()
        permit.refresh_from_db()
        permit.status = ParkingPermitStatus.VALID
        permit.vehicle = low_emission_vehicle
        permit.save()

        with freeze_time(timezone.make_aware(datetime(2021, 5, 5))):
            new_order = Order.objects.create_renewal_order(order)
            order_items = new_order.order_items.all().order_by("start_date")
            self.assertEqual(order_items.count(), 2)
            self.assertEqual(order_items[0].unit_price, Decimal(15))
            self.assertEqual(order_items[0].payment_unit_price, Decimal(-15))
            self.assertEqual(order_items[0].quantity, 2)
            self.assertEqual(order_items[1].unit_price, Decimal(25))
            self.assertEqual(order_items[1].payment_unit_price, Decimal(-25))
            self.assertEqual(order_items[1].quantity, 2)

    def test_create_renewable_order_should_raise_error_for_draft_permits(self):
        start_time = timezone.make_aware(datetime(2021, 3, 15))
        end_time = get_end_time(start_time, 6)  # end at 2021-09-14 23:59
        ParkingPermitFactory(
            parking_zone=self.zone,
            customer=self.customer,
            contract_type=ContractType.FIXED_PERIOD,
            status=ParkingPermitStatus.DRAFT,
            start_time=start_time,
            end_time=end_time,
            month_count=6,
        )
        order = Order.objects.create_for_customer(self.customer)
        with freeze_time(timezone.make_aware(datetime(2021, 5, 5))):
            with self.assertRaises(OrderCreationFailed):
                Order.objects.create_renewal_order(order)

    def test_create_renewable_order_should_raise_error_for_open_ended_permits(self):
        start_time = timezone.make_aware(datetime(2021, 3, 15))
        end_time = get_end_time(start_time, 6)  # end at 2021-09-14 23:59
        permit = ParkingPermitFactory(
            parking_zone=self.zone,
            customer=self.customer,
            contract_type=ContractType.OPEN_ENDED,
            status=ParkingPermitStatus.DRAFT,
            start_time=start_time,
            end_time=end_time,
            month_count=6,
        )
        order = Order.objects.create_for_customer(self.customer)
        permit.status = ParkingPermitStatus.VALID
        permit.save()
        with freeze_time(timezone.make_aware(datetime(2021, 5, 5))):
            with self.assertRaises(OrderCreationFailed):
                Order.objects.create_renewal_order(order)


class TestOrder(TestCase):
    def setUp(self):
        self.order = OrderFactory()
        OrderItemFactory(
            order=self.order,
            unit_price=Decimal(30),
            payment_unit_price=Decimal(30),
            quantity=2,
            vat=Decimal(0.2),
        )
        OrderItemFactory(
            order=self.order,
            unit_price=Decimal(20),
            payment_unit_price=Decimal(30),
            quantity=5,
            vat=Decimal(0.5),
        )

    def test_should_return_correct_total_price(self):
        self.assertAlmostEqual(self.order.total_price, Decimal(160))

    def test_should_return_correct_total_price_net(self):
        self.assertAlmostEqual(self.order.total_price_net, Decimal(98))

    def test_should_return_correct_total_price_vat(self):
        self.assertAlmostEqual(self.order.total_price_vat, Decimal(62))


class TestOrderItem(TestCase):
    def setUp(self):
        self.order_item = OrderItemFactory(
            unit_price=Decimal(30),
            payment_unit_price=Decimal(30),
            quantity=2,
            vat=Decimal(0.2),
        )

    def test_should_return_correct_unit_price_net(self):
        self.assertAlmostEqual(self.order_item.unit_price_net, Decimal(24))

    def test_should_return_correct_unit_price_vat(self):
        self.assertAlmostEqual(self.order_item.unit_price_vat, Decimal(6))

    def test_should_return_correct_total_price(self):
        self.assertAlmostEqual(self.order_item.total_price, Decimal(60))

    def test_should_return_correct_total_price_net(self):
        self.assertAlmostEqual(self.order_item.total_price_net, Decimal(48))

    def test_should_return_correct_total_price_vat(self):
        self.assertAlmostEqual(self.order_item.total_price_vat, Decimal(12))
