# Generated by Django 3.2.13 on 2022-11-20 06:03

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("parking_permits", "0019_vehicle_power_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="type",
            field=models.CharField(
                choices=[
                    ("CREATED", "Created"),
                    ("VEHICLE_CHANGED", "Vehicle changed"),
                    ("ADDRESS_CHANGED", "Address changed"),
                ],
                default="CREATED",
                max_length=50,
                verbose_name="Order type",
            ),
        ),
        migrations.AddField(
            model_name="parkingpermit",
            name="next_address",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="next_permits",
                to="parking_permits.address",
                verbose_name="Next address",
            ),
        ),
        migrations.AddField(
            model_name="parkingpermit",
            name="next_parking_zone",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="next_permits",
                to="parking_permits.parkingzone",
                verbose_name="Next parking zone",
            ),
        ),
        migrations.AddField(
            model_name="parkingpermit",
            name="next_vehicle",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="next_permits",
                to="parking_permits.vehicle",
                verbose_name="Next vehicle",
            ),
        ),
        migrations.AlterField(
            model_name="parkingpermit",
            name="parking_zone",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="permits",
                to="parking_permits.parkingzone",
                verbose_name="Parking zone",
            ),
        ),
        migrations.AlterField(
            model_name="parkingpermit",
            name="vehicle",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="permits",
                to="parking_permits.vehicle",
                verbose_name="Vehicle",
            ),
        ),
    ]
