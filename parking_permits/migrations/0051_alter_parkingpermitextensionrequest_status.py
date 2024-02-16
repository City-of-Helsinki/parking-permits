# Generated by Django 4.2.1 on 2024-02-14 11:59

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("parking_permits", "0050_merge_20240208_0845"),
    ]

    operations = [
        migrations.AlterField(
            model_name="parkingpermitextensionrequest",
            name="status",
            field=models.CharField(
                choices=[
                    ("PENDING", "Pending"),
                    ("APPROVED", "Approved"),
                    ("CANCELLED", "Cancelled"),
                ],
                default="PENDING",
                max_length=12,
            ),
        ),
    ]
