# Generated by Django 3.2.13 on 2022-08-04 18:02

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("parking_permits", "0011_encrypted_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="TemporaryVehicle",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="Time created"
                    ),
                ),
                (
                    "modified_at",
                    models.DateTimeField(auto_now=True, verbose_name="Time modified"),
                ),
                (
                    "start_time",
                    models.DateTimeField(
                        default=django.utils.timezone.now, verbose_name="Start time"
                    ),
                ),
                ("end_time", models.DateTimeField(verbose_name="End time")),
                ("is_active", models.BooleanField(default=True)),
                (
                    "vehicle",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        to="parking_permits.vehicle",
                        verbose_name="Vehicle",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.AddField(
            model_name="parkingpermit",
            name="temp_vehicles",
            field=models.ManyToManyField(
                blank=True, to="parking_permits.TemporaryVehicle"
            ),
        ),
    ]
