"""Assignments — a player's copy of an assignable, attached to something.

An assignment lives in exactly one place: on a gang, on a model, or on
another assignment (a scope on a gun on a fighter). That is its *host*, and
the database enforces that exactly one is set.

It also names exactly one **assignable**. Because assignables are a mixin
rather than a shared table (see ``n26.library.models.assignable``), there is no
single column to point at — instead there is one nullable foreign key per
kind, listed in ``ASSIGNABLE_FIELDS``, with a database constraint that
exactly one is set. A startup check (``n26.checks``) refuses to boot if a
kind of assignable exists with no column here, so the list cannot silently
fall behind.

Beside the host sits the **cause**: the assignment that brought this one —
a membership bringing a fighter's built-in kit, a purchase bringing what
came with it. Removal follows the cause chain down, and provenance ("came
with the Cutter") is read off the same link.

The payoff over a loose pointer: real referential integrity, and resolving
a whole gang's assignments to their assignables is **one** query with a few
left joins rather than one query per kind present.

Two **root** columns name the gang and model at the top of the chain,
written at save time, so "everything on this gang" is one indexed query at
any depth — no walking.
"""

from django.core.exceptions import ValidationError
from django.db import models

from n26.core.constraints import NamesAnAssignable, exactly_one_of
from n26.core.models.abstract import Archived, Base

#: Field name on Assignment -> the assignable model it points at.
#: Adding a kind of assignable means adding a line here and a migration;
#: ``n26.checks`` fails loudly if you forget.
#: Field on Assignment -> the assignable model it points at. The paths are
#: what ``n26.checks`` compares against the registry of Assignable
#: subclasses; the field names are what ``NamesAnAssignable`` iterates.
ASSIGNABLE_FIELDS = {
    "profile": "library.Profile",
    "weapon": "library.Weapon",
    "weapon_profile": "library.WeaponProfile",
    "wargear": "library.Wargear",
    "weapon_accessory": "library.WeaponAccessory",
    "subtype": "library.Subtype",
    "skill": "library.Skill",
    "trait": "library.Trait",
    "collection": "library.Collection",
    "power": "library.Power",
    "rule": "library.Rule",
    "affiliation": "library.Affiliation",
    "hidden": "library.Hidden",
    "gang_type": "library.GangType",
    "counter": "library.Counter",
    "slot": "library.Slot",
    "pickable": "library.Pickable",
}

HOST_FIELDS = ("gang", "miniature", "parent", "stash")


class Assignment(NamesAnAssignable, Base, Archived):
    # What was assigned — exactly one of these, see ASSIGNABLE_FIELDS.
    profile = models.ForeignKey(
        "library.Profile",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assignments",
    )
    weapon = models.ForeignKey(
        "library.Weapon",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assignments",
    )
    weapon_profile = models.ForeignKey(
        "library.WeaponProfile",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assignments",
    )
    weapon_accessory = models.ForeignKey(
        "library.WeaponAccessory",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assignments",
    )
    wargear = models.ForeignKey(
        "library.Wargear",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assignments",
    )
    subtype = models.ForeignKey(
        "library.Subtype",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assignments",
    )
    skill = models.ForeignKey(
        "library.Skill",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assignments",
    )
    trait = models.ForeignKey(
        "library.Trait",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assignments",
    )
    collection = models.ForeignKey(
        "library.Collection",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assignments",
    )
    power = models.ForeignKey(
        "library.Power",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assignments",
    )
    rule = models.ForeignKey(
        "library.Rule",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assignments",
    )
    affiliation = models.ForeignKey(
        "library.Affiliation",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assignments",
    )
    hidden = models.ForeignKey(
        "library.Hidden",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assignments",
    )
    gang_type = models.ForeignKey(
        "library.GangType",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assignments",
    )
    counter = models.ForeignKey(
        "library.Counter",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assignments",
    )
    slot = models.ForeignKey(
        "library.Slot",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assignments",
    )
    pickable = models.ForeignKey(
        "library.Pickable",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assignments",
    )

    # Where it lives — exactly one of these three.
    gang = models.ForeignKey(
        "n26.Gang",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="hosted_assignments",
    )
    miniature = models.ForeignKey(
        "n26.Miniature",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="hosted_assignments",
    )
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="children"
    )
    stash = models.ForeignKey(
        "n26.Stash",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="hosted_assignments",
    )

    # Why this exists. Removing the cause removes everything it caused.
    caused_by = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="caused"
    )

    # An assignment that takes its assignable away rather than holding
    # it: the owner's own removal of a subtype or rule. Never a line on
    # a card — it is compiled at read time to an unconditional removal,
    # so what it cancels is suppressed rather than written to, and comes
    # back the moment this assignment is archived.
    removes = models.BooleanField(default=False)

    # Which choice this settles: the slot's own assignment, not the slot
    # row — so two slots of one type on one holder stay independent and a
    # card reads what was chosen without inferring anything from kinds.
    # Declared like ``caused_by`` because it names the same assignment: a
    # pick's cause is the slot that offered it, and one link protecting
    # what the other cascades would make the row impossible to delete.
    chosen_for = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="picks"
    )

    # Which slot this pick settles. One assignment may ask twice — a
    # thing giving two skill-tree choices opens both from one line — so
    # the asking assignment alone cannot say which choice a pick
    # answers. PROTECT: a library row must not vanish out from under a
    # player's pick.
    chosen_for_slot = models.ForeignKey(
        "library.Slot",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )

    # Which offer this pick settles, for the other way a choice is asked.
    # The same reasoning as ``chosen_for_slot``, and the same need: one
    # line may offer two choices of a kind — a primary role and a
    # secondary one — and both are answered by the same kind of thing, so
    # nothing about the answer says which question it was.
    #
    # SET_NULL where a slot PROTECTs, because the two rows do not live
    # alike: a slot is a thing an author edits in place, while an offer is
    # part of a modifier and is written afresh every time that modifier is
    # composed. Holding the old row hostage would make renaming a
    # question fail for everyone who had answered it. Losing the link is
    # survivable — an unnamed answer is read by what it is instead, which
    # is what every answer written before there was a question to name
    # relies on.
    chosen_for_offer = models.ForeignKey(
        "library.OffersChoice",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    # Which built-in membership this materialised, and for which carrier
    # — the profile's membership, the gang's founding, the bought mount's
    # own assignment. Null on everything that was not materialised from a
    # set — purchases, rewards, picks — and on copies that carry no
    # recorded link, which are matched by the shape they were written in
    # instead. The pair is what says a member is already satisfied on a
    # carrier, so nothing infers it from reasons or newest-first
    # ordering. PROTECT holds because a member is only ever archived,
    # never deleted, once anything has materialised from it.
    materialised_from = models.ForeignKey(
        "library.DefaultAssignment",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    materialised_for = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
    )

    # Denormalised roots, maintained in save().
    gang_root = models.ForeignKey(
        "n26.Gang",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="assignments",
    )
    miniature_root = models.ForeignKey(
        "n26.Miniature",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="assignments",
    )
    stash_root = models.ForeignKey(
        "n26.Stash",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="assignments",
    )

    ASSIGNABLE_FIELDS = ASSIGNABLE_FIELDS

    class Meta:
        verbose_name = "assignment"
        verbose_name_plural = "assignments"
        ordering = ["created"]
        constraints = [
            models.CheckConstraint(
                condition=exactly_one_of(HOST_FIELDS),
                name="assignment_exactly_one_host",
            ),
            models.CheckConstraint(
                condition=exactly_one_of(ASSIGNABLE_FIELDS),
                name="assignment_exactly_one_assignable",
            ),
            # A removal names what it takes away, and only the kinds an
            # owner edits by hand may be taken away this way — hosted on
            # the model it edits, because assembly compiles removals off
            # a model's own rows and a gang-hosted one would broadcast
            # as a held line instead.
            models.CheckConstraint(
                condition=models.Q(removes=False)
                | (
                    models.Q(miniature__isnull=False)
                    & (models.Q(subtype__isnull=False) | models.Q(rule__isnull=False))
                ),
                name="assignment_removes_names_subtype_or_rule",
            ),
            # One live copy per member per carrier. Archived copies stay
            # out of it, so an owner who parts with a grant may see it
            # rematerialised deliberately without the old record blocking.
            models.UniqueConstraint(
                fields=["materialised_from", "materialised_for"],
                condition=models.Q(archived=False),
                name="assignment_one_live_materialisation",
            ),
            # A removal is machinery, never a grant: it suppresses its
            # assignable rather than holding it, so it must never satisfy
            # the provenance lookup that says a built-in member is already
            # materialised for a carrier.
            models.CheckConstraint(
                condition=models.Q(removes=False)
                | models.Q(materialised_from__isnull=True),
                name="assignment_removal_carries_no_provenance",
            ),
            # Provenance is a pair or nothing. A copy naming only half
            # would slip both grant lookups and the unique constraint
            # (NULLs never collide), so the half-written shape is refused
            # outright.
            models.CheckConstraint(
                condition=(
                    models.Q(
                        materialised_from__isnull=True,
                        materialised_for__isnull=True,
                    )
                    | models.Q(
                        materialised_from__isnull=False,
                        materialised_for__isnull=False,
                    )
                ),
                name="assignment_provenance_is_a_pair",
            ),
        ]
        indexes = [
            models.Index(fields=["gang_root"], name="assignment_gang_root_idx"),
            models.Index(fields=["miniature_root"], name="assignment_mini_root_idx"),
            models.Index(fields=["stash_root"], name="assignment_stash_root_idx"),
        ]

    def __str__(self):
        return f"{self.assignable} on {self.host}"

    @property
    def archive_with(self):
        """Removal takes the subtree: things hung off this, and things it caused."""
        related = [*self.children.all(), *self.caused.all()]
        return list({a.pk: a for a in related}.values())

    @property
    def rating(self):
        """What this contributes. Lives on the ledger entry — read it there."""
        entry = getattr(self, "ledger_entry", None)
        return entry.rating_contribution if entry else 0

    def member_or_none(self):
        """The model this assignment is about, when hosted on the gang."""
        return getattr(self, "member", None)

    @property
    def host(self):
        """Whichever of gang / model / stash / parent this lives on."""
        return self.gang or self.miniature or self.stash or self.parent

    @classmethod
    def with_assignables(cls, queryset=None):
        """Resolve every assignment's assignable in one query."""
        return (queryset if queryset is not None else cls.objects).select_related(
            *ASSIGNABLE_FIELDS
        )

    def clean(self):
        super().clean()
        if sum(getattr(self, f"{f}_id") is not None for f in HOST_FIELDS) != 1:
            raise ValidationError(
                "An assignment must have exactly one host: gang, model, "
                "stash, or parent."
            )

    def save(self, *args, **kwargs):
        self._set_roots()
        super().save(*args, **kwargs)

    def _set_roots(self):
        """Derive the gang and model at the top of this assignment's chain."""
        if self.parent_id:
            self.gang_root_id = self.parent.gang_root_id
            self.miniature_root_id = self.parent.miniature_root_id
            self.stash_root_id = self.parent.stash_root_id
        elif self.stash_id:
            # A move must shed the old roots, not only gain new ones.
            self.stash_root_id = self.stash_id
            self.gang_root_id = self.stash.gang_id
            self.miniature_root_id = None
        elif self.miniature_id:
            self.miniature_root_id = self.miniature_id
            self.stash_root_id = None
            membership = getattr(self.miniature, "membership", None)
            self.gang_root_id = membership.gang_id if membership else None
        elif self.gang_id:
            self.gang_root_id = self.gang_id
            # miniature_root is left alone: a membership assignment is hosted on
            # the gang but is *about* the model it brought in, so what the hire
            # was worth counts towards that model's rating. n26.operations
            # sets it.
