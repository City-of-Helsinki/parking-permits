# Generated by Django 3.2 on 2021-06-28 06:17

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("parking_permits_app", "0005_alter_product_shared_product_id_to_be_null"),
    ]

    operations = [
        migrations.AddField(
            model_name="parkingzone",
            name="description",
            field=models.TextField(blank=True, null=True, verbose_name="Description"),
        ),
    ]
