import django.db.models.deletion
from django.db import migrations, models


def carry_columns_into_rows(apps, schema_editor):
    """Move each scope's single trait and category into condition rows.

    The columns held one value each; the rows hold as many as an author
    likes. A scope naming a trait becomes a ``has trait`` row naming that
    one trait, which reaches exactly the weapons it reached before.

    Written so a second run changes nothing: the row is found or founded
    per scope, and adding a value already in the set is a no-op.
    """
    TargetsWeapons = apps.get_model("library", "TargetsWeapons")
    HasTrait = apps.get_model("library", "HasTrait")
    InCategory = apps.get_model("library", "InCategory")

    for scope in TargetsWeapons.objects.exclude(
        with_trait__isnull=True, with_category__isnull=True
    ):
        if scope.with_trait_id is not None:
            row, _ = HasTrait.objects.get_or_create(scope=scope)
            row.traits.add(scope.with_trait_id)
        if scope.with_category_id is not None:
            row, _ = InCategory.objects.get_or_create(scope=scope)
            row.categories.add(scope.with_category_id)


def carry_rows_back_into_columns(apps, schema_editor):
    """Put a single-valued row back in its column.

    A row naming several values cannot go back into a column that holds
    one, so the first by primary key is kept and the rest are dropped:
    going backwards over this migration narrows what a scope says.
    """
    HasTrait = apps.get_model("library", "HasTrait")
    InCategory = apps.get_model("library", "InCategory")

    for row in HasTrait.objects.all():
        first = row.traits.order_by("pk").first()
        if first is not None:
            row.scope.with_trait = first
            row.scope.save(update_fields=["with_trait"])
    for row in InCategory.objects.all():
        first = row.categories.order_by("pk").first()
        if first is not None:
            row.scope.with_category = first
            row.scope.save(update_fields=["with_category"])


class Migration(migrations.Migration):
    """A weapon scope narrows by condition rows, as the model scope does.

    Three ways to narrow — the traits a weapon carries, the categories it
    is homed in, and the weapons it may be outright — each a row naming as
    many values as it likes. Any one value in a row matching is enough;
    every row must match. The two single-value columns this replaces are
    carried into rows first, so every scope already written keeps reaching
    the weapons it reached.
    """

    dependencies = [
        ("library", "0029_weapon_scope_narrows_by_category"),
    ]

    operations = [
        migrations.CreateModel(
            name="HasTrait",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "scope",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="has_trait",
                        to="library.targetsweapons",
                    ),
                ),
                (
                    "traits",
                    models.ManyToManyField(
                        help_text=(
                            "The weapon must carry one of these traits. Any one "
                            "of them matching is enough."
                        ),
                        related_name="+",
                        to="library.trait",
                    ),
                ),
            ],
            options={
                "verbose_name": "has trait",
                "verbose_name_plural": "has traits",
            },
        ),
        migrations.CreateModel(
            name="InCategory",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "scope",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="in_category",
                        to="library.targetsweapons",
                    ),
                ),
                (
                    "categories",
                    models.ManyToManyField(
                        help_text=(
                            "The weapon must be homed in one of these categories. "
                            "Any one of them matching is enough."
                        ),
                        related_name="+",
                        to="library.category",
                    ),
                ),
            ],
            options={
                "verbose_name": "in category",
                "verbose_name_plural": "in categories",
            },
        ),
        migrations.CreateModel(
            name="IsOneOf",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "scope",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="is_one_of",
                        to="library.targetsweapons",
                    ),
                ),
                (
                    "weapons",
                    models.ManyToManyField(
                        help_text=(
                            "The weapon must be one of these. Any one of them "
                            "matching is enough."
                        ),
                        related_name="+",
                        to="library.weapon",
                    ),
                ),
            ],
            options={
                "verbose_name": "is one of",
                "verbose_name_plural": "is one of",
            },
        ),
        migrations.RunPython(carry_columns_into_rows, carry_rows_back_into_columns),
        migrations.RemoveField(model_name="targetsweapons", name="with_trait"),
        migrations.RemoveField(model_name="targetsweapons", name="with_category"),
    ]
