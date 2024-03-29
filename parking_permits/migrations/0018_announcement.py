# Generated by Django 3.2.13 on 2022-10-18 14:26

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("parking_permits", "0017_alter_temporaryvehicle_options"),
    ]

    operations = [
        migrations.CreateModel(
            name="Announcement",
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
                    "subject_en",
                    models.CharField(max_length=255, verbose_name="Subject (EN)"),
                ),
                ("content_en", models.TextField(verbose_name="Content (EN)")),
                (
                    "subject_fi",
                    models.CharField(max_length=255, verbose_name="Subject (FI)"),
                ),
                ("content_fi", models.TextField(verbose_name="Content (FI)")),
                (
                    "subject_sv",
                    models.CharField(max_length=255, verbose_name="Subject (SV)"),
                ),
                ("content_sv", models.TextField(verbose_name="Content (SV)")),
                (
                    "_parking_zones",
                    models.ManyToManyField(
                        related_name="announcements", to="parking_permits.ParkingZone"
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Created by",
                    ),
                ),
                (
                    "modified_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Modified by",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
    ]
