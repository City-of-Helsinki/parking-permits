import abc
from datetime import date

from django.conf import settings
from django.utils import timezone as tz
from django.utils.translation import gettext_lazy as _
from fpdf import FPDF

from parking_permits.models import Order, ParkingPermit, Product, Refund
from parking_permits.models.order import OrderPaymentType

DATETIME_FORMAT = "%-d.%-m.%Y, %H:%M"
DATE_FORMAT = "%-d.%-m.%Y"
CURRENT_YEAR = date.today().year

MODEL_MAPPING = {
    "permits": ParkingPermit,
    "orders": Order,
    "refunds": Refund,
    "products": Product,
}


def _get_permit_end_time(permit):
    if permit.is_open_ended:
        return permit.current_period_end_time
    return permit.end_time


def _format_datetime(dt, default=""):
    return tz.localtime(dt).strftime(DATETIME_FORMAT) if dt else default


def _format_percentage(value, default=""):
    return "%.2f" % value if value else default


def _format_price(value):
    return "%.2f" % value


def _get_permit_row(permit):
    customer = permit.customer
    vehicle = permit.vehicle
    name = f"{customer.last_name}, {customer.first_name}"
    end_time = _get_permit_end_time(permit)
    return [
        name,
        customer.national_id_number,
        vehicle.registration_number,
        getattr(permit, "active_temporary_vehicle_registration_number", None) or "-",
        (
            str(permit.full_address)
            if permit.address and permit.address == customer.primary_address
            else "-"
        ),
        (
            str(permit.full_address)
            if permit.address and permit.address == customer.other_address
            else "-"
        ),
        permit.parking_zone.name,
        _format_datetime(permit.start_time, "-"),
        _format_datetime(end_time, "-"),
        _("Primary permit") if permit.primary_vehicle else _("Secondary permit"),
        permit.get_status_display(),
    ]


def _get_order_row(order):
    customer = order.customer
    permits = order.permits.all()
    try:
        permit_type = permits[0].get_type_display()
        permit_ids = ", ".join([str(permit.pk) for permit in permits])
    except IndexError:
        permit_type = permit_ids = "-"

    reg_numbers = ", ".join(order.vehicles) if order.vehicles else "-"
    name = f"{customer.last_name}, {customer.first_name}"

    return [
        permit_ids,
        reg_numbers,
        name,
        order.parking_zone_name or "-",
        order.address_text or "-",
        permit_type,
        order.id,
        (
            _("Online payment")
            if order.payment_type == OrderPaymentType.ONLINE_PAYMENT
            else _("Cashier payment")
        ),
        _format_datetime(order.paid_time, "-"),
        _format_price(order.total_payment_price),
    ]


def _get_refund_row(refund):
    return [
        refund.name,
        refund.amount,
        refund.iban,
        refund.get_status_display(),
        _format_datetime(refund.created_at),
    ]


def _get_product_row(product):
    start_date = product.start_date.strftime(DATE_FORMAT)
    end_date = product.end_date.strftime(DATE_FORMAT)
    valid_period = f"{start_date} - {end_date}"
    return [
        product.get_type_display(),
        product.zone.name,
        product.unit_price,
        _format_percentage(product.low_emission_discount_percentage, "-"),
        _format_percentage(product.vat_percentage, "-"),
        valid_period,
        _format_datetime(product.modified_at),
        product.modified_by,
    ]


ROW_GETTER_MAPPING = {
    "permits": _get_permit_row,
    "orders": _get_order_row,
    "refunds": _get_refund_row,
    "products": _get_product_row,
}

PERMIT_HEADERS = [
    _("Name"),
    _("National identification number"),
    _("Registration number"),
    _("Temporary registration number"),
    _("Primary address"),
    _("Other address"),
    _("Area"),
    _("Start time"),
    _("End time"),
    _("Permit order"),
    _("Status"),
]


LIMITED_PERMIT_HEADERS = [
    _("Registration number"),
    _("Area"),
    _("Start time"),
    _("End time"),
    _("Status"),
]

ORDER_HEADERS = [
    _("Parking permits"),
    _("Registration numbers"),
    _("Customer"),
    _("Area"),
    _("Address"),
    _("Permit type"),
    _("Order number"),
    _("Order payment type"),
    _("Paid time"),
    _("Amount"),
]

REFUND_HEADERS = [
    _("Name"),
    _("Amount"),
    _("IBAN"),
    _("Status"),
    _("Created at"),
]

PRODUCT_HEADERS = [
    _("Product type"),
    _("Parking zone"),
    _("Price") + " (€)",
    _("Low emission discount") + " (%)",
    _("VAT") + " (%)",
    _("Validity period"),
    _("Modified at"),
    _("Modified by"),
]

HEADERS_MAPPING = {
    "permits": PERMIT_HEADERS,
    "limited_permits": LIMITED_PERMIT_HEADERS,
    "orders": ORDER_HEADERS,
    "refunds": REFUND_HEADERS,
    "products": PRODUCT_HEADERS,
}


class DataExporter:
    def __init__(self, data_type, queryset):
        self.data_type = data_type
        self.queryset = queryset

    def get_metadata(self):
        return {
            "metadata": {
                "copyright": {
                    "© " + _("City of Helsinki"),
                    _("Personal data - Digital and population data services agency"),
                }
            }
        }

    def get_headers(self):
        headers = HEADERS_MAPPING[self.data_type]
        headers.append(self.get_metadata())
        return headers

    def get_rows(self):
        row_getter = ROW_GETTER_MAPPING[self.data_type]
        return [row_getter(item) for item in self.queryset]


class BasePDF(FPDF, metaclass=abc.ABCMeta):
    def header(self):
        self.image(
            str(settings.STATIC_ROOT) + "/parking_permits/img/helsinki.png", 10, 8, 33
        )
        self.set_font("Arial", "B", 15)
        self.cell(55)
        self.cell(20, 10, self.get_title(), 0, 0, "C")
        self.ln(20)

    def footer(self):
        self.set_y(-25)
        self.set_font("Arial", "", 10)
        self.cell(0, 5, "© " + _("City of Helsinki"), 0, 1)
        self.cell(
            0, 5, _("Personal data - Digital and population data services agency"), 0, 1
        )

    @abc.abstractmethod
    def get_title(self):
        pass

    @abc.abstractmethod
    def get_source_object(self, object_id):
        pass

    @abc.abstractmethod
    def set_content(self, obj):
        pass


class ParkingPermitPDF(BasePDF):
    def get_title(self):
        return _("Parking permits")

    def get_source_object(self, object_id):
        permit_qs = ParkingPermit.objects.filter(pk=object_id)
        if not permit_qs.exists():
            return None
        return permit_qs.first()

    def get_permit_content(self, permit):
        customer_name = (
            f"{permit.customer.first_name} {permit.customer.last_name}"
            if permit.customer.first_name
            else "-"
        )
        address = str(permit.full_address) if permit.full_address else "-"
        permit_end_time = _get_permit_end_time(permit)

        return [
            _("Permit ID") + ": " + f"{permit.id}",
            _("Customer") + ": " + customer_name,
            _("Address") + ": " + address,
            _("Area") + ": " + str(permit.parking_zone.name),
            _("Vehicle")
            + ": "
            + f"{permit.vehicle.registration_number} ({permit.vehicle.manufacturer} {permit.vehicle.model})",
            _("Type") + ": " + permit.get_contract_type_display(),
            _("Validity period")
            + ": "
            + f"{_format_datetime(permit.start_time)} - {_format_datetime(permit_end_time)}",
        ]

    def set_content(self, obj):
        self.set_font("Arial", "B", 16)
        self.cell(0, 14, _("Resident permit"), 0, 1)
        self.set_draw_color(0, 0, 139)
        self.set_line_width(0.5)
        self.line(11, 45, 200, 45)
        self.ln(10)
        self.set_font("Arial", "", 12)
        content = self.get_permit_content(obj)
        for line in content:
            self.cell(0, 7, line, 0, 1)


class RefundPDF(ParkingPermitPDF):
    def get_title(self):
        return _("Refunds")

    def get_source_object(self, object_id):
        refund_qs = Refund.objects.filter(pk=object_id)
        if not refund_qs.exists():
            return None
        return refund_qs.first()

    @staticmethod
    def get_refund_content(refund):
        return [
            _("Refund ID") + ": " + f"{refund.id}",
            _("Customer")
            + ": "
            + f"{refund.order.customer.first_name} {refund.order.customer.last_name}",
            _("Amount") + ": " + f"{refund.amount} e (" + _("incl. VAT") + " 24%)",
            _("IBAN") + ": " + f"{refund.iban}",
            _("Status") + ": " + f"{refund.get_status_display()}",
            _("Extra info") + ": " + f"{refund.description}",
        ]

    @staticmethod
    def get_order_content(order):
        return [
            _("Order ID") + ": " + f"{order.id}",
            _("Order payment type") + ": " + f"{order.get_payment_type_display()}",
            _("Order payment time") + ": " + f"{_format_datetime(order.paid_time)}",
        ]

    def set_content(self, obj):
        self.set_font("Arial", "B", 16)
        self.cell(0, 14, _("Refund"), 0, 1)
        self.set_draw_color(0, 0, 139)
        self.set_line_width(0.5)
        self.line(11, 45, 200, 45)
        self.ln(5)
        self.set_font("Arial", "", 12)

        content = self.get_refund_content(obj)
        for line in content:
            self.cell(0, 7, line, 0, 1)

        self.ln(5)
        self.set_font("Arial", "B", 12)
        self.cell(0, 7, _("Order info"), 0, 1)
        self.set_font("Arial", "", 12)
        order_content = self.get_order_content(obj.order)
        for line in order_content:
            self.cell(0, 7, line, 0, 1)

        permits = obj.order.permits.order_by("-primary_vehicle")
        for permit in permits:
            self.ln(5)
            self.set_font("Arial", "B", 12)
            permit_header = (
                _("Primary permit") if permit.primary_vehicle else _("Secondary permit")
            )
            self.cell(0, 7, permit_header, 0, 1)
            self.set_font("Arial", "", 12)
            permit_content = self.get_permit_content(permit)
            for line in permit_content:
                self.cell(0, 7, line, 0, 1)


PDF_MODEL_MAPPING = {
    "permit": ParkingPermitPDF,
    "refund": RefundPDF,
}


class PdfExporter:
    def __init__(self, data_type, object_id):
        self.data_type = data_type
        self.object_id = object_id

    def get_pdf(self):
        pdf = PDF_MODEL_MAPPING[self.data_type]()
        obj = pdf.get_source_object(self.object_id)
        if not obj:
            return None
        pdf.add_page()
        pdf.set_content(obj)
        return pdf
