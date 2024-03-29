# Generated by Django 4.2.1 on 2024-02-21 12:03

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("parking_permits", "0052_parkingpermit_end_type"),
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
                    (
                        "create_customer_permit_extension_request",
                        "Create Customer Permit Extension Request",
                    ),
                    (
                        "create_admin_permit_extension_request",
                        "Create Admin Permit Extension Request",
                    ),
                ],
                max_length=255,
            ),
        ),
    ]
