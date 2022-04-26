from django.test import TestCase

from parking_permits.exporters import (
    ORDER_HEADERS,
    PERMIT_HEADERS,
    PRODUCT_HEADERS,
    REFUND_HEADERS,
    DataExporter,
)
from parking_permits.tests.factories import ParkingZoneFactory
from parking_permits.tests.factories.customer import CustomerFactory
from parking_permits.tests.factories.order import OrderFactory, OrderItemFactory
from parking_permits.tests.factories.parking_permit import ParkingPermitFactory
from parking_permits.tests.factories.product import ProductFactory
from parking_permits.tests.factories.refund import RefundFactory


class DataExporterTestCase(TestCase):
    def setUp(self):
        self.customer_a = CustomerFactory(national_id_number="20000101-ABC")
        self.customer_b = CustomerFactory(national_id_number="20000102-EFG")
        self.zone_a = ParkingZoneFactory(name="A")
        self.zone_b = ParkingZoneFactory(name="B")

    def test_export_permits(self):
        ParkingPermitFactory(customer=self.customer_a, parking_zone=self.zone_a)
        ParkingPermitFactory(customer=self.customer_a, parking_zone=self.zone_b)
        ParkingPermitFactory(customer=self.customer_b, parking_zone=self.zone_b)
        order_by = {
            "order_fields": ["customer__national_id_number"],
            "order_direction": "DESC",
        }
        search_items = [
            {"match_type": "exact", "fields": ["parking_zone__name"], "value": "B"}
        ]
        exporter = DataExporter("permits", order_by, search_items)
        self.assertEqual(exporter.get_headers(), PERMIT_HEADERS)
        rows = exporter.get_rows()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][1], "20000102-EFG")
        self.assertEqual(rows[1][1], "20000101-ABC")

    def test_export_orders(self):
        order_1 = OrderFactory(customer=self.customer_a)
        OrderItemFactory(order=order_1)
        order_2 = OrderFactory(customer=self.customer_a)
        OrderItemFactory(order=order_2)
        order_3 = OrderFactory(customer=self.customer_b)
        OrderItemFactory(order=order_3)
        exporter = DataExporter("orders")
        self.assertEqual(exporter.get_headers(), ORDER_HEADERS)
        rows = exporter.get_rows()
        self.assertEqual(len(rows), 3)

    def test_export_refunds(self):
        RefundFactory()
        RefundFactory()
        RefundFactory()
        exporter = DataExporter("refunds")
        self.assertEqual(exporter.get_headers(), REFUND_HEADERS)
        rows = exporter.get_rows()
        self.assertEqual(len(rows), 3)

    def test_export_products(self):
        ProductFactory()
        ProductFactory()
        ProductFactory()
        exporter = DataExporter("products")
        self.assertEqual(exporter.get_headers(), PRODUCT_HEADERS)
        rows = exporter.get_rows()
        self.assertEqual(len(rows), 3)
