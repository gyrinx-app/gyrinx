# Generated by Django 5.2.2 on 2025-06-28 20:31

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0071_historicallistattributeassignment_and_more"),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="campaign",
            name="core_campai_status_7e2b43_idx",
        ),
        migrations.RemoveIndex(
            model_name="list",
            name="core_list_status_3f8a91_idx",
        ),
        migrations.RemoveIndex(
            model_name="listfighter",
            name="core_listfi_injury__2adf42_idx",
        ),
        migrations.RemoveIndex(
            model_name="listfighter",
            name="core_listfi_xp_curr_9b3e1a_idx",
        ),
        migrations.RemoveIndex(
            model_name="listfighter",
            name="core_listfi_xp_tota_c4f892_idx",
        ),
        migrations.RemoveIndex(
            model_name="listfighter",
            name="core_listfi_list_ar_8e7f3b_idx",
        ),
        migrations.RemoveIndex(
            model_name="listfighter",
            name="core_listfi_list_in_4a9c2e_idx",
        ),
    ]
