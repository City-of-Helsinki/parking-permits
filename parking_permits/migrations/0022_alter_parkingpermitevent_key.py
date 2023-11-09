# Generated by Django 3.2.13 on 2022-11-25 13:34

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("parking_permits", "0021_parkingpermitevent"),
    ]

    operations = [
        migrations.AlterField(
            model_name="parkingpermitevent",
            name="key",
            field=models.CharField(
                choices=[
                    ("create_permit", "Create Permit"),
                    ("update_permit", "Update Permit"),
                    ("end_permit", "End Permit"),
                    ("create_order", "Create Order"),
                    ("renew_order", "Renew Order"),
                    ("create_refund", "Create Refund"),
                    ("add_temporary_vehicle", "Add Temporary Vehicle"),
                    ("remove_temporary_vehicle", "Remove Temporary Vehicle"),
                ],
                max_length=255,
            ),
        ),
    ]
