from django.db import migrations, models


def name_options_after_their_sets(apps, schema_editor):
    """Give every option the name it was already showing.

    Until now an option's wording on a hire screen was the name of the
    set of things it brings, so copying that across leaves every screen
    reading exactly as it did.
    """
    Option = apps.get_model("library", "Option")
    for option in Option.objects.select_related("default_set"):
        Option.objects.filter(pk=option.pk).update(name=option.default_set.name)


def forget_the_names(apps, schema_editor):
    apps.get_model("library", "Option").objects.update(name="")


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0033_sections_carry_the_order_they_print_in"),
    ]

    operations = [
        migrations.AddField(
            model_name="option",
            name="name",
            field=models.CharField(
                default="",
                help_text=(
                    'What a player is offered, e.g. "As standard" or "with '
                    'razor-sharp talons". This is the wording on the hire '
                    "screen."
                ),
                max_length=200,
            ),
            preserve_default=False,
        ),
        migrations.RunPython(name_options_after_their_sets, forget_the_names),
        migrations.AlterField(
            model_name="option",
            name="group",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "The axis this option belongs to. Blank puts it in the "
                    "basic choice — exactly one of those is taken, the first "
                    "unasked."
                ),
                null=True,
                on_delete=models.CASCADE,
                related_name="options",
                to="library.optiongroup",
                verbose_name="Axis",
            ),
        ),
        migrations.AlterField(
            model_name="optiongroup",
            name="name",
            field=models.CharField(
                help_text=(
                    "What this axis is called while you are writing it, e.g. "
                    '"Melee weapons" or "Additional grenades". Never shown to '
                    "a player: a hire screen puts the answers in front of "
                    "them and the question is what the answers are. Name it "
                    "for yourself."
                ),
                max_length=200,
                verbose_name="Name (authoring only)",
            ),
        ),
        migrations.AlterField(
            model_name="optiongroup",
            name="choose",
            field=models.CharField(
                choices=[("one", "Exactly one"), ("any", "Any number")],
                default="one",
                help_text=(
                    "Exactly one takes the first option unasked, and picking "
                    "another replaces it. Any number starts with none taken."
                ),
                max_length=10,
            ),
        ),
    ]
