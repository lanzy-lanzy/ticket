# Generated by Django 4.2.17 on 2025-05-07 00:31

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('trip', '0006_booking_senior_fare_rate_booking_senior_passengers_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='booking',
            name='emergency_contact_name',
            field=models.CharField(blank=True, max_length=200, null=True),
        ),
        migrations.AddField(
            model_name='booking',
            name='emergency_contact_number',
            field=models.CharField(blank=True, max_length=15, null=True),
        ),
        migrations.AddField(
            model_name='booking',
            name='emergency_contact_relationship',
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
    ]
