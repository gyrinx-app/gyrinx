import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """The weapon conditions are named for the several values they hold.

    Each row names any number of traits or categories, and any one of them
    matching is enough — so the verbs an author writes are ``has_traits``
    and ``in_categories``, and the models and their reverse accessors
    follow. ``IsOneOf`` already read as several.

    A rename throughout, not a drop and re-add: the tables and the
    many-to-many tables beneath them are carried over with whatever they
    hold.
    """

    dependencies = [
        ("library", "0030_weapon_scope_narrows_by_rows"),
    ]

    operations = [
        migrations.RenameModel(old_name="HasTrait", new_name="HasTraits"),
        migrations.RenameModel(old_name="InCategory", new_name="InCategories"),
        migrations.AlterModelOptions(
            name="hastraits",
            options={
                "verbose_name": "has traits",
                "verbose_name_plural": "has traits",
            },
        ),
        migrations.AlterModelOptions(
            name="incategories",
            options={
                "verbose_name": "in categories",
                "verbose_name_plural": "in categories",
            },
        ),
        migrations.AlterField(
            model_name="hastraits",
            name="scope",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="has_traits",
                to="library.targetsweapons",
            ),
        ),
        migrations.AlterField(
            model_name="incategories",
            name="scope",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="in_categories",
                to="library.targetsweapons",
            ),
        ),
    ]
