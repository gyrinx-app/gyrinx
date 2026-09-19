from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("pages", "0009_flatpageoptions_introduction")]

    operations = [
        migrations.AlterField(
            model_name="flatpagevisibility",
            name="groups",
            field=models.ManyToManyField(
                help_text="Select the groups that can view this page. A rule with no groups prevents everyone from viewing the page.",
                to="auth.group",
                verbose_name="Visible to Groups",
            ),
        ),
    ]
