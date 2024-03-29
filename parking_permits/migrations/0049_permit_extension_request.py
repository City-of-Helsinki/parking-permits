# Generated by Django 4.2.1 on 2024-02-02 13:44

import django.core.validators
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("parking_permits", "0048_merge_20240202_0838"),
    ]

    operations = [
        migrations.CreateModel(
            name="ParkingPermitExtensionRequest",
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
                    "month_count",
                    models.PositiveIntegerField(
                        validators=[django.core.validators.MaxValueValidator(12)]
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending"),
                            ("APPROVED", "Approved"),
                            ("CANCELLED", "Cancelled"),
                        ],
                        default="Pending",
                        max_length=12,
                    ),
                ),
                ("status_changed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "order",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="permit_extension_requests",
                        to="parking_permits.order",
                    ),
                ),
                (
                    "permit",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="permit_extension_requests",
                        to="parking_permits.parkingpermit",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
    ]
