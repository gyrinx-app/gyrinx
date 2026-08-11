from django.db import migrations, models


def pets_are_not_hired(apps, schema_editor):
    """Untick the profiles nobody hires directly.

    An editorial sweep over the content as it stands: everything homed
    under a Pet rank arrives with its keeper's gear rather than off the
    hire screen, as does anything an "adds a model" effect already names.
    From here on the flag is the author's to set.
    """
    Profile = apps.get_model("library", "Profile")
    OpAddsMiniature = apps.get_model("library", "OpAddsMiniature")
    spawned = OpAddsMiniature.objects.values_list("profile_id", flat=True)
    Profile.objects.filter(
        models.Q(category__name="Pet") | models.Q(pk__in=spawned)
    ).update(hireable=False)


def all_hireable(apps, schema_editor):
    Profile = apps.get_model("library", "Profile")
    Profile.objects.update(hireable=True)


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0039_the_rank_ladder_runs_across_sections"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="hireable",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "Untick for a model nobody hires directly — one that "
                    "arrives when something else brings it, a pet behind "
                    "its collar. An “adds a model” effect can still bring "
                    "it in."
                ),
                verbose_name="Offered for hire",
            ),
        ),
        migrations.RunPython(pets_are_not_hired, all_hireable),
    ]
