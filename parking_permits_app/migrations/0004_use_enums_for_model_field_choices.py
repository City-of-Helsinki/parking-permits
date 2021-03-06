# Generated by Django 3.2 on 2021-06-22 16:46

from django.db import migrations, models

import parking_permits_app.constants


class Migration(migrations.Migration):

    dependencies = [
        ("parking_permits_app", "0003_add_price_model"),
    ]

    operations = [
        migrations.AlterField(
            model_name="contracttype",
            name="contract_type",
            field=models.CharField(
                choices=[
                    (
                        parking_permits_app.constants.ContractType["FIXED_PERIOD"],
                        "Fixed period",
                    ),
                    (
                        parking_permits_app.constants.ContractType["OPEN_ENDED"],
                        "Open ended",
                    ),
                ],
                max_length=16,
                verbose_name="Contract type",
            ),
        ),
        migrations.AlterField(
            model_name="vehicle",
            name="category",
            field=models.CharField(
                choices=[
                    (parking_permits_app.constants.VehicleCategory["M1"], "M1"),
                    (parking_permits_app.constants.VehicleCategory["M2"], "M2"),
                    (parking_permits_app.constants.VehicleCategory["N1"], "N1"),
                    (parking_permits_app.constants.VehicleCategory["N2"], "N2"),
                    (parking_permits_app.constants.VehicleCategory["L3e"], "L3e"),
                    (parking_permits_app.constants.VehicleCategory["L4e"], "L4e"),
                    (parking_permits_app.constants.VehicleCategory["L5e"], "L5e"),
                    (parking_permits_app.constants.VehicleCategory["L6e"], "L6e"),
                ],
                max_length=16,
                verbose_name="Vehicle category",
            ),
        ),
        migrations.AlterField(
            model_name="vehicletype",
            name="type",
            field=models.CharField(
                choices=[
                    (parking_permits_app.constants.VehicleType["BENSIN"], "Bensin"),
                    (parking_permits_app.constants.VehicleType["DIESEL"], "Diesel"),
                    (parking_permits_app.constants.VehicleType["BIFUEL"], "Bifuel"),
                ],
                max_length=32,
                verbose_name="Type",
            ),
        ),
    ]
