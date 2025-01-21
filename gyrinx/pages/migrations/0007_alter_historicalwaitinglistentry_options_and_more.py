# Generated by Django 5.1.5 on 2025-01-21 22:14

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("pages", "0006_alter_waitinglistentry_skills"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="historicalwaitinglistentry",
            options={
                "get_latest_by": ("history_date", "history_id"),
                "ordering": ("-history_date", "-history_id"),
                "verbose_name": "historical waiting list entry",
                "verbose_name_plural": "historical waiting list entries",
            },
        ),
        migrations.AlterModelOptions(
            name="waitinglistentry",
            options={
                "verbose_name": "waiting list entry",
                "verbose_name_plural": "waiting list entries",
            },
        ),
    ]
