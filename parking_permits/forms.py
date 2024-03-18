import functools
import operator

from django import forms
from django.contrib.postgres.forms import SimpleArrayField
from django.db import models
from django.db.models import OuterRef, Q, Subquery, Value
from django.db.models.functions import Concat
from django.utils import timezone

from parking_permits.models import (
    Address,
    Announcement,
    Customer,
    LowEmissionCriteria,
    Product,
    TemporaryVehicle,
)
from parking_permits.models.order import Order, OrderPaymentType
from parking_permits.models.parking_permit import (
    ContractType,
    ParkingPermit,
    ParkingPermitStatus,
)
from parking_permits.models.refund import Refund, RefundStatus
from parking_permits.paginator import QuerySetPaginator
from users.models import ParkingPermitGroups

EXPORT_DATA_TYPE_CHOICES = [
    ("permits", "Permits"),
    ("orders", "Orders"),
    ("refunds", "Refunds"),
    ("products", "Products"),
]

PDF_EXPORT_DATA_TYPE_CHOICES = [
    ("permit", "Permit"),
    ("order", "Order"),
    ("refund", "Refund"),
]


class PdfExportForm(forms.Form):
    data_type = forms.ChoiceField(choices=PDF_EXPORT_DATA_TYPE_CHOICES)
    object_id = forms.IntegerField()


class OrderDirection(models.TextChoices):
    DESC = "DESC"
    ASC = "ASC"


class SearchFormBase(forms.Form):
    page = forms.IntegerField(min_value=1, required=False)
    order_field = forms.CharField(required=False)
    order_direction = forms.ChoiceField(choices=OrderDirection.choices, required=False)

    def filter_queryset(self, qs):
        return qs

    def page_queryset(self, qs):
        paginator = QuerySetPaginator(qs, self.cleaned_data)
        return {
            "page_info": paginator.page_info,
            "objects": paginator.object_list,
        }

    def get_order_fields_mapping(self):
        return {}

    def get_model_class(self):
        raise NotImplementedError

    def order_queryset(self, qs):
        order_field = self.cleaned_data.get("order_field")
        order_fields_mapping = self.get_order_fields_mapping()
        model_fields = order_fields_mapping.get(order_field)
        if not model_fields:
            return qs.order_by("-id")
        order_direction = self.cleaned_data.get("order_direction")
        if order_direction and order_direction == OrderDirection.DESC:
            model_fields = [f"-{field}" for field in model_fields]
        return qs.order_by(*model_fields)

    def get_queryset(self):
        model_class = self.get_model_class()
        qs = self.filter_queryset(model_class.objects.all().distinct())
        return self.order_queryset(qs)

    def get_paged_queryset(self):
        return self.page_queryset(self.get_queryset())

    def get_empty_queryset(self):
        model_class = self.get_model_class()
        return model_class.objects.none()


class PermitSearchForm(SearchFormBase):
    # max number of individual terms in text search
    MAX_TEXT_SEARCH_TOKENS = 6

    q = forms.CharField(required=False)
    status = forms.ChoiceField(
        choices=ParkingPermitStatus.choices + [("ALL", "All")],
        required=False,
    )
    user_role = forms.ChoiceField(choices=ParkingPermitGroups.choices, required=False)

    def get_model_class(self):
        return ParkingPermit

    def get_order_fields_mapping(self):
        return {
            "name": ["customer__first_name", "customer__last_name"],
            "nationalIdNumber": ["customer__national_id_number"],
            "registrationNumber": [
                "vehicle__registration_number",
            ],
            "primaryAddress": [
                "customer__primary_address__street_name",
                "customer__primary_address__street_number",
            ],
            "otherAddress": [
                "customer__other_address__street_name",
                "customer__other_address__street_number",
            ],
            "parkingZone": ["parking_zone__name"],
            "startTime": ["start_time"],
            "endTime": ["end_time"],
            "status": ["status"],
        }

    def filter_queryset(self, qs):
        q = self.cleaned_data.get("q")

        if not q:
            return self.get_empty_queryset()

        now = timezone.now()

        fields = [
            "vehicle__registration_number",
            "temp_vehicles__vehicle__registration_number",
        ]

        if self.cleaned_data.get("user_role") != ParkingPermitGroups.INSPECTORS:
            fields += [
                "customer__first_name",
                "customer__last_name",
                "customer__national_id_number",
            ]

        query = functools.reduce(
            operator.and_,
            [
                functools.reduce(
                    operator.or_,
                    [Q(**{f"{field}__icontains": token}) for field in fields],
                )
                for token in q.split()[: self.MAX_TEXT_SEARCH_TOKENS]
            ],
        )

        if q.isdigit():
            query = query | Q(pk=q)

        qs = qs.annotate(
            active_temporary_vehicle_registration_number=Subquery(
                TemporaryVehicle.objects.filter(
                    parkingpermit__pk=OuterRef("pk"),
                    is_active=True,
                    start_time__lte=now,
                    end_time__gte=now,
                ).values("vehicle__registration_number")[:1]
            )
        ).filter(query)

        status = self.cleaned_data.get("status") or "ALL"

        if status != "ALL":
            qs = qs.filter(status=status)

        return qs.select_related("customer", "vehicle").distinct()


class RefundSearchForm(SearchFormBase):
    q = forms.CharField(required=False)
    status = forms.ChoiceField(
        choices=RefundStatus.choices + [("ALL", "All")], required=False
    )
    start_date = forms.DateField(required=False)
    end_date = forms.DateField(required=False)
    payment_types = SimpleArrayField(
        forms.ChoiceField(choices=OrderPaymentType.choices), required=False
    )

    def get_model_class(self):
        return Refund

    def get_order_fields_mapping(self):
        return {
            "id": ["id"],
            "name": ["name"],
            "orderId": ["order_id"],
            "registrationNumber": ["order__permits__vehicle__registration_number"],
            "accountNumber": ["iban"],
            "createdAt": ["created_at"],
            "acceptedAt": ["accepted_at"],
            "status": ["status"],
            "amount": ["amount"],
        }

    def filter_queryset(self, qs):
        has_filters = False
        q = self.cleaned_data.get("q")
        start_date = self.cleaned_data.get("start_date")
        end_date = self.cleaned_data.get("end_date")
        status = self.cleaned_data.get("status")
        payment_types = self.cleaned_data.get("payment_types")

        if q:
            text_filters = (
                Q(name__icontains=q)
                | Q(order__permits__vehicle__registration_number__icontains=q)
                | Q(iban__icontains=q)
            )
            qs = qs.filter(text_filters)
            has_filters = True
        if start_date:
            qs = qs.filter(created_at__gte=start_date)
            has_filters = True
        if end_date:
            qs = qs.filter(created_at__lte=end_date)
            has_filters = True
        if status and status != "ALL":
            qs = qs.filter(status=status)
            has_filters = True
        if payment_types:
            qs = qs.filter(order__payment_type__in=payment_types)
            has_filters = True

        return qs if has_filters else self.get_empty_queryset()


class OrderSearchForm(SearchFormBase):
    # max number of individual terms in text search
    MAX_TEXT_SEARCH_TOKENS = 6

    q = forms.CharField(required=False)
    start_date = forms.DateField(required=False)
    end_date = forms.DateField(required=False)
    parking_zone = forms.CharField(required=False)
    contract_types = SimpleArrayField(
        forms.ChoiceField(choices=ContractType.choices), required=False
    )
    payment_types = SimpleArrayField(
        forms.ChoiceField(choices=OrderPaymentType.choices), required=False
    )
    price_discounts = SimpleArrayField(
        forms.ChoiceField(
            choices=[
                ("LOW_EMISSION", "LOW_EMISSION"),
            ]
        ),
        required=False,
    )

    def get_model_class(self):
        return Order

    def get_order_fields_mapping(self):
        return {
            "name": ["customer__first_name", "customer__last_name"],
            "permits": ["_permit_id"],
            "parkingZone": ["_permit_parking_zone_name"],
            "address": [
                "_permit_address_street_name",
                "_permit_address_street_number",
            ],
            "permitType": ["_permit_type"],
            "id": ["id"],
            "paidTime": ["paid_time"],
        }

    def order_queryset(self, qs):
        permit = ParkingPermit.objects.filter(orders=OuterRef("pk"))
        return super(OrderSearchForm, self).order_queryset(
            qs.annotate(
                _permit_parking_zone_name=Subquery(
                    permit.values("parking_zone__name")[:1]
                ),
                _permit_address_street_name=Subquery(
                    permit.values("address__street_name")[:1]
                ),
                _permit_address_street_number=Subquery(
                    permit.values("address__street_number")[:1]
                ),
                _permit_type=Subquery(permit.values("type")[:1]),
                _permit_id=Subquery(permit.values("id")[:1]),
            )
        )

    def filter_queryset(self, qs):
        has_filters = False
        q = self.cleaned_data.get("q")
        contract_types = self.cleaned_data.get("contract_types")
        payment_types = self.cleaned_data.get("payment_types")
        parking_zone = self.cleaned_data.get("parking_zone")
        start_date = self.cleaned_data.get("start_date")
        end_date = self.cleaned_data.get("end_date")
        price_discounts = self.cleaned_data.get("price_discounts")

        if q:
            if q.isdigit():
                query = Q(id=int(q))
            else:
                query = functools.reduce(
                    operator.and_,
                    [
                        Q(customer__first_name__icontains=token)
                        | Q(customer__last_name__icontains=token)
                        | Q(customer__national_id_number=token)
                        | Q(vehicles__icontains=token)
                        for token in q.split()[: self.MAX_TEXT_SEARCH_TOKENS]
                    ],
                )
            qs = qs.filter(query)
            has_filters = True

        if start_date:
            # Find all orders with permits that are or will be valid after the given start date.
            qs = qs.filter(
                Q(permits__start_time__gte=start_date)
                | Q(permits__end_time__isnull=True)
                | Q(permits__end_time__gte=start_date)
            )
            has_filters = True

        if end_date:
            # Find all orders with permits that are or have been valid before the given end date.
            qs = qs.filter(permits__start_time__lte=end_date)
            has_filters = True

        if parking_zone:
            qs = qs.filter(parking_zone_name=parking_zone)
            has_filters = True

        if contract_types:
            qs = qs.filter(permits__contract_type__in=contract_types)
            has_filters = True

        if payment_types:
            qs = qs.filter(payment_type__in=payment_types)
            has_filters = True

        if "LOW_EMISSION" in price_discounts:
            qs = qs.filter(permits__vehicle___is_low_emission=True)
            has_filters = True

        if has_filters:
            model_class = self.get_model_class()
            return model_class.objects.filter(id__in=qs.distinct("id"))
        return self.get_empty_queryset()


class ProductSearchForm(SearchFormBase):
    def get_model_class(self):
        return Product

    def get_order_fields_mapping(self):
        return {
            "productType": ["type"],
            "zone": ["zone__name"],
            "price": ["unit_price"],
            "vat": ["vat"],
            "validPeriod": ["start_date"],
            "modifiedAt": ["modified_at"],
            "modifiedBy": ["modified_by"],
        }


class AddressSearchForm(SearchFormBase):
    street_name = forms.CharField(required=False)
    street_number = forms.CharField(required=False)
    postal_code = forms.CharField(required=False)
    parking_zone = forms.CharField(required=False)

    def get_model_class(self):
        return Address

    def get_order_fields_mapping(self):
        return {
            "streetName": ["street_name"],
            "streetNameSv": ["street_name_sv"],
            "streetNumber": ["street_number"],
            "postalCode": ["postal_code"],
            "city": ["city"],
            "citySv": ["city_sv"],
            "zone": ["_zone__name"],
        }

    def filter_queryset(self, qs):
        street_name = self.cleaned_data.get("street_name")
        street_number = self.cleaned_data.get("street_number")
        postal_code = self.cleaned_data.get("postal_code")
        parking_zone = self.cleaned_data.get("parking_zone")

        if street_name:
            qs = qs.filter(
                Q(street_name__icontains=street_name)
                | Q(street_name_sv__icontains=street_name)
            )

        if street_number:
            qs = qs.filter(street_number=street_number)

        if postal_code:
            qs = qs.filter(postal_code=postal_code)

        if parking_zone:
            qs = qs.filter(_zone__name=parking_zone)

        return qs


class LowEmissionCriteriaSearchForm(SearchFormBase):
    def get_model_class(self):
        return LowEmissionCriteria

    def get_order_fields_mapping(self):
        return {
            "powerType": ["power_type"],
            "euroMinClassLimit": ["euro_min_class_limit"],
            "nedcMaxEmissionLimit": ["nedc_max_emission_limit"],
            "wltpMaxEmissionLimit": ["wltp_max_emission_limit"],
            "validPeriod": ["start_date"],
        }


class AnnouncementSearchForm(SearchFormBase):
    def get_model_class(self):
        return Announcement

    def get_order_fields_mapping(self):
        return {
            "createdAt": ["created_at"],
            "createdBy": ["created_by"],
        }


class CustomerSearchForm(SearchFormBase):
    name = forms.CharField(required=False)
    national_id_number = forms.CharField(required=False)

    def get_model_class(self):
        return Customer

    def get_order_fields_mapping(self):
        return {
            "name": ["last_name", "first_name"],
            "email": ["email"],
            "phoneNumber": ["phone_number"],
            "nationalIdNumber": ["national_id_number"],
        }

    def filter_queryset(self, qs):
        has_filters = False
        name = self.cleaned_data.get("name")
        national_id_number = self.cleaned_data.get("national_id_number")

        if name:
            qs = qs.annotate(full_name=Concat("first_name", Value(" "), "last_name"))
            qs = qs.annotate(
                full_name_reverse=Concat("last_name", Value(" "), "first_name")
            )
            qs = qs.filter(
                Q(first_name__icontains=name)
                | Q(last_name__icontains=name)
                | Q(full_name__icontains=name)
                | Q(full_name_reverse__icontains=name)
            )
            has_filters = True
        if national_id_number:
            qs = qs.filter(national_id_number=national_id_number)
            has_filters = True

        return qs if has_filters else self.get_empty_queryset()
