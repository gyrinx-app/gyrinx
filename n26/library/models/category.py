"""Where things sort when a collection shows them.

A given assignable always sorts into the same section and category,
whatever collection it appears in — an autogun is an Auto/Stub Weapon
under Ranged Weapons on every list that carries it. So classification is
the item's own data: a ``Section`` heading, a ``Category`` row inside
it, and a ``category`` foreign key on the ``Assignable`` mixin pointing
at its home.

Collections therefore hold entries only; display grouping derives from
each entry's item. A list "adds its own category" simply by containing
items whose home is that category — Subjugator weapons live in the
Subjugator category wherever they go; the category just never *appears*
outside lists that carry them.

The section began as a plain name on the category (two levels is what
the rulebook prints), and became a leaf model when authoring gave it a
form: a free-text heading means "Ranged Weapons" and "ranged weapons"
silently fork the taxonomy, where a pick list cannot.

Not to be confused with ``CollectionSection`` — the *tiers* a
collection is divided into (Primary, Secondary). A Section is a heading
of the catalogue's taxonomy; a CollectionSection is a heading one list
declares for itself.
"""

from django.db import models
from django.db.models.functions import Lower

from n26.library.models.assignable import Family
from n26.library.models.base import Content


class Section(Content):
    """One heading of the taxonomy — the level above categories."""

    family = Family.BASE

    name = models.CharField(
        max_length=200,
        help_text='The heading above categories, e.g. "Ranged Weapons".',
    )
    position = models.PositiveIntegerField(
        default=0,
        help_text="Sort order among headings.",
    )

    class Meta:
        verbose_name = "section"
        verbose_name_plural = "sections"
        ordering = ["position", "name"]
        constraints = [
            models.UniqueConstraint(
                "pack", Lower("name"), name="section_unique_per_pack"
            ),
        ]

    def __str__(self):
        return self.name


class Category(Content):
    """One home in the taxonomy: a category name inside a section."""

    family = Family.BASE

    section = models.ForeignKey(
        Section,
        on_delete=models.PROTECT,
        related_name="categories",
        help_text="The heading this category sits under.",
    )
    name = models.CharField(
        max_length=200,
        help_text='The category itself, e.g. "Auto/Stub Weapons".',
    )
    position = models.PositiveIntegerField(
        default=0,
        help_text=(
            "Sort order across the whole taxonomy. Sections appear in the "
            "order their first category does."
        ),
    )

    class Meta:
        verbose_name = "category"
        verbose_name_plural = "categories"
        ordering = ["position", "section__name", "name"]
        constraints = [
            # The same category name may recur across sections — the rulebook
            # has Primitive Weapons under both Ranged and Close Combat.
            models.UniqueConstraint(
                "pack",
                "section",
                Lower("name"),
                name="category_unique_per_pack",
            ),
        ]

    def __str__(self):
        return f"{self.section}: {self.name}"
