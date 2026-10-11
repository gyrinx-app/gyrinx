"""Assignments — a player's copy of an assignable, attached to something.

An assignment lives in exactly one place: on a gang, on a model, on
the stash, or on another assignment (a scope on a gun on a fighter).
That is its *host*, and the database enforces that exactly one is set.

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

Compared with a generic foreign key, this keeps referential integrity, and
resolving a whole gang's assignments to their assignables is **one** query
with a few left joins rather than one query per kind present.

Three **root** columns name the gang, model, and stash at the top of the
chain, written at save time, so everything on a gang is one indexed query
at any depth, without walking the chain.
"""

from django.core.exceptions import ValidationError
from django.db import models

from n26.core.constraints import NamesAnAssignable, exactly_one_of
from n26.core.models.abstract import Archived, Base

#: Field on Assignment -> the assignable model it points at. Adding a kind
#: means a matching nullable FK, a line here, and a migration; ``n26.checks``
#: compares these paths to the Assignable registry and refuses to boot if
#: they disagree. ``NamesAnAssignable`` iterates the field names.
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
    "campaign_type": "library.CampaignType",
    "asset": "library.Asset",
    "asset_table": "library.AssetTable",
    "counter": "library.Counter",
    "slot": "library.Slot",
    "pickable": "library.Pickable",
    "action": "library.Action",
    "rank_table": "library.RankTable",
}

HOST_FIELDS = ("gang", "miniature", "parent", "stash")


class Assignment(NamesAnAssignable, Base, Archived):
    profile = models.ForeignKey(
        "library.Profile",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assignments",
    )
    action = models.ForeignKey(
        "library.Action",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assignments",
    )
    rank_table = models.ForeignKey(
        "library.RankTable",
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
    campaign_type = models.ForeignKey(
        "library.CampaignType",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assignments",
    )
    asset = models.ForeignKey(
        "library.Asset",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assignments",
    )
    asset_table = models.ForeignKey(
        "library.AssetTable",
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

    # Where it lives — exactly one of gang, miniature, parent, or stash.
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

    # True when this assignment removes its assignable from the model
    # instead of granting it: an owner's own removal of a subtype or rule.
    # It never shows as a card line. Assembly compiles it to an
    # unconditional removal, so the removed item is hidden, not changed,
    # and returns as soon as this assignment is archived.
    removes = models.BooleanField(default=False)

    # The assignment that offered the slot this pick fills. It points at an
    # assignment, not the library Slot, so two slots of one type on one
    # holder stay independent and a card finds each pick without matching
    # on kinds. CASCADE to match ``caused_by``, which names the same
    # assignment: if one link PROTECTed what the other cascades, that
    # assignment could never be deleted.
    chosen_for = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="picks"
    )

    # The library Slot this pick fills. One assignment can offer two slots
    # (two skill-tree choices from one line), so ``chosen_for`` alone
    # cannot tell them apart. PROTECT stops a Slot being deleted while a
    # player's pick points at it.
    chosen_for_slot = models.ForeignKey(
        "library.Slot",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )

    chosen_for_status_revision = models.PositiveIntegerField(null=True, blank=True)

    # A holding's choice belongs to one ownership period. The campaign
    # retains the asset; the selected pick is an ordinary gang assignment.
    # Deleting an unclaimed holding keeps the archived pick and its history.
    chosen_for_holding = models.ForeignKey(
        "n26.CampaignAsset",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="choice_picks",
    )
    chosen_for_holding_revision = models.PositiveIntegerField(null=True, blank=True)

    # The OffersChoice this pick fills. One assignment may carry two offers
    # for the same kind of assignable, and the pick alone cannot show which
    # offer it fills.
    #
    # SET_NULL, unlike ``chosen_for_slot``'s PROTECT: a Slot is edited in
    # place, but an OffersChoice is recreated each time its modifier is
    # composed. PROTECT would make that edit fail once any gang had picked
    # from the offer. A pick without this link is matched to an offer by
    # its assignable instead (``effects._fill_choice_slots``).
    chosen_for_offer = models.ForeignKey(
        "library.OffersChoice",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    # The ROLLED ledger event this pick came from, where a table was rolled
    # for it. Null on a pick made without rolling and on anything that is
    # not a pick. Only one unarchived pick may use a roll, checked by
    # ``Operation._choose_for_slot`` under the gang's lock. A plain foreign
    # key, not one-to-one, because an archived pick keeps its roll when a
    # new pick reuses it. SET_NULL: ledger events are not deleted in normal
    # use, and a pick stays valid without its roll.
    roll = models.ForeignKey(
        "n26.LedgerEvent",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="picks",
    )

    # The built-in set member (``DefaultAssignment``) this assignment was
    # materialised from, and the carrier it was materialised for: a
    # model's membership, the gang's founding, or a bought mount's own
    # assignment. Both are null on purchases, rewards and picks, and on
    # copies stored without the link, which are matched by shape instead.
    # The pair records that a member is already materialised on a carrier,
    # so nothing infers it from reasons or creation order. PROTECT is safe
    # because a member is archived, never deleted, once anything has been
    # materialised from it.
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
                condition=models.Q(chosen_for_holding__isnull=True)
                | models.Q(
                    pickable__isnull=False,
                    gang__isnull=False,
                    chosen_for__isnull=True,
                    chosen_for_offer__isnull=True,
                    chosen_for_slot__isnull=False,
                    chosen_for_holding_revision__isnull=False,
                ),
                name="assignment_holding_pick_has_origin",
            ),
            models.CheckConstraint(
                condition=exactly_one_of(HOST_FIELDS),
                name="assignment_exactly_one_host",
            ),
            models.CheckConstraint(
                condition=exactly_one_of(ASSIGNABLE_FIELDS),
                name="assignment_exactly_one_assignable",
            ),
            # A removal must be hosted on a model and name a subtype or
            # rule, the only kinds an owner removes by hand. Assembly
            # compiles removals from a model's own assignments; a
            # gang-hosted removal would broadcast as a held line instead.
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
            # A removal suppresses its assignable instead of granting it,
            # so it must never satisfy the provenance lookup that says a
            # built-in member is already materialised for a carrier.
            models.CheckConstraint(
                condition=models.Q(removes=False)
                | models.Q(materialised_from__isnull=True),
                name="assignment_removal_carries_no_provenance",
            ),
            # Set both provenance fields or neither. A copy with only one
            # would be missed by both grant lookups and by the unique
            # constraint (NULLs never collide).
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
        """The rating contribution on this assignment's ledger entry, or 0."""
        entry = getattr(self, "ledger_entry", None)
        return entry.rating_contribution if entry else 0

    def member_or_none(self):
        return getattr(self, "member", None)

    @property
    def host(self):
        return self.gang or self.miniature or self.stash or self.parent

    @classmethod
    def with_assignables(cls, queryset=None):
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
