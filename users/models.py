from django.contrib.gis.db import models
from helusers.models import AbstractUser


class ParkingPermitGroups(models.TextChoices):
    SUPER_ADMIN = "super_admin"
    SANCTIONS_AND_REFUNDS = "sanctions_and_refunds"
    SANCTIONS = "sanctions"
    CUSTOMER_SERVICE = "customer_service"
    PREPARATORS = "preparators"
    INSPECTORS = "inspectors"


class User(AbstractUser):
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
