# Generated by Django 3.2.13 on 2022-11-07 06:31

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("parking_permits", "0018_announcement"),
    ]

    operations = [
        migrations.CreateModel(
            name="VehiclePowerType",
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
                    "name",
                    models.CharField(
                        blank=True, max_length=100, null=True, verbose_name="Name"
                    ),
                ),
                (
                    "identifier",
                    models.CharField(max_length=10, verbose_name="Identifier"),
                ),
            ],
            options={
                "verbose_name": "Vehicle power type",
                "verbose_name_plural": "Vehicle power types",
            },
        ),
        migrations.RemoveField(
            model_name="lowemissioncriteria",
            name="power_type",
        ),
        migrations.AlterField(
            model_name="vehicle",
            name="power_type",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="vehicles",
                to="parking_permits.vehiclepowertype",
                verbose_name="power_type",
            ),
        ),
    ]
