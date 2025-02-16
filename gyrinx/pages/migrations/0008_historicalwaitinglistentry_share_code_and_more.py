# Generated by Django 5.1.5 on 2025-01-21 22:20

import uuid
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("pages", "0007_alter_historicalwaitinglistentry_options_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="historicalwaitinglistentry",
            name="share_code",
            field=models.UUIDField(default=uuid.uuid4, editable=False),
        ),
        migrations.AddField(
            model_name="waitinglistentry",
            name="share_code",
            field=models.UUIDField(default=uuid.uuid4, editable=False),
        ),
    ]
