from django.db import migrations

POWER_TYPE_FALLBACK_NAME = "Other"


def set_fallback_name(apps, schema_editor):
    model_class = apps.get_model("parking_permits", "VehiclePowerType")
    model_class.objects.filter(name__isnull=True).update(name=POWER_TYPE_FALLBACK_NAME)


def unset_fallback_name(apps, schema_editor):
    model_class = apps.get_model("parking_permits", "VehiclePowerType")
    model_class.objects.filter(name=POWER_TYPE_FALLBACK_NAME).update(name=None)


class Migration(migrations.Migration):
    dependencies = [
        ("parking_permits", "0076_alter_vehicle_updated_from_traficom_on"),
    ]

    operations = [
        migrations.RunPython(set_fallback_name, unset_fallback_name),
    ]
