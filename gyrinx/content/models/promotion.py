"""
Promotion path content models.

Content-driven replacement for the promotion advancement configs that were hardcoded in
``gyrinx/core/forms/advancement.py`` (``skill_promote_specialist`` /
``skill_promote_champion``). See ``.claude/notes/promotions-rules-spec.md`` for the rules
research and ``.claude/notes/promotions-epic-design.md`` for the epic.

``ContentPromotionPath`` expresses every promotion family in the rules with one model:

- **Category relabel** (e.g. Ganger → Specialist): the fighter's category label changes and
  they gain access benefits, but they remain the same fighter type.
- **Type change** (e.g. Wrecker → Road Sergeant | Arms Master): the fighter from now on
  *counts as* a chosen target type for equipment and skill access, and swaps special rules.

In both cases — per the rules, and by decision — **statline and base cost never change**:
promotion is an identity-and-access change with a flat, content-authored ``cost_increase``.
Wiring this model into the advancement flow is Phase 2; the model is inert until then.
"""

from django.core.exceptions import ValidationError
from django.db import models
from simple_history.models import HistoricalRecords

from gyrinx.models import FighterCategoryChoices

from .base import Content

# Categories a promotion may relabel a fighter to. Must stay in sync with
# ``gyrinx.core.models.list._common.ALLOWED_CATEGORY_OVERRIDES`` — applying a promotion sets
# the fighter's ``category_override``, which is validated against that list at apply time.
# Content must not import from core (circular layer), so this is a deliberate local mirror;
# a drift guard test asserts the two lists stay identical.
PROMOTION_TARGET_CATEGORIES = [
    FighterCategoryChoices.LEADER,
    FighterCategoryChoices.CHAMPION,
    FighterCategoryChoices.GANGER,
    FighterCategoryChoices.JUVE,
    FighterCategoryChoices.PROSPECT,
    FighterCategoryChoices.SPECIALIST,
]


class ContentPromotionPath(Content):
    """A content-authored promotion path (e.g. "Promote to Specialist").

    Applying it (Phase 2) sets the fighter's ``category_override`` and, for type changes,
    records which target type the fighter now counts as for equipment and skill access.
    The fighter keeps its ``content_fighter`` statline and base cost in all cases — cost
    impact is only the flat ``cost_increase``.
    """

    class Kind(models.TextChoices):
        RELABEL = "RELABEL", "Category relabel"
        TYPE_CHANGE = "TYPE_CHANGE", "Type change"

    class Timing(models.TextChoices):
        POST_BATTLE = "POST_BATTLE", "Post-battle sequence"
        DOWNTIME = "DOWNTIME", "Downtime"
        FOUNDING = "FOUNDING", "At gang founding"
        LEADER_DEATH = "LEADER_DEATH", "On leader death"

    GRANTS_SKILL_NONE = "none"
    GRANTS_SKILL_CHOICES = [
        (GRANTS_SKILL_NONE, "No skill"),
        ("primary_random", "Random Primary Skill"),
        ("primary_chosen", "Chosen Primary Skill"),
        ("secondary_random", "Random Secondary Skill"),
        ("secondary_chosen", "Chosen Secondary Skill"),
        ("any_random", "Random Skill (Any Set)"),
    ]

    name = models.CharField(max_length=255, help_text="e.g. 'Promote to Specialist'")
    kind = models.CharField(
        max_length=16,
        choices=Kind.choices,
        default=Kind.RELABEL,
        help_text=(
            "Category relabel: only the fighter's category label changes. Type change: the "
            "fighter also counts as a chosen target type for equipment and skill access."
        ),
    )
    from_category = models.CharField(
        max_length=50,
        choices=FighterCategoryChoices.choices,
        help_text="The fighter category this promotion is offered to.",
    )
    source_fighter = models.ForeignKey(
        "ContentFighter",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="promotion_paths_from",
        help_text=(
            "If set, this path is offered only to fighters of this specific type "
            "(house-specific paths, e.g. Orlock Wrecker). Leave blank for generic "
            "category-based paths."
        ),
    )
    to_category = models.CharField(
        max_length=50,
        choices=FighterCategoryChoices.choices,
        blank=True,
        help_text=(
            "The category the fighter is relabelled to. Required for category relabels; "
            "optional for type changes, where the chosen target type's category applies."
        ),
    )
    targets = models.ManyToManyField(
        "ContentFighter",
        blank=True,
        related_name="promotion_paths_to",
        help_text=(
            "Target types the player may choose between on a type change (e.g. Forge Boss "
            "or Stimmer). Leave empty if the target is resolved later."
        ),
    )
    rank = models.PositiveIntegerField(
        default=0,
        help_text=(
            "Ordinal seniority of the promotion. On reversal a fighter falls back to the "
            "highest-ranked promotion it still holds (e.g. Champion=2 outranks Specialist=1)."
        ),
    )
    xp_cost = models.PositiveIntegerField(help_text="XP spent to take this promotion.")
    cost_increase = models.IntegerField(
        default=0, help_text="Flat fighter-rating increase applied by this promotion."
    )
    rolls = models.JSONField(
        default=list,
        blank=True,
        help_text="2d6 totals that offer this promotion in the roll-driven flow, e.g. [2, 12].",
    )
    grants_skill = models.CharField(
        max_length=32,
        choices=GRANTS_SKILL_CHOICES,
        default="primary_random",
        help_text="Which skill (if any) the fighter gains alongside the promotion.",
    )
    advancements_threshold = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=(
            "Advancements the fighter should have before promotion (e.g. 5 for most "
            "Prospects). Guidance for the UI — warn, don't block."
        ),
    )
    timing = models.CharField(
        max_length=16,
        choices=Timing.choices,
        default=Timing.POST_BATTLE,
        help_text="When the rules say this promotion happens. Informational.",
    )
    restricted_to_houses = models.ManyToManyField(
        "ContentHouse",
        blank=True,
        related_name="promotion_paths",
        help_text="If set, only fighters in these houses are offered this promotion.",
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Promotion path"
        verbose_name_plural = "Promotion paths"
        ordering = ["rank", "name"]

    def __str__(self):
        to_part = self.to_category or "chosen type"
        return f"{self.name} ({self.from_category} → {to_part})"

    def clean(self):
        super().clean()
        if self.kind == self.Kind.RELABEL:
            if not self.to_category:
                raise ValidationError(
                    {"to_category": "A category relabel must name a target category."}
                )
            if self.from_category and self.from_category == self.to_category:
                raise ValidationError(
                    {"to_category": "A promotion must change the fighter's category."}
                )
        if self.to_category and self.to_category not in PROMOTION_TARGET_CATEGORIES:
            allowed = ", ".join(c.label for c in PROMOTION_TARGET_CATEGORIES)
            raise ValidationError(
                {"to_category": f"Promotion target must be one of: {allowed}."}
            )
        self._clean_rolls()

    def _clean_rolls(self):
        """Validate ``rolls`` as a duplicate-free list of 2d6 totals (admin-authored JSON)."""
        if not self.rolls:
            return
        if not isinstance(self.rolls, list) or not all(
            isinstance(r, int) and not isinstance(r, bool) and 2 <= r <= 12
            for r in self.rolls
        ):
            raise ValidationError(
                {"rolls": "Rolls must be a list of whole numbers between 2 and 12."}
            )
        if len(set(self.rolls)) != len(self.rolls):
            raise ValidationError({"rolls": "Rolls must not contain duplicates."})

    @staticmethod
    def clean_target(fighter) -> None:
        """Validate a candidate target fighter for a type change.

        M2M rows can't be validated in ``clean()`` on unsaved instances, so the admin form
        and the Phase 2 apply flow call this per target instead. A promotion must never turn
        a fighter into the stash or a vehicle.
        """
        if fighter.is_stash:
            raise ValidationError("A promotion target cannot be a stash fighter type.")
        if fighter.is_vehicle:
            raise ValidationError("A promotion target cannot be a vehicle type.")

    def is_available_to_fighter(self, list_fighter) -> bool:
        """Content-level availability gate: source match + house restriction.

        This is *only* the content gate. Flow-level eligibility (already promoted, enough XP,
        advancement threshold, etc.) is applied by the advancement flow in Phase 2.
        """
        if self.source_fighter_id is not None:
            if list_fighter.content_fighter_id != self.source_fighter_id:
                return False
        elif list_fighter.get_category() != self.from_category:
            return False
        houses = list(self.restricted_to_houses.all())
        if houses and list_fighter.list.content_house not in houses:
            return False
        return True


# Canonical values for the two promotions previously hardcoded in
# ``AdvancementTypeForm.ADVANCEMENT_CONFIGS``. This constant is the LIVE source of truth going
# forward and is consumed by the invariant tests (A4/G6), which assert it still matches the
# hardcoded configs — that agreement is what makes the Phase 2 refactor cost-neutral. The
# Phase 1 data migration (0181) deliberately carries its own frozen inline snapshot of these
# values instead of importing this constant, so editing it later (e.g. adding paths in Phase 2)
# cannot change what that historical migration seeds.
# ``_legacy_choice`` maps each row to the hardcoded key it replaces, for the invariant test.
DEFAULT_PROMOTIONS = [
    {
        "name": "Promote to Specialist",
        "kind": ContentPromotionPath.Kind.RELABEL,
        "from_category": FighterCategoryChoices.GANGER,
        "to_category": FighterCategoryChoices.SPECIALIST,
        "rank": 1,
        "xp_cost": 6,
        "cost_increase": 20,
        "rolls": [2, 12],
        "grants_skill": "primary_random",
        "timing": ContentPromotionPath.Timing.POST_BATTLE,
        "_legacy_choice": "skill_promote_specialist",
    },
    {
        "name": "Promote to Champion",
        "kind": ContentPromotionPath.Kind.TYPE_CHANGE,
        "from_category": FighterCategoryChoices.SPECIALIST,
        "to_category": FighterCategoryChoices.CHAMPION,
        "rank": 2,
        "xp_cost": 12,
        "cost_increase": 40,
        "rolls": [],
        "grants_skill": "primary_random",
        "timing": ContentPromotionPath.Timing.POST_BATTLE,
        "_legacy_choice": "skill_promote_champion",
    },
]

_SEED_DEFAULT_FIELDS = (
    "name",
    "kind",
    "rank",
    "xp_cost",
    "cost_increase",
    "rolls",
    "grants_skill",
    "timing",
)


def seed_default_promotions(model):
    """Create/refresh the default promotion paths on ``model``.

    Used by tests (the data migration carries its own frozen snapshot — see the note on
    ``DEFAULT_PROMOTIONS``). Idempotent — keyed on ``(from_category, to_category)`` so
    re-running never duplicates. Excludes the ``_legacy_choice`` bookkeeping key.
    """
    for entry in DEFAULT_PROMOTIONS:
        model.objects.update_or_create(
            from_category=entry["from_category"],
            to_category=entry["to_category"],
            defaults={field: entry[field] for field in _SEED_DEFAULT_FIELDS},
        )
