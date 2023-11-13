# Generated by Django 4.2.1 on 2023-11-09 16:57

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("parking_permits", "0042_add_permits_and_order_to_refund"),
    ]

    operations = [
        migrations.AlterField(
            model_name="subscription",
            name="cancel_reason",
            field=models.CharField(
                blank=True,
                choices=[
                    ("RENEWAL_FAILED", "Renewal failed"),
                    ("USER_CANCELLED", "User cancelled"),
                    ("PERMIT_EXPIRED", "Permit expired"),
                ],
                max_length=20,
                null=True,
                verbose_name="Cancel reason",
            ),
        ),
    ]