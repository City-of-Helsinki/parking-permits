# Generated by Django 3.2.13 on 2022-09-26 06:16

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("parking_permits", "0015_vehicle__is_low_emission"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="customer",
            name="old_national_id_number",
        ),
    ]
