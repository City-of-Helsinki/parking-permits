# Generated by Django 3.2.13 on 2022-10-12 11:56

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("parking_permits", "0016_remove_old_national_id_number_alter_is_low_emission"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="temporaryvehicle",
            options={
                "verbose_name": "Temporary vehicle",
                "verbose_name_plural": "Temporary vehicles",
            },
        ),
    ]
