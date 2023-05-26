# Generated by Django 3.2.18 on 2023-04-12 08:30

from django.db import migrations
import encrypted_fields.fields


class Migration(migrations.Migration):
    dependencies = [
        ("parking_permits", "0023_order_talpa_logged_in_checkout_url"),
    ]

    operations = [
        migrations.AlterField(
            model_name="customer",
            name="national_id_number",
            field=encrypted_fields.fields.SearchField(
                blank=True,
                db_index=True,
                encrypted_field_name="_national_id_number",
                hash_key="National identification number",
                max_length=66,
                null=True,
                unique=True,
            ),
        ),
    ]
