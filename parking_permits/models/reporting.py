import datetime

from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from parking_permits.models.parking_permit import (
    ContractType,
    ParkingPermit,
    ParkingPermitStatus,
)


class PermitCountSnapshot(models.Model):
    """Represents a daily snapshot of the counts of valid parking
    permits on the given date grouped by relevant dimensions."""

    permit_count = models.IntegerField(_("Permit count"))

    date = models.DateField(_("Date"))

    parking_zone_name = models.CharField(_("Parking zone name"), max_length=128)
    parking_zone_description = models.TextField(_("Parking zone description"))
    parking_zone_description_sv = models.TextField(_("Parking zone description sv"))

    low_emission = models.BooleanField(_("Low-emission"))

    primary_vehicle = models.BooleanField(_("Primary vehicle"))

    contract_type = models.CharField(
        _("Contract type"),
        max_length=16,
        choices=ContractType.choices,
    )

    class Meta:
        verbose_name = _("Permit count snapshot")
        verbose_name_plural = _("Permit count snapshots")
        constraints = [
            models.UniqueConstraint(
                fields=(
                    "date",
                    "parking_zone_name",
                    "parking_zone_description",
                    "parking_zone_description_sv",
                    "low_emission",
                    "primary_vehicle",
                    "contract_type",
                ),
                name="unique_daily_snapshot",
            )
        ]

    @staticmethod
    def get_counts_for_permit_ids(
        *, permit_ids, low_emission: bool, date: datetime.date
    ):
        grouping_fields = (
            "parking_zone__name",
            "parking_zone__description",
            "parking_zone__description_sv",
            "primary_vehicle",
            "contract_type",
        )

        permit_count_data = (
            ParkingPermit.objects.filter(id__in=permit_ids)
            .select_related("parking_zone")
            # IMPORTANT:
            # - values() is used to group the data by the relevant
            # fields
            # - values() _MUST_ be called before annotating the permit
            # count into the queryset as otherwise were just annotating
            # a count of 1 into all the entries without doing any
            # proper grouping.
            # - We're always running this logic for a given emission
            # type and date, these are annotated in.
            .values(*grouping_fields)
            .annotate(
                permit_count=models.Count("id"),
                low_emission=models.Value(low_emission),
                date=models.Value(date),
            )
        )

        return permit_count_data

    @staticmethod
    def build_daily_snapshot():
        now = timezone.now()
        now_date = now.date()

        # Get permits that are going to contribute to the
        # daily snapshot
        valid_permits = ParkingPermit.objects.filter(
            status=ParkingPermitStatus.VALID,
            start_time__lte=now,
            end_time__gte=now,
        ).select_related("vehicle__power_type")

        # Split the permits into lists of permit ids by their
        # low-emission-status, this allows us to calculate the grouped
        # counts on the database-level.
        valid_low_emission_permit_ids = []
        valid_high_emission_permit_ids = []
        for permit in valid_permits:
            if permit.vehicle.is_low_emission:
                valid_low_emission_permit_ids.append(permit.id)
            else:
                valid_high_emission_permit_ids.append(permit.id)

        low_emission_permit_counts = PermitCountSnapshot.get_counts_for_permit_ids(
            permit_ids=valid_low_emission_permit_ids,
            low_emission=True,
            date=now_date,
        )

        high_emission_permit_counts = PermitCountSnapshot.get_counts_for_permit_ids(
            permit_ids=valid_high_emission_permit_ids,
            low_emission=False,
            date=now_date,
        )

        permit_counts = list(low_emission_permit_counts) + list(
            high_emission_permit_counts
        )

        permit_counts_to_create = []
        permit_counts_to_update = []

        for count_entry in permit_counts:
            filter_dict = {
                "date": count_entry["date"],
                "parking_zone_name": count_entry["parking_zone__name"],
                "parking_zone_description": count_entry["parking_zone__description"],
                "parking_zone_description_sv": count_entry[
                    "parking_zone__description_sv"
                ],
                "low_emission": count_entry["low_emission"],
                "primary_vehicle": count_entry["primary_vehicle"],
                "contract_type": count_entry["contract_type"],
            }

            permit_count_snapshot = PermitCountSnapshot(
                **filter_dict,
                permit_count=count_entry["permit_count"],
            )

            if pre_existing_snapshot := PermitCountSnapshot.objects.filter(
                **filter_dict
            ).first():
                permit_count_snapshot.id = pre_existing_snapshot.id
                permit_counts_to_update.append(permit_count_snapshot)
            else:
                permit_counts_to_create.append(permit_count_snapshot)

        with transaction.atomic():
            fields_to_update = ("permit_count",)
            PermitCountSnapshot.objects.bulk_update(
                permit_counts_to_update,
                fields=fields_to_update,
                batch_size=5000,
            )

            PermitCountSnapshot.objects.bulk_create(
                permit_counts_to_create,
                batch_size=5000,
            )
