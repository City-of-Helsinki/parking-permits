# Generated by Django 3.2 on 2022-01-27 07:30

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("parking_permits", "0012_orderitem_payment_unit_price"),
    ]

    operations = [
        migrations.AddField(
            model_name="refund",
            name="description",
            field=models.TextField(blank=True, verbose_name="Description"),
        ),
    ]