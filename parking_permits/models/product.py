import json
import logging
from decimal import Decimal

import requests
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from parking_permits.exceptions import CreateTalpaProductError, ProductCatalogError

from ..utils import diff_months_ceil, find_next_date
from .mixins import TimestampedModelMixin, UserStampedModelMixin
from .parking_zone import ParkingZone

logger = logging.getLogger("db")


SECONDARY_VEHICLE_INCREASE_RATE = Decimal(0.5)


class ProductType(models.TextChoices):
    COMPANY = "COMPANY", _("Company")
    RESIDENT = "RESIDENT", _("Resident")


class Unit(models.TextChoices):
    MONTHLY = "MONTHLY", _("Monthly")
    PIECES = "PIECES", _("Pieces")


class ProductQuerySet(models.QuerySet):
    def for_resident(self):
        return self.filter(type=ProductType.RESIDENT)

    def for_company(self):
        return self.filter(type=ProductType.COMPANY)

    def get_for_date(self, dt):
        try:
            return self.get(start_date__lte=dt, end_date__gte=dt)
        except Product.DoesNotExist:
            logger.error(f"Product does not exist for date {dt}")
            raise ProductCatalogError(
                _("Product catalog error, please report to admin")
            )
        except Product.MultipleObjectsReturned:
            logger.error(f"Products date range overlapping for date {dt}")
            raise ProductCatalogError(
                _("Product catalog error, please report to admin")
            )

    def for_date_range(self, start_date, end_date):
        return self.filter(
            start_date__lte=end_date,
            end_date__gte=start_date,
        ).order_by("start_date")

    def get_products_with_quantities(self, start_date, end_date):
        # convert to list to enable minus indexing
        products = list(self.for_date_range(start_date, end_date))

        # check that there is no gap and overlapping between product date ranges
        for current_product, next_product in zip(products, products[1:]):
            if (
                current_product.end_date + relativedelta(days=1)
                != next_product.start_date
            ):
                logger.error("There are gaps or overlaps in product date ranges")
                raise ProductCatalogError(
                    _("Product catalog error, please report to admin")
                )

        # check product date range covers the whole duration of the permit
        if start_date < products[0].start_date or end_date > products[-1].end_date:
            logger.error("Products does not cover permit duration")
            raise ProductCatalogError(
                _("Product catalog error, please report to admin")
            )

        products_with_quantities = []
        for index, product in enumerate(products):
            if index == 0:
                period_start_date = start_date
            else:
                period_start_date = find_next_date(product.start_date, start_date.day)

            if index == len(products) - 1:
                period_end_date = end_date
            else:
                period_end_date = find_next_date(product.end_date, end_date.day)

            quantity = diff_months_ceil(period_start_date, period_end_date)
            products_with_quantities.append(
                [product, quantity, (period_start_date, period_end_date)]
            )

        return products_with_quantities


class Product(TimestampedModelMixin, UserStampedModelMixin):
    talpa_product_id = models.UUIDField(
        _("Talpa product id"),
        unique=True,
        editable=False,
        blank=True,
        null=True,
    )
    zone = models.ForeignKey(
        ParkingZone,
        verbose_name=_("zone"),
        related_name="products",
        on_delete=models.PROTECT,
    )
    type = models.CharField(
        _("Type"),
        max_length=20,
        choices=ProductType.choices,
        default=ProductType.RESIDENT,
    )
    start_date = models.DateField(_("Start date"))
    end_date = models.DateField(_("End date"))
    unit_price = models.DecimalField(_("Unit price"), max_digits=6, decimal_places=2)
    unit = models.CharField(
        _("Unit"), max_length=50, choices=Unit.choices, default=Unit.MONTHLY
    )
    vat = models.DecimalField(_("VAT"), max_digits=6, decimal_places=4)
    low_emission_discount = models.DecimalField(
        _("Low emission discount"), max_digits=4, decimal_places=2
    )
    objects = ProductQuerySet.as_manager()

    class Meta:
        verbose_name = _("Product")
        verbose_name_plural = _("Products")

    def __str__(self):
        return self.name

    @property
    def secondary_vehicle_increase_rate(self):
        return SECONDARY_VEHICLE_INCREASE_RATE

    @property
    def vat_percentage(self):
        return self.vat * 100

    @vat_percentage.setter
    def vat_percentage(self, value):
        self.vat = value / 100

    @property
    def name(self):
        return f"{self.get_type_display()}pysäköintialue {self.zone.name}"

    @property
    def description(self):
        return f"{self.get_type_display()}pysäköintialue {self.zone.name}, {self.start_date} - {self.end_date}"

    def get_modified_unit_price(self, is_low_emission, is_secondary):
        price = self.unit_price
        if is_low_emission:
            price -= price * self.low_emission_discount
        if is_secondary:
            price += price * self.secondary_vehicle_increase_rate
        return price

    def get_merchant_id(self):
        headers = {
            "api-key": settings.TALPA_API_KEY,
            "Content-Type": "application/json",
        }
        response = requests.get(
            f"{settings.TALPA_MERCHANT_EXPERIENCE_API}/list/merchants/{settings.NAMESPACE}/",
            headers=headers,
        )
        if response.status_code == 200:
            logger.info("Talpa merchant id found")
            data = response.json()
            if len(data):
                # we always assume only one merchant to exist here
                return data["0"]["merchantId"]
        else:
            logger.error(
                "Failed to get Talpa merchant id. "
                f"Error: {response.status_code} {response.reason}. "
                f"Detail: {response.text}"
            )
            raise CreateTalpaProductError(
                "Cannot retrieve Talpa merchant id. "
                f"Error: {response.status_code} {response.reason}."
            )

    def create_talpa_product(self):
        if self.talpa_product_id:
            logger.warning("Talpa product has been created already")
            return

        data = {
            "namespace": settings.NAMESPACE,
            "namespaceEntityId": str(self.id),
            "name": self.name,
            "merchantId": self.get_merchant_id()
        }
        headers = {
            "api-key": settings.TALPA_API_KEY,
            "Content-Type": "application/json",
        }
        response = requests.post(
            settings.TALPA_PRODUCT_EXPERIENCE_API,
            data=json.dumps(data, default=str),
            headers=headers,
        )
        if response.status_code == 201:
            logger.info("Talpa product created")
            data = response.json()
            self.talpa_product_id = data["productId"]
            self.save()
        else:
            logger.error(
                "Failed to create Talpa product. "
                f"Error: {response.status_code} {response.reason}. "
                f"Detail: {response.text}"
            )
            raise CreateTalpaProductError(
                "Cannot create Talpa Product. "
                f"Error: {response.status_code} {response.reason}."
            )
