# Generated by Django 5.0.6 on 2024-09-17 09:06

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("parking_permits", "0063_refund_many_orders_support"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="refund",
            name="order",
        ),
    ]
