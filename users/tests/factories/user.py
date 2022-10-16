import factory
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from helusers.models import ADGroup


class GroupFactory(factory.django.DjangoModelFactory):
    name = factory.Sequence(lambda n: f"ad-group-{n}")

    class Meta:
        model = Group


class ADGroupFactory(factory.django.DjangoModelFactory):
    name = factory.Sequence(lambda n: f"ad-group-{n}")
    display_name = factory.Faker("name")

    class Meta:
        model = ADGroup


class UserFactory(factory.django.DjangoModelFactory):
    username = factory.Sequence(lambda n: f"username-{n}")
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    email = factory.Faker("email")
    uuid = factory.Faker("uuid4")

    class Meta:
        model = get_user_model()


class ADAdminFactory(UserFactory):
    @factory.post_generation
    def groups(self, create, extracted, **kwargs):
        group_name = settings.ALLOWED_ADMIN_AD_GROUPS[0]
        group = ADGroupFactory(name=group_name)
        self.ad_groups.add(group)
