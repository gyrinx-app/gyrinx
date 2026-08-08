"""
Statlines.

Four layers, from definition to value:

``Stat``
    A single stat definition — Movement, Toughness — with the display rules
    for rendering its values. Defined once, reused across statline types.

``StatlineType`` / ``StatlineTypeStat``
    A named *shape* of statline (Fighter, Vehicle), and the ordered set of
    stats making it up. ``StatlineTypeStat`` is the through model, carrying
    the position.

``Statline`` / ``StatlineStat``
    An actual set of values. A ``Statline`` belongs to exactly one of a
    fighter ``Profile`` or a ``WeaponProfile``; in both cases its shape is
    read from one level up (the profile type, or the weapon), so it cannot
    drift out of step with what it is supposed to implement.

Ported from gyrinx's ``library/models/statline.py``, dropping the history
tables and the fighter-category defaults.
"""

import re

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower

from n26.core.constraints import exactly_one_of
from n26.library.models.assignable import Family
from n26.library.models.base import Content

#: Rendered in place of an absent value.
EMPTY_VALUE = "-"

#: A statline belongs to exactly one of these.
STATLINE_OWNERS = ("profile", "weapon_profile")


#: Django model name -> the Statline column that holds it.
_OWNER_FIELDS = {"profile": "profile", "weaponprofile": "weapon_profile"}


def _owner_field(owner):
    """Which column on Statline holds this kind of owner."""
    try:
        return _OWNER_FIELDS[owner._meta.model_name]
    except KeyError:
        raise ValueError(
            f"{type(owner).__name__} cannot own a statline — expected a "
            f"Profile or a WeaponProfile."
        ) from None


_SMART_QUOTES = {
    "“": '"',
    "”": '"',
    "‘": "'",
    "’": "'",
}


class Stat(Content):
    """A stat definition, shared across statline types."""

    family = Family.FOUNDATION

    field_name = models.CharField(
        max_length=50,
        blank=True,
        help_text="Internal name, e.g. 'movement'. Derived from full name if blank.",
    )
    short_name = models.CharField(
        max_length=10, help_text="Short display name, e.g. 'M'."
    )
    full_name = models.CharField(
        max_length=50, help_text="Full display name, e.g. 'Movement'."
    )
    is_inverted = models.BooleanField(
        default=False,
        help_text=(
            "Improving this stat means a lower number, e.g. Weapon Skill 4+ to 3+."
        ),
    )
    is_inches = models.BooleanField(
        default=False,
        help_text='A distance, displayed with a quote mark, e.g. Movement 3".',
    )
    is_modifier = models.BooleanField(
        default=False,
        help_text="Modifies a roll, displayed with a sign prefix, e.g. +3.",
    )
    is_target = models.BooleanField(
        default=False,
        help_text="A roll target, displayed with a plus suffix, e.g. 3+.",
    )

    class Meta:
        verbose_name = "stat"
        verbose_name_plural = "stats"
        ordering = ["full_name"]
        constraints = [
            models.UniqueConstraint(
                "pack", Lower("field_name"), name="stat_field_name_unique_per_pack"
            ),
        ]

    def __str__(self):
        return f"{self.short_name} ({self.full_name})"

    def save(self, *args, **kwargs):
        if not self.field_name and self.full_name:
            self.field_name = self.derive_field_name(self.full_name)
        super().save(*args, **kwargs)

    @staticmethod
    def derive_field_name(full_name):
        """``"Front Toughness"`` -> ``"front_toughness"``."""
        return re.sub(r"[^a-z0-9]+", "_", full_name.lower()).strip("_")

    def format_value(self, raw):
        """Render ``raw`` according to this stat's display rules.

        ``4`` -> ``4"`` for a distance, ``3`` -> ``3+`` for a roll target,
        ``2`` -> ``+2`` for a modifier. Values that aren't plain integers are
        passed through untouched, so ``"D6"`` or ``"*"`` survive.
        """
        value = (raw or "").strip()
        for smart, plain in _SMART_QUOTES.items():
            value = value.replace(smart, plain)

        if value in ("", EMPTY_VALUE):
            return EMPTY_VALUE

        if self.is_inches:
            return self._reformat(value.rstrip('"'), '{}"')
        if self.is_target:
            return self._reformat(value.rstrip("+"), "{}+")
        if self.is_modifier:
            number = self._as_int(value.lstrip("+-"))
            if number is None:
                return value
            number = -abs(number) if value.startswith("-") else abs(number)
            return f"+{number}" if number >= 0 else str(number)
        return value

    def _reformat(self, stripped, template):
        number = self._as_int(stripped)
        return template.format(number) if number is not None else stripped.strip()

    @staticmethod
    def _as_int(value):
        try:
            return int(value.strip())
        except ValueError:
            return None

    @property
    def placeholder(self):
        """An example value, for form inputs."""
        if self.is_inches:
            return '4"'
        if self.is_target:
            return "3+"
        if self.is_modifier:
            return "+1"
        return "3"


class StatlineType(Content):
    """A named shape of statline, e.g. Fighter or Vehicle."""

    family = Family.FOUNDATION

    name = models.CharField(max_length=255)

    class Meta:
        verbose_name = "statline type"
        verbose_name_plural = "statline types"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                "pack", Lower("name"), name="statline_type_unique_per_pack"
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def field_names(self):
        return [type_stat.field_name for type_stat in self.stats.all()]


class StatlineTypeStat(Content):
    """Places a stat within a statline type, at a position."""

    statline_type = models.ForeignKey(
        StatlineType, on_delete=models.CASCADE, related_name="stats"
    )
    stat = models.ForeignKey(
        Stat, on_delete=models.PROTECT, related_name="statline_type_stats"
    )
    position = models.PositiveIntegerField(
        default=0, help_text="Display order; lower numbers come first."
    )
    is_highlighted = models.BooleanField(
        default=False,
        help_text="Drawn with emphasis — the psychology stats (Ld, Cl, Wil, Int).",
    )
    is_first_of_group = models.BooleanField(
        default=False,
        help_text="Starts a new visual group; renderers break the row here.",
    )

    class Meta:
        verbose_name = "statline type stat"
        verbose_name_plural = "statline type stats"
        ordering = ["statline_type", "position"]
        constraints = [
            models.UniqueConstraint(
                "statline_type", "stat", name="statline_type_stat_unique"
            ),
        ]

    def __str__(self):
        return f"{self.statline_type.name} — {self.stat}"

    @property
    def field_name(self):
        return self.stat.field_name

    @property
    def short_name(self):
        return self.stat.short_name

    @property
    def full_name(self):
        return self.stat.full_name


class Statline(Content):
    """A concrete set of stat values, for a fighter or for a weapon profile.

    The shape is not stored here — it is read from the owner (a fighter's
    profile type, a weapon profile's weapon), so a statline cannot disagree
    with the type it is supposed to implement.
    """

    #: Exactly one of these is set.
    OWNERS = STATLINE_OWNERS

    profile = models.OneToOneField(
        "library.Profile",
        on_delete=models.CASCADE,
        related_name="statline",
        null=True,
        blank=True,
    )
    weapon_profile = models.OneToOneField(
        "library.WeaponProfile",
        on_delete=models.CASCADE,
        related_name="statline",
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "statline"
        verbose_name_plural = "statlines"
        constraints = [
            models.CheckConstraint(
                condition=exactly_one_of(STATLINE_OWNERS),
                name="statline_exactly_one_owner",
            ),
        ]

    def __init__(self, *args, owner=None, **kwargs):
        """``Statline(owner=weapon_profile)`` routes to the right column."""
        if owner is not None:
            kwargs[_owner_field(owner)] = owner
        super().__init__(*args, **kwargs)

    def __str__(self):
        return f"{self.owner} statline"

    @property
    def owner(self):
        """The fighter profile or weapon profile these values belong to."""
        return self.profile or self.weapon_profile

    @property
    def statline_type(self):
        """The shape, read from one level up. Never stored, so never wrong."""
        return self.owner.statline_type

    def clean(self):
        """Every stat in the type must have a value, and no strays."""
        if sum(getattr(self, f"{f}_id") is not None for f in self.OWNERS) != 1:
            raise ValidationError(
                "A statline must belong to exactly one of a profile or a "
                "weapon profile."
            )
        if self._state.adding:
            # Stats are attached after the first save. Note this cannot be a
            # `self.pk` check: ULID pks are generated client-side, so an
            # unsaved instance already has one.
            return

        required = {ts.pk for ts in self.statline_type.stats.all()}
        provided = set(self.stats.values_list("statline_type_stat_id", flat=True))

        if missing := required - provided:
            names = StatlineTypeStat.objects.filter(pk__in=missing)
            raise ValidationError(
                f"Missing values for: {', '.join(sorted(s.full_name for s in names))}"
            )
        if stray := provided - required:
            names = StatlineTypeStat.objects.filter(pk__in=stray)
            raise ValidationError(
                f"Not part of the {self.statline_type} statline: "
                f"{', '.join(sorted(s.full_name for s in names))}"
            )

    def as_dict(self):
        """``{field_name: formatted value}``, in type order."""
        return {stat.field_name: stat.formatted_value for stat in self.ordered_stats()}

    def ordered_stats(self):
        """The values in display order.

        Uses rows the caller has already prefetched — ``n26.card.card_rows``
        does, when asked for statlines — and otherwise fetches them with the
        joins it needs. Either way this is at most one query, never one per
        stat, which is what stops a card full of weapons turning into an
        N+1.
        """
        if "stats" in getattr(self, "_prefetched_objects_cache", {}):
            return sorted(self.stats.all(), key=lambda s: s.statline_type_stat.position)
        return list(
            self.stats.select_related("statline_type_stat__stat").order_by(
                "statline_type_stat__position"
            )
        )


class StatlineStat(Content):
    """One stat value within a statline."""

    statline = models.ForeignKey(
        Statline, on_delete=models.CASCADE, related_name="stats"
    )
    statline_type_stat = models.ForeignKey(
        StatlineTypeStat, on_delete=models.PROTECT, related_name="values"
    )
    value = models.CharField(
        max_length=10, help_text="""The raw value, e.g. '5"', '12', '4+', '-'."""
    )

    class Meta:
        verbose_name = "statline stat"
        verbose_name_plural = "statline stats"
        ordering = ["statline_type_stat__position"]
        constraints = [
            models.UniqueConstraint(
                "statline", "statline_type_stat", name="statline_stat_unique"
            ),
        ]

    def __str__(self):
        return f"{self.short_name}: {self.formatted_value}"

    def save(self, *args, **kwargs):
        """Store the value as its stat says it reads.

        An author typing 4 for a Movement means 4", and typing 3 for a
        Save means 3+ — so the stored value is normalised here rather
        than left to whoever wrote the form. In ``save`` and not
        ``clean`` because ``objects.create`` never calls ``full_clean``:
        the verbs and any importer must land the same canonical value a
        form does. Values that are not plain numbers — S for the
        wielder's Strength, E for engaged only, D6 — pass through
        untouched, and a blank stays blank rather than becoming a dash.
        """
        if self.value and self.statline_type_stat_id:
            self.value = self.statline_type_stat.stat.format_value(self.value)
        super().save(*args, **kwargs)

    def clean(self):
        """The stat must belong to the statline type the profile calls for."""
        if not (self.statline_id and self.statline_type_stat_id):
            return
        expected = self.statline.statline_type
        if self.statline_type_stat.statline_type_id != expected.pk:
            raise ValidationError(
                {
                    "statline_type_stat": (
                        f"{self.statline_type_stat.full_name} belongs to "
                        f"{self.statline_type_stat.statline_type}, "
                        f"but this statline is a {expected}."
                    )
                }
            )

    @property
    def stat(self):
        return self.statline_type_stat.stat

    @property
    def field_name(self):
        return self.statline_type_stat.field_name

    @property
    def short_name(self):
        return self.statline_type_stat.short_name

    @property
    def formatted_value(self):
        return self.stat.format_value(self.value)
