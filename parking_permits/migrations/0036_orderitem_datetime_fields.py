# Generated by Django 4.2.1 on 2023-06-02 14:46

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("parking_permits", "0035_subscription_order_item"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="orderitem",
            name="end_date",
        ),
        migrations.RemoveField(
            model_name="orderitem",
            name="start_date",
        ),
        migrations.AddField(
            model_name="orderitem",
            name="end_time",
            field=models.DateTimeField(blank=True, null=True, verbose_name="End time"),
        ),
        migrations.AddField(
            model_name="orderitem",
            name="start_time",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="Start time"
            ),
        ),
    ]