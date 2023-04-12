# Generated by Django 3.2.18 on 2023-04-12 10:43

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("parking_permits", "0024_alter_customer_national_id_number"),
    ]

    operations = [
        migrations.AlterField(
            model_name="product",
            name="low_emission_discount",
            field=models.DecimalField(
                decimal_places=4, max_digits=6, verbose_name="Low emission discount"
            ),
        ),
    ]
