from django.db import migrations, models


class Migration(migrations.Migration):
    """A gang type's badge becomes a file in the site's storage, named by its
    address, instead of markup kept in the row.

    Renamed rather than dropped and re-added so the column keeps its identity
    through the change of what it holds.
    """

    dependencies = [
        ("library", "0025_gang_type_icon"),
    ]

    operations = [
        migrations.RenameField(
            model_name="gangtype",
            old_name="icon",
            new_name="icon_url",
        ),
        migrations.AlterField(
            model_name="gangtype",
            name="icon_url",
            field=models.CharField(
                blank=True,
                default="",
                max_length=500,
                help_text=(
                    "Address of the SVG drawn beside this gang type's name "
                    "wherever the gang is listed. Upload a drawing to fill "
                    "this in, or paste the address of one already uploaded. "
                    "Draw it in one colour and it will follow the surrounding "
                    "text. Leave blank and nothing is drawn."
                ),
            ),
        ),
    ]
