# Generated by Django 3.2.13 on 2022-05-30 14:49

from django.db import migrations

from parking_permits.models.order import OrderStatus, OrderPaymentType


def update_payment_type(apps, schema_editor):
    model_class = apps.get_model("parking_permits", "Order")
    online_payment_orders = model_class.objects.filter(
        status=OrderStatus.CONFIRMED, talpa_order_id__isnull=False
    )
    online_payment_orders.update(payment_type=OrderPaymentType.ONLINE_PAYMENT)


class Migration(migrations.Migration):

    dependencies = [
        ("parking_permits", "0005_order_payment_type"),
    ]

    operations = [migrations.RunPython(update_payment_type, migrations.RunPython.noop)]