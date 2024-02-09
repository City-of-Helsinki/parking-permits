import importlib
from unittest.mock import MagicMock, patch

from django.core import mail
from django.test import TestCase

from parking_permits import admin_resolvers
from parking_permits.models import Announcement
from parking_permits.models.parking_permit import ParkingPermitStatus
from parking_permits.services.mail import send_announcement_email
from parking_permits.tests.factories import ParkingZoneFactory
from parking_permits.tests.factories.announcement import AnnouncementFactory
from parking_permits.tests.factories.customer import CustomerFactory
from parking_permits.tests.factories.parking_permit import ParkingPermitFactory
from users.tests.factories.user import UserFactory


@patch("parking_permits.admin_resolvers.post_create_announcement")
class CreateAnnouncementResolverTest(TestCase):
    def setUp(self):
        # Patch the authentication decorators and reload the module, so we can
        # directly test the resolver without authentication shenanigans.
        def kill_patches():
            patch.stopall()
            importlib.reload(admin_resolvers)

        self.addCleanup(kill_patches)

        patch("parking_permits.decorators.is_authenticated", lambda x: x).start()
        patch("parking_permits.decorators.is_super_admin", lambda x: x).start()
        importlib.reload(admin_resolvers)

        # Mock the info object passed for the resolver.
        user = UserFactory()
        request = MagicMock(user=user)
        self.info = MagicMock(context={"request": request})

        self.announcement = dict(
            content_fi="Content FI",
            content_en="Content EN",
            content_sv="Content SV",
            subject_en="Subject EN",
            subject_fi="Subject FI",
            subject_sv="Subject SV",
            parking_zones=[],
        )

    def test_happy_day_scenario(self, mock_post_create_announcement):
        message = admin_resolvers.resolve_create_announcement(
            None, self.info, self.announcement
        )

        self.assertDictEqual(message, {"success": True})
        mock_post_create_announcement.assert_called_once()
        self.assertEqual(len(Announcement.objects.all()), 1)

    def test_should_set_correct_parking_zones(self, mock_post_create_announcement):
        zone_a = ParkingZoneFactory(name="A")
        zone_b = ParkingZoneFactory(name="B")
        ParkingZoneFactory(name="C")

        self.announcement["parking_zones"] = ["A", "B", "some utter nonsense"]

        admin_resolvers.resolve_create_announcement(None, self.info, self.announcement)

        self.assertEqual(len(Announcement.objects.all()), 1)

        announcement_from_db = Announcement.objects.first()
        announcement_zones = announcement_from_db.parking_zones.order_by("name")

        self.assertEqual(len(announcement_zones), 2)
        self.assertEqual(announcement_zones[0], zone_a)
        self.assertEqual(announcement_zones[1], zone_b)


@patch("parking_permits.admin_resolvers.send_announcement_email")
class PostCreateAnnouncementTest(TestCase):
    def setUp(self):
        self.announcement = AnnouncementFactory()

    def test_should_have_no_customers_for_an_empty_parking_zone(
        self, mock_send_announcement_email: MagicMock
    ):
        empty_zone = ParkingZoneFactory(name="Empty")
        self.announcement._parking_zones.set([empty_zone])
        admin_resolvers.post_create_announcement(self.announcement)

        mock_send_announcement_email.assert_called_once()
        customers_arg = mock_send_announcement_email.call_args.args[0]
        self.assertEqual(len(customers_arg), 0)

    def test_should_get_correct_customers_from_single_parking_zone(
        self, mock_send_announcement_email: MagicMock
    ):
        # Create zones A and B; A will be the target for our announcement.
        zone_a = ParkingZoneFactory(name="A")
        zone_b = ParkingZoneFactory(name="B")

        # Create customers for the zones.
        zone_a_customer = CustomerFactory(zone=zone_a)
        CustomerFactory(zone=zone_b)

        ParkingPermitFactory(
            customer=zone_a_customer,
            parking_zone=zone_a,
            status=ParkingPermitStatus.VALID,
        )

        # Set the announcement for zone A.
        self.announcement._parking_zones.set([zone_a])

        admin_resolvers.post_create_announcement(self.announcement)

        # Should have only one customer (from zone A).
        mock_send_announcement_email.assert_called_once()
        customers_arg = mock_send_announcement_email.call_args.args[0]
        self.assertEqual(len(customers_arg), 1)
        filtered_customer = customers_arg.first()
        self.assertEqual(filtered_customer, zone_a_customer)

    def test_should_get_correct_customers_from_multiple_parking_zones(
        self, mock_send_announcement_email: MagicMock
    ):
        # Create zones A, B and C; A and B will be the targets for our announcement.
        zone_a = ParkingZoneFactory(name="A")
        zone_b = ParkingZoneFactory(name="B")
        zone_c = ParkingZoneFactory(name="C")

        # Create customers for the zones.
        zone_a_customer = CustomerFactory(zone=zone_a)
        zone_b_customer = CustomerFactory(zone=zone_b)
        CustomerFactory(zone=zone_c)
        expected_customers = [zone_a_customer, zone_b_customer]

        ParkingPermitFactory(
            customer=zone_a_customer,
            parking_zone=zone_a,
            status=ParkingPermitStatus.VALID,
        )
        ParkingPermitFactory(
            customer=zone_b_customer,
            parking_zone=zone_b,
            status=ParkingPermitStatus.VALID,
        )

        # Set the announcement for zone A & B.
        self.announcement._parking_zones.set([zone_a, zone_b])
        admin_resolvers.post_create_announcement(self.announcement)

        # Should have two customers (from zone A & B).
        mock_send_announcement_email.assert_called_once()
        customers_arg = mock_send_announcement_email.call_args.args[0]
        self.assertEqual(len(customers_arg), 2)
        for idx, customer in enumerate(customers_arg.order_by("zone__name")):
            self.assertEqual(customer, expected_customers[idx])

    def test_should_get_correct_customers_only_with_valid_status(
        self, mock_send_announcement_email: MagicMock
    ):
        # Create zones A, B and C.
        zone_a = ParkingZoneFactory(name="A")
        zone_b = ParkingZoneFactory(name="B")
        zone_c = ParkingZoneFactory(name="C")

        # Create customers for the zones.
        zone_a_customer = CustomerFactory(zone=zone_a)
        zone_b_customer = CustomerFactory(zone=zone_b)
        zone_c_customer = CustomerFactory(zone=zone_c)
        expected_customers = [zone_a_customer, zone_b_customer]

        # Create permits for the zones, but only A and B will be valid.
        ParkingPermitFactory(
            customer=zone_a_customer,
            parking_zone=zone_a,
            status=ParkingPermitStatus.VALID,
        )
        ParkingPermitFactory(
            customer=zone_b_customer,
            parking_zone=zone_b,
            status=ParkingPermitStatus.VALID,
        )
        ParkingPermitFactory(
            customer=zone_c_customer,
            parking_zone=zone_c,
            status=ParkingPermitStatus.DRAFT,
        )

        # Set the announcement for zone A, B & C.
        self.announcement._parking_zones.set([zone_a, zone_b, zone_c])
        admin_resolvers.post_create_announcement(self.announcement)

        # Should have two customers (from zone A & B).
        mock_send_announcement_email.assert_called_once()
        customers_arg = mock_send_announcement_email.call_args.args[0]
        self.assertEqual(len(customers_arg), 2)
        for idx, customer in enumerate(customers_arg.order_by("zone__name")):
            self.assertEqual(customer, expected_customers[idx])


class SendAnnouncementMailTest(TestCase):
    def setUp(self):
        self.announcement = AnnouncementFactory()

    def test_should_do_nothing_if_no_customers(self):
        send_announcement_email([], self.announcement)
        self.assertEqual(len(mail.outbox), 0)

    def test_should_send_mail_for_a_single_customer(self):
        customer = CustomerFactory(email="foo@bar.test")
        send_announcement_email([customer], self.announcement)
        self.assertEqual(len(mail.outbox), 1)

    def test_should_send_mail_for_multiple_customers(self):
        customers = [CustomerFactory(email=f"foo{i}@bar.test") for i in range(1, 11)]
        send_announcement_email(customers, self.announcement)
        self.assertEqual(len(mail.outbox), 10)

    def test_mail_should_contain_all_translations(self):
        contents_subjects = dict(
            content_fi="Content FI",
            content_en="Content EN",
            content_sv="Content SV",
            subject_en="Subject EN",
            subject_fi="Subject FI",
            subject_sv="Subject SV",
        )
        announcement = AnnouncementFactory(
            content_fi="Content FI",
            content_en="Content EN",
            content_sv="Content SV",
            subject_en="Subject EN",
            subject_fi="Subject FI",
            subject_sv="Subject SV",
        )
        send_announcement_email([CustomerFactory()], announcement)
        sent_email = mail.outbox[0]
        html_body, content_type = sent_email.alternatives[0]

        self.assertEqual(content_type, "text/html")
        self.assertEqual(sent_email.subject, "Subject FI | Subject SV | Subject EN")
        for value in contents_subjects.values():
            self.assertIn(value, sent_email.body)
            self.assertIn(value, html_body)
