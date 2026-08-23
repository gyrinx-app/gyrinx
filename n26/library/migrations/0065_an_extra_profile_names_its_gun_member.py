import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0064_sheets_are_held_between_upload_and_import"),
    ]

    operations = [
        migrations.AddField(
            model_name="defaultassignment",
            name="gun_member",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="library.defaultassignment",
                help_text=(
                    "The weapon member of this set that this extra profile "
                    "rides — which gun the line lands under. Blank means the "
                    "profile rides whatever matching weapon the acquirer "
                    "already holds, the way an option set arms a gun the "
                    "built-ins bring."
                ),
            ),
        ),
    ]
