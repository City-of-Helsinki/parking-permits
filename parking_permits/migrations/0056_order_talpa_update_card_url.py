# Generated by Django 4.2.1 on 2024-03-20 11:38

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("parking_permits", "0055_alter_vehicle_vehicle_class"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="talpa_update_card_url",
            field=models.URLField(blank=True, verbose_name="Talpa update card url"),
        ),
    ]
