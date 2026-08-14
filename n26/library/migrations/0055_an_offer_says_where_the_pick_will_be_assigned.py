from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0054_weapon_shapes_print_strength_as_str"),
    ]

    operations = [
        migrations.RenameField(
            model_name="offerschoice",
            old_name="answer_host",
            new_name="will_be_assigned_to",
        ),
        migrations.AlterField(
            model_name="offerschoice",
            name="will_be_assigned_to",
            field=models.CharField(
                choices=[("bearer", "the bearer"), ("gang", "the gang")],
                default="bearer",
                help_text="Where the chosen thing's assignment will land. Almost always the bearer; a Leader's archetype pick is carried by the gang, not the Leader.",
                max_length=20,
            ),
        ),
    ]
