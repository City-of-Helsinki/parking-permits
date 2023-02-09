# Generated by Django 3.2.13 on 2022-09-22 07:15s
from django.utils import timezone as tz
from django.db import migrations, models


def initialize_is_low_emission_on_existing_vehicles(apps, schema_editor):
    # Get the historical models.
    Vehicle = apps.get_model("parking_permits", "Vehicle")
    LowEmissionCriteria = apps.get_model("parking_permits", "LowEmissionCriteria")

    # Copy-pasted historical function for determining whether a vehicle is low emission or not.
    # Enums replaced with their actual values (at the time).
    def is_low_emission_vehicle(power_type, euro_class, emission_type, emission):
        if power_type == "ELECTRIC":
            return True
        try:
            now = tz.now()
            le_criteria = LowEmissionCriteria.objects.get(
                power_type=power_type,
                start_date__lte=now,
                end_date__gte=now,
            )
        except LowEmissionCriteria.DoesNotExist:
            return False

        if (
            not euro_class
            or emission is None
            or euro_class < le_criteria.euro_min_class_limit
        ):
            return False

        if emission_type == "NEDC":
            return emission <= le_criteria.nedc_max_emission_limit

        if emission_type == "WLTP":
            return emission <= le_criteria.wltp_max_emission_limit

        return False

    # Initialize the vehicles' _is_low_emission field.
    for obj in Vehicle.objects.all():
        obj._is_low_emission = is_low_emission_vehicle(
            obj.power_type,
            obj.euro_class,
            obj.emission_type,
            obj.emission,
        )
        obj.save(update_fields=["_is_low_emission"])


class Migration(migrations.Migration):
    dependencies = [
        ("parking_permits", "0014_add_search_field_for_customer_national_id_number"),
    ]

    operations = [
        migrations.AddField(
            model_name="vehicle",
            name="_is_low_emission",
            field=models.BooleanField(default=False, editable=False),
        ),
        migrations.RunPython(
            initialize_is_low_emission_on_existing_vehicles,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
