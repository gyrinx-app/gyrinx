from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("n26", "0027_a_campaign_is_a_thing_an_arbitrator_owns"),
        # Whatever this table held is read across to the site's own before
        # the table goes, so the drop waits for that to have happened.
        ("gyrinxsite", "0008_the_flags_an_edition_held_move_to_the_site"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="featureflag",
            name="n26_feature_flag_availability_known",
        ),
        migrations.DeleteModel(
            name="FeatureFlag",
        ),
    ]
