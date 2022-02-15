from django.contrib.gis import admin
from django.utils.translation import ugettext_lazy as _

from parking_permits.models import (
    Address,
    Company,
    Customer,
    DrivingClass,
    DrivingLicence,
    LowEmissionCriteria,
    Order,
    OrderItem,
    ParkingPermit,
    ParkingZone,
    Price,
    Product,
    Refund,
    Vehicle,
)


@admin.register(Address)
class AddressAdmin(admin.OSMGeoAdmin):
    search_fields = ("street_name", "street_name_sv", "city", "city_sv")
    list_display = (
        "id",
        "street_name",
        "street_name_sv",
        "street_number",
        "postal_code",
        "city",
        "city_sv",
    )


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    search_fields = ("name", "business_id")
    list_display = ("id", "name", "business_id", "address", "company_owner")
    list_select_related = ("address", "company_owner")


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    search_fields = ("first_name", "last_name")
    list_display = ("__str__", "national_id_number", "email")

    def has_add_permission(self, request):
        return False


@admin.register(DrivingClass)
class DrivingClassAdmin(admin.ModelAdmin):
    list_display = ("class_name", "identifier")


@admin.register(DrivingLicence)
class DrivingLicenceAdmin(admin.ModelAdmin):
    search_fields = ("customer__first_name", "customer__last_name")
    list_display = ("id", "customer", "valid_start", "valid_end", "active")
    list_select_related = ("customer",)


@admin.register(LowEmissionCriteria)
class LowEmissionCriteriaAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "power_type",
        "nedc_max_emission_limit",
        "wltp_max_emission_limit",
        "euro_min_class_limit",
        "start_date",
        "end_date",
    )


@admin.register(ParkingPermit)
class ParkingPermitAdmin(admin.ModelAdmin):
    search_fields = ("customer__first_name", "customer__last_name")
    list_display = (
        "identifier",
        "customer",
        "vehicle",
        "parking_zone",
        "status",
        "start_time",
        "end_time",
        "contract_type",
    )
    list_select_related = ("customer", "vehicle", "parking_zone")


@admin.register(ParkingZone)
class ParkingZoneAdmin(admin.OSMGeoAdmin):
    list_display = ("id", "name", "description", "description_sv")
    ordering = ("name",)


@admin.register(Price)
class PriceAdmin(admin.ModelAdmin):
    list_display = ("id", "zone", "price", "year", "type")
    list_select_related = ("zone",)


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    search_fields = ("registration_number", "manufacturer", "model")
    list_display = (
        "id",
        "registration_number",
        "manufacturer",
        "model",
        "owner",
        "holder",
    )
    list_select_related = ("owner", "holder")


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "iban",
        "order",
        "amount",
    )


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "zone",
        "type",
        "start_date",
        "end_date",
        "unit_price",
        "vat_percentage",
    )
    list_select_related = ("zone",)
    readonly_fields = ("talpa_product_id",)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_filter = ("order_type", "status")
    list_display = (
        "order_number",
        "customer",
        "order_type",
        "status",
    )
    list_select_related = ("customer",)
    readonly_fields = ("order_number", "talpa_order_id", "talpa_subscription_id")

    def order_number(self, obj):
        return obj.order_number

    order_number.admin_order_field = "order_number"
    order_number.short_description = _("Order number")


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = (
        "order",
        "product",
        "permit",
        "unit_price",
        "vat_percentage",
        "quantity",
    )
    list_select_related = ("order", "product", "permit")
    readonly_fields = ("talpa_order_item_id",)
