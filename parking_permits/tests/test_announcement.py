import importlib
from unittest.mock import MagicMock, patch

from django.core import mail
from django.test import TestCase

from parking_permits import admin_resolvers
from parking_permits.models import Announcement
from parking_permits.services.mail import send_announcement_emails
from parking_permits.tests.factories import ParkingZoneFactory
from parking_permits.tests.factories.announcement import AnnouncementFactory
from parking_permits.tests.factories.customer import CustomerFactory
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
        self.assertFalse(announcement_from_db.emails_handled)


class SendAnnouncementMailTest(TestCase):
    def setUp(self):
        self.announcement = AnnouncementFactory()

    def test_should_do_nothing_if_no_customers(self):
        send_announcement_emails([], self.announcement)
        self.assertEqual(len(mail.outbox), 0)

    def test_should_send_mail_for_a_single_customer(self):
        customer = CustomerFactory(email="foo@bar.test")
        send_announcement_emails([customer], self.announcement)
        self.assertEqual(len(mail.outbox), 1)

    def test_should_send_mail_for_multiple_customers(self):
        customers = [CustomerFactory(email=f"foo{i}@bar.test") for i in range(1, 11)]
        send_announcement_emails(customers, self.announcement)
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
        send_announcement_emails([CustomerFactory()], announcement)
        sent_email = mail.outbox[0]
        html_body, content_type = sent_email.alternatives[0]

        self.assertEqual(content_type, "text/html")
        self.assertEqual(sent_email.subject, "Subject FI | Subject SV | Subject EN")
        for value in contents_subjects.values():
            self.assertIn(value, sent_email.body)
            self.assertIn(value, html_body)
