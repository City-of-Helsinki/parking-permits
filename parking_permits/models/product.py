import json
import logging
from decimal import Decimal
from urllib.parse import urljoin

import requests
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from parking_permits.exceptions import CreateTalpaProductError, ProductCatalogError
from parking_permits.talpa.pricing import Pricing

from ..utils import diff_months_ceil, find_next_date, format_local_time
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


class Accounting(TimestampedModelMixin, UserStampedModelMixin):
    active_from = models.DateTimeField(_("Active from"), null=True, blank=True)
    company_code = models.CharField(
        _("Company code"), max_length=64, null=True, blank=True
    )
    vat_code = models.CharField(_("VAT code"), max_length=64, null=True, blank=True)
    internal_order = models.CharField(
        _("Internal order"), max_length=64, null=True, blank=True
    )
    profit_center = models.CharField(
        _("Profit center"), max_length=64, null=True, blank=True
    )
    balance_profit_center = models.CharField(
        _("Balance profit center"), max_length=64, null=True, blank=True
    )
    project = models.CharField(_("Project"), max_length=64, null=True, blank=True)
    operation_area = models.CharField(
        _("Operation area"), max_length=64, null=True, blank=True
    )
    main_ledger_account = models.CharField(
        _("Main ledger account"), max_length=64, null=True, blank=True
    )

    class Meta:
        verbose_name = _("Accounting")
        verbose_name_plural = _("Accountings")

    def __str__(self):
        return (
            f"{self.pk} "
            f"({self.company_code} - {self.main_ledger_account}"
            f" - {self.vat_code})"
        )


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
        choices=ProductType,
        default=ProductType.RESIDENT,
    )
    start_date = models.DateField(_("Start date"))
    end_date = models.DateField(_("End date"))
    unit_price = models.DecimalField(_("Unit price"), max_digits=6, decimal_places=2)
    unit = models.CharField(
        _("Unit"), max_length=50, choices=Unit, default=Unit.MONTHLY
    )
    vat = models.DecimalField(_("VAT"), max_digits=6, decimal_places=4)
    low_emission_discount = models.DecimalField(
        _("Low emission discount"), max_digits=12, decimal_places=10
    )
    accounting = models.ForeignKey(
        Accounting,
        verbose_name=_("Accounting"),
        related_name="products",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    next_accounting = models.ForeignKey(
        Accounting,
        verbose_name=_("Next accounting"),
        related_name="next_products",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
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
    def low_emission_discount_percentage(self):
        return self.low_emission_discount * 100

    @low_emission_discount_percentage.setter
    def low_emission_discount_percentage(self, value):
        self.low_emission_discount = value / 100

    @property
    def name(self):
        return f"{_('Parking zone')} {self.zone.name}"

    @property
    def description(self):
        return (
            f"{_('Parking zone')} {self.zone.name}, {self.start_date} - {self.end_date}"
        )

    def get_modified_unit_price(self, is_low_emission, is_secondary):
        price = self.unit_price
        if is_low_emission:
            price -= price * self.low_emission_discount
        if is_secondary:
            price += price * self.secondary_vehicle_increase_rate
        return price

    def get_talpa_pricing(self, is_low_emission, is_secondary):
        """Returns dict of the following price values for Talpa processing e.g.:
        {
            "price_gross": "20.00",
            "price_net": "16.13",
            "price_vat": "3.87",
            "vat_percentage": "25.50",
        }
        """
        price_gross = self.get_modified_unit_price(is_low_emission, is_secondary)
        pricing = Pricing.calculate(price_gross, self.vat)

        return {
            "price_gross": pricing.format_gross(),
            "price_net": pricing.format_net(),
            "price_vat": pricing.format_vat(),
            "vat_percentage": f"{self.vat_percentage:.2f}",
        }

    def get_merchant_id(self):
        headers = {
            "api-key": settings.TALPA_API_KEY,
            "Content-Type": "application/json",
        }
        response = requests.get(
            urljoin(
                settings.TALPA_MERCHANT_EXPERIENCE_API,
                f"list/merchants/{settings.NAMESPACE}/",
            ),
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
            "merchantId": self.get_merchant_id(),
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

    def create_talpa_accounting(self):
        if not self.talpa_product_id:
            logger.error("Talpa product does not exist")
            return

        self.accounting = Accounting.objects.create(
            company_code=settings.TALPA_DEFAULT_ACCOUNTING_COMPANY_CODE,
            vat_code=settings.TALPA_DEFAULT_ACCOUNTING_VAT_CODE,
            internal_order=settings.TALPA_DEFAULT_ACCOUNTING_INTERNAL_ORDER,
            profit_center=settings.TALPA_DEFAULT_ACCOUNTING_PROFIT_CENTER,
            balance_profit_center=settings.TALPA_DEFAULT_ACCOUNTING_BALANCE_PROFIT_CENTER,
            project=settings.TALPA_DEFAULT_ACCOUNTING_PROJECT,
            operation_area=settings.TALPA_DEFAULT_ACCOUNTING_OPERATION_AREA,
            main_ledger_account=settings.TALPA_DEFAULT_ACCOUNTING_MAIN_LEDGER_ACCOUNT,
        )
        self.save()

        data = {
            "vatCode": self.accounting.vat_code,
            "internalOrder": self.accounting.internal_order,
            "profitCenter": self.accounting.profit_center,
            "balanceProfitCenter": self.accounting.balance_profit_center,
            "project": self.accounting.project,
            "operationArea": self.accounting.operation_area,
            "companyCode": self.accounting.company_code,
            "mainLedgerAccount": self.accounting.main_ledger_account,
        }

        headers = {
            "api-key": settings.TALPA_API_KEY,
            "namespace": settings.NAMESPACE,
            "Content-Type": "application/json",
        }
        response = requests.post(
            urljoin(
                settings.TALPA_PRODUCT_EXPERIENCE_API,
                f"{self.talpa_product_id}/accounting/",
            ),
            data=json.dumps(data, default=str),
            headers=headers,
        )
        if response.status_code == 201:
            logger.info(f"Talpa product {self.talpa_product_id} accounting created")
        else:
            logger.error(
                f"Failed to create Talpa product {self.talpa_product_id} accounting. "
                f"Error: {response.status_code} {response.reason}. "
                f"Detail: {response.text}"
            )
            raise CreateTalpaProductError(
                f"Cannot create Talpa product {self.talpa_product_id} accounting. "
                f"Error: {response.status_code} {response.reason}."
            )

    def update_talpa_accounting(self):
        if not self.talpa_product_id:
            logger.error("Talpa product does not exist")
            return

        accounting = self.accounting
        if not accounting:
            logger.error("Product accounting is missing")
            return

        data = {
            "vatCode": accounting.vat_code,
            "internalOrder": accounting.internal_order,
            "profitCenter": accounting.profit_center,
            "balanceProfitCenter": accounting.balance_profit_center,
            "project": accounting.project,
            "operationArea": accounting.operation_area,
            "companyCode": accounting.company_code,
            "mainLedgerAccount": accounting.main_ledger_account,
        }

        next_accounting = self.next_accounting
        if next_accounting:
            active_from = (
                format_local_time(next_accounting.active_from)
                if next_accounting.active_from
                else ""
            )
            data.update(
                {
                    "nextEntity": {
                        "companyCode": next_accounting.company_code,
                        "mainLedgerAccount": next_accounting.main_ledger_account,
                        "vatCode": next_accounting.vat_code,
                        "internalOrder": next_accounting.internal_order,
                        "profitCenter": next_accounting.profit_center,
                        "balanceProfitCenter": next_accounting.balance_profit_center,
                        "project": next_accounting.project,
                        "operationArea": next_accounting.operation_area,
                    },
                    "activeFrom": active_from,
                }
            )

        headers = {
            "api-key": settings.TALPA_API_KEY,
            "namespace": settings.NAMESPACE,
            "Content-Type": "application/json",
        }
        response = requests.post(
            urljoin(
                settings.TALPA_PRODUCT_EXPERIENCE_API,
                f"{self.talpa_product_id}/accounting/",
            ),
            data=json.dumps(data, default=str),
            headers=headers,
        )
        if response.status_code == 201:
            logger.info(f"Talpa product {self.talpa_product_id} accounting updated")
        else:
            logger.error(
                f"Failed to update Talpa product {self.talpa_product_id} accounting. "
                f"Error: {response.status_code} {response.reason}. "
                f"Detail: {response.text}"
            )
            raise CreateTalpaProductError(
                f"Cannot update Talpa product {self.talpa_product_id} accounting. "
                f"Error: {response.status_code} {response.reason}."
            )
