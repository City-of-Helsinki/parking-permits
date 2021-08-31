# Generated by Django 3.2 on 2021-08-31 06:10

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("parking_permits_app", "0018_helsinki_profile_and_kmo_support_update"),
    ]

    operations = [
        migrations.AddField(
            model_name="address",
            name="postal_code",
            field=models.CharField(
                blank=True,
                default=None,
                max_length=5,
                null=True,
                verbose_name="Postal code",
            ),
        ),
    ]
