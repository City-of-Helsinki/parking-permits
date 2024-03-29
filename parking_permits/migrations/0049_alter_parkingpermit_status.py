# Generated by Django 4.2.1 on 2024-02-06 11:47

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("parking_permits", "0048_merge_20240202_0838"),
    ]

    operations = [
        migrations.AlterField(
            model_name="parkingpermit",
            name="status",
            field=models.CharField(
                choices=[
                    ("DRAFT", "Draft"),
                    ("PAYMENT_IN_PROGRESS", "Payment in progress"),
                    ("VALID", "Valid"),
                    ("CANCELLED", "Cancelled"),
                    ("CLOSED", "Closed"),
                ],
                default="DRAFT",
                max_length=32,
                verbose_name="Status",
            ),
        ),
    ]
