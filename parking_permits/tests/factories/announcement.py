import factory

from parking_permits.models import Announcement


class AnnouncementFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Announcement
