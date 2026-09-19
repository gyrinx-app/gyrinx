from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("pages", "0009_flatpageoptions_introduction")]

    operations = [
        migrations.AlterField(
            model_name="flatpagevisibility",
            name="groups",
            field=models.ManyToManyField(
                help_text="Select the groups allowed by this rule. A rule with no groups grants no access. Other rules can still allow access to the page.",
                to="auth.group",
                verbose_name="Visible to Groups",
            ),
        ),
    ]
