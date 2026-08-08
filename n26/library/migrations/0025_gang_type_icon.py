from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0024_alter_defaultassignment_amount"),
    ]

    operations = [
        migrations.AddField(
            model_name="gangtype",
            name="icon",
            field=models.TextField(
                blank=True,
                default="",
                help_text=(
                    "SVG markup for the gang type's badge, drawn beside its name "
                    "wherever the gang is listed. Paste the whole <svg> element; "
                    "draw it in one colour and it will follow the surrounding "
                    "text. Leave blank and nothing is drawn."
                ),
            ),
        ),
    ]
