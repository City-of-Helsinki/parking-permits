from django.contrib.gis.db import models
from django.utils.translation import gettext_lazy as _

from .address import Address
from .customer import Customer
from .mixins import TimestampedModelMixin


class Company(TimestampedModelMixin):
    name = models.CharField(_("Company name"), max_length=128)
    business_id = models.CharField(_("Business Id"), max_length=32)
    address = models.ForeignKey(
        Address, verbose_name=_("Address"), on_delete=models.PROTECT
    )
    company_owner = models.ForeignKey(
        Customer, verbose_name=_("Company owner"), on_delete=models.PROTECT
    )

    class Meta:
        verbose_name = _("Company")
        verbose_name_plural = _("Companies")

    def __str__(self):
        return "%s" % self.name
