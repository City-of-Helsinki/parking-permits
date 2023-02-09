from django.conf import settings
from django.contrib.gis.db import models
from django.utils.translation import gettext_lazy as _


class TimestampedModelMixin(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Time created"))
    modified_at = models.DateTimeField(auto_now=True, verbose_name=_("Time modified"))

    class Meta:
        abstract = True


class UserStampedModelMixin(models.Model):
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("Created by"),
        related_name="+",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    modified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("Modified by"),
        related_name="+",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )

    class Meta:
        abstract = True
