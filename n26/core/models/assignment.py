"""An assignment is a player's hosted copy of library content.

Database constraints require exactly one host and one assignable. Hosts
are gangs, models, stashes or parent assignments. Each assignable kind
has its own nullable foreign key because the library uses a mixin rather
than a shared table. Startup checks compare these fields with the
assignable registry. See n26.library.models.assignable.

The host locates the content; caused_by identifies the assignment that
created it. Removal follows causes recursively. Explicit foreign keys
retain referential integrity and permit loading assignables through joins.

Save derives gang, miniature and stash roots for indexed subtree reads.
Membership assignments retain the miniature root set by the hiring operation.
"""

from django.core.exceptions import ValidationError
from django.db import models

from n26.core.constraints import NamesAnAssignable, exactly_one_of
from n26.core.models.abstract import Archived, Base

#: Map assignment fields to library models. Adding a kind requires its
#: nullable foreign key, this registry entry and a migration. Startup checks
#: compare the registry with the fields; NamesAnAssignable uses its keys.
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

    # Exactly one host must be set.
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

    # Removal follows this cause link recursively, independently of the host tree.
    caused_by = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="caused"
    )

    # Treat this as an owner-authored removal, not a grant or visible card line.
    # Assembly applies it as an unconditional suppression. Archiving the removal
    # allows the suppressed content to apply again.
    removes = models.BooleanField(default=False)

    # Identify the stored anchor that offered this pick. Use CASCADE like
    # caused_by so one link cannot block deletion required by the other.
    # Record the library slot separately when one anchor offers several choices.
    chosen_for = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="picks"
    )

    # Distinguish multiple slots offered by the same anchor. PROTECT retains
    # the authored slot while a player pick references it.
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

    # Distinguish multiple OffersChoice effects on the same anchor. Composing
    # a modifier recreates its effect, so SET_NULL permits that edit while
    # retaining picks. Without the link, effects._fill_choice_slots matches
    # existing picks to offers by assignable.
    chosen_for_offer = models.ForeignKey(
        "library.OffersChoice",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    # Record the roll used for this pick. Under the gang lock, operations allow
    # only one unarchived pick per roll. Archived picks retain the link when a
    # replacement reuses the roll, so this cannot be one-to-one. SET_NULL keeps
    # the pick if its event is deleted.
    roll = models.ForeignKey(
        "n26.LedgerEvent",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="picks",
    )

    # Record the DefaultAssignment member and carrier that produced a built-in
    # copy. Explicit provenance prevents inferring grants from reason or creation
    # order. Once used, members are archived rather than deleted, allowing
    # PROTECT to retain the source link.
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
            # Limit each member and carrier pair to one live copy while retaining archived copies.
            models.UniqueConstraint(
                fields=["materialised_from", "materialised_for"],
                condition=models.Q(archived=False),
                name="assignment_one_live_materialisation",
            ),
            # Exclude removal assignments from built-in provenance so suppression
            # cannot satisfy a grant requirement.
            models.CheckConstraint(
                condition=models.Q(removes=False)
                | models.Q(materialised_from__isnull=True),
                name="assignment_removal_carries_no_provenance",
            ),
            # Require both provenance fields together so grant lookups and the
            # unique constraint cannot miss a partial pair containing NULL.
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
        """Return hosted children and caused dependants, deduplicated by assignment ID."""
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
        """Derive gang, miniature and stash roots from the host chain."""
        if self.parent_id:
            self.gang_root_id = self.parent.gang_root_id
            self.miniature_root_id = self.parent.miniature_root_id
            self.stash_root_id = self.parent.stash_root_id
        elif self.stash_id:
            # Clear the previous miniature root when moving into the stash.
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
            # Preserve miniature_root: a gang-hosted membership contributes to its
            # model's rating. Operation.hire sets that root explicitly.
