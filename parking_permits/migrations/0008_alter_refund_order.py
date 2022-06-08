# Generated by Django 3.2.13 on 2022-06-08 07:52

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("parking_permits", "0007_alter_refund_status"),
    ]

    operations = [
        migrations.AlterField(
            model_name="refund",
            name="order",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="refund",
                to="parking_permits.order",
                verbose_name="Order",
            ),
        ),
    ]
