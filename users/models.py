from django.conf import settings
from django.contrib.gis.db import models
from django.db import transaction
from helusers.models import AbstractUser, ADGroupMapping


class ParkingPermitGroups(models.TextChoices):
    SUPER_ADMIN = "super_admin"
    SANCTIONS_AND_REFUNDS = "sanctions_and_refunds"
    SANCTIONS = "sanctions"
    CUSTOMER_SERVICE = "customer_service"
    PREPARATORS = "preparators"
    INSPECTORS = "inspectors"


class User(AbstractUser):
    @transaction.atomic
    def sync_groups_from_ad(self):
        if not settings.LOCAL_ADMIN_ROLES_ENABLED:
            return super().sync_groups_from_ad()

        type(self).objects.select_for_update().get(pk=self.pk)
        mappings = ADGroupMapping.objects.exclude(
            group__name__in=ParkingPermitGroups.values
        )
        old_groups = set(
            self.groups.filter(pk__in=mappings.values("group_id")).values_list(
                "pk", flat=True
            )
        )
        new_groups = set(
            mappings.filter(ad_group__in=self.ad_groups.all()).values_list(
                "group_id", flat=True
            )
        )
        self.groups.remove(*(old_groups - new_groups))
        self.groups.add(*(new_groups - old_groups))

    @property
    def is_super_admin(self):
        return self.groups.filter(name=ParkingPermitGroups.SUPER_ADMIN).exists()

    @property
    def is_sanctions_and_refunds(self):
        return (
            self.groups.filter(name=ParkingPermitGroups.SANCTIONS_AND_REFUNDS).exists()
            or self.is_super_admin
        )

    @property
    def is_sanctions(self):
        return (
            self.groups.filter(name=ParkingPermitGroups.SANCTIONS).exists()
            or self.is_sanctions_and_refunds
            or self.is_super_admin
        )

    @property
    def is_customer_service(self):
        return (
            self.groups.filter(name=ParkingPermitGroups.CUSTOMER_SERVICE).exists()
            or self.is_sanctions
            or self.is_sanctions_and_refunds
            or self.is_super_admin
        )

    @property
    def is_preparators(self):
        return (
            self.groups.filter(name=ParkingPermitGroups.PREPARATORS).exists()
            or self.is_customer_service
            or self.is_sanctions
            or self.is_sanctions_and_refunds
            or self.is_super_admin
        )

    @property
    def is_inspectors(self):
        return (
            self.groups.filter(name=ParkingPermitGroups.INSPECTORS).exists()
            or self.is_preparators
            or self.is_customer_service
            or self.is_sanctions
            or self.is_sanctions_and_refunds
            or self.is_super_admin
        )
