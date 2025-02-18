# Generated by Django 5.1.2 on 2024-11-24 21:18

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0013_rename_weapon_profile_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="contentweaponprofile",
            name="cost_sign",
            field=models.CharField(
                blank=True, choices=[("+", "+"), ("-", "-")], default="", max_length=1
            ),
        ),
        migrations.AddField(
            model_name="historicalcontentweaponprofile",
            name="cost_sign",
            field=models.CharField(
                blank=True, choices=[("+", "+"), ("-", "-")], default="", max_length=1
            ),
        ),
        migrations.AlterField(
            model_name="contentweaponprofile",
            name="accuracy_long",
            field=models.CharField(
                blank=True, default="", max_length=12, verbose_name="Acc L"
            ),
        ),
        migrations.AlterField(
            model_name="contentweaponprofile",
            name="accuracy_short",
            field=models.CharField(
                blank=True, default="", max_length=12, verbose_name="Acc S"
            ),
        ),
        migrations.AlterField(
            model_name="contentweaponprofile",
            name="ammo",
            field=models.CharField(
                blank=True, default="", max_length=12, verbose_name="Am"
            ),
        ),
        migrations.AlterField(
            model_name="contentweaponprofile",
            name="armour_piercing",
            field=models.CharField(
                blank=True, default="", max_length=12, verbose_name="Ap"
            ),
        ),
        migrations.AlterField(
            model_name="contentweaponprofile",
            name="damage",
            field=models.CharField(
                blank=True, default="", max_length=12, verbose_name="D"
            ),
        ),
        migrations.AlterField(
            model_name="contentweaponprofile",
            name="range_long",
            field=models.CharField(
                blank=True, default="", max_length=12, verbose_name="Rng L"
            ),
        ),
        migrations.AlterField(
            model_name="contentweaponprofile",
            name="range_short",
            field=models.CharField(
                blank=True, default="", max_length=12, verbose_name="Rng S"
            ),
        ),
        migrations.AlterField(
            model_name="contentweaponprofile",
            name="strength",
            field=models.CharField(
                blank=True, default="", max_length=12, verbose_name="Str"
            ),
        ),
        migrations.AlterField(
            model_name="historicalcontentweaponprofile",
            name="accuracy_long",
            field=models.CharField(
                blank=True, default="", max_length=12, verbose_name="Acc L"
            ),
        ),
        migrations.AlterField(
            model_name="historicalcontentweaponprofile",
            name="accuracy_short",
            field=models.CharField(
                blank=True, default="", max_length=12, verbose_name="Acc S"
            ),
        ),
        migrations.AlterField(
            model_name="historicalcontentweaponprofile",
            name="ammo",
            field=models.CharField(
                blank=True, default="", max_length=12, verbose_name="Am"
            ),
        ),
        migrations.AlterField(
            model_name="historicalcontentweaponprofile",
            name="armour_piercing",
            field=models.CharField(
                blank=True, default="", max_length=12, verbose_name="Ap"
            ),
        ),
        migrations.AlterField(
            model_name="historicalcontentweaponprofile",
            name="damage",
            field=models.CharField(
                blank=True, default="", max_length=12, verbose_name="D"
            ),
        ),
        migrations.AlterField(
            model_name="historicalcontentweaponprofile",
            name="range_long",
            field=models.CharField(
                blank=True, default="", max_length=12, verbose_name="Rng L"
            ),
        ),
        migrations.AlterField(
            model_name="historicalcontentweaponprofile",
            name="range_short",
            field=models.CharField(
                blank=True, default="", max_length=12, verbose_name="Rng S"
            ),
        ),
        migrations.AlterField(
            model_name="historicalcontentweaponprofile",
            name="strength",
            field=models.CharField(
                blank=True, default="", max_length=12, verbose_name="Str"
            ),
        ),
    ]
