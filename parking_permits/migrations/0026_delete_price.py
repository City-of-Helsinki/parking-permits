# Generated by Django 3.2.18 on 2023-04-12 10:45

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("parking_permits", "0025_alter_product_low_emission_discount"),
    ]

    operations = [
        migrations.DeleteModel(
            name="Price",
        ),
    ]
