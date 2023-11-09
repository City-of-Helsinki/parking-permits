from django.test import TestCase

from parking_permits.models.customer import generate_ssn
from parking_permits.tests.factories.customer import CustomerFactory


class CustomerTestCase(TestCase):
    def test_ssn_creation_with_empty_db(self):
        ssn = generate_ssn()
        self.assertEqual(ssn, "XX-000001")

    def test_ssn_creation(self):
        CustomerFactory(national_id_number="XX-000001")
        CustomerFactory(national_id_number="XX-000002")
        CustomerFactory(national_id_number="XX-000003")
        CustomerFactory(national_id_number="XX-000004")
        CustomerFactory(national_id_number="XX-000005")
        CustomerFactory(national_id_number="XX-ABCDEF")
        CustomerFactory(national_id_number="YY-000001")
        CustomerFactory(national_id_number="ZZ-000002")
        CustomerFactory(national_id_number="XX-000104")
        CustomerFactory(national_id_number="XX-105")
        CustomerFactory(national_id_number="270602-123X")
        ssn = generate_ssn()
        self.assertEqual(ssn, "XX-000105")
