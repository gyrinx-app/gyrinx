"""
Promotion path content models.

Content-driven replacement for the promotion advancement configs that were hardcoded in
``gyrinx/core/forms/advancement.py`` (``skill_promote_specialist`` /
``skill_promote_champion``). See ``.claude/notes/promotions-epic-design.md`` for the epic.

Phase 1 (#1596 / #1467 epic) adds ``ContentPromotionCategoryPath`` — the *category-relabel*
mechanism (e.g. Ganger → Specialist), which sets a fighter's ``category_override`` without
changing its ``content_fighter``. Wiring it into the advancement flow is Phase 2; the
fighter-*type*-change mechanism for #1467 arrives in a later phase.
"""

from django.core.exceptions import ValidationError
from django.db import models
from simple_history.models import HistoricalRecords

from gyrinx.models import FighterCategoryChoices

from .base import Content

# Categories a promotion may target. Must stay in sync with
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


class ContentPromotionCategoryPath(Content):
    """A content-authored *category-relabel* promotion (e.g. "Promote to Specialist").

    Applying it sets the fighter's ``category_override`` to ``to_category`` — a label change
    only. The fighter keeps its ``content_fighter`` (statline, base cost, equipment list), so
    this mechanism is inert to base cost. Generalises the two formerly-hardcoded
    ``skill_promote_*`` advancement configs.
    """

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
    from_category = models.CharField(
        max_length=50,
        choices=FighterCategoryChoices.choices,
        help_text="The fighter category this promotion is offered to.",
    )
    to_category = models.CharField(
        max_length=50,
        choices=FighterCategoryChoices.choices,
        help_text="The category the fighter is relabelled to (a promotable target).",
    )
    rank = models.PositiveIntegerField(
        default=0,
        help_text=(
            "Ordinal seniority of the target category. On reversal a fighter falls back to the "
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
    restricted_to_houses = models.ManyToManyField(
        "ContentHouse",
        blank=True,
        related_name="promotion_category_paths",
        help_text="If set, only fighters in these houses are offered this promotion.",
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Promotion (category)"
        verbose_name_plural = "Promotions (category)"
        ordering = ["rank", "name"]

    def __str__(self):
        return f"{self.name} ({self.from_category} → {self.to_category})"

    def clean(self):
        super().clean()
        if (
            self.from_category
            and self.to_category
            and self.from_category == self.to_category
        ):
            raise ValidationError(
                {"to_category": "A promotion must change the fighter's category."}
            )
        if self.to_category and self.to_category not in PROMOTION_TARGET_CATEGORIES:
            allowed = ", ".join(c.label for c in PROMOTION_TARGET_CATEGORIES)
            raise ValidationError(
                {"to_category": f"Promotion target must be one of: {allowed}."}
            )

    def is_available_to_fighter(self, list_fighter) -> bool:
        """Content-level availability gate: category match + house restriction.

        This is *only* the content gate. Flow-level eligibility (already promoted, enough XP,
        etc.) is applied by the advancement flow in Phase 2.
        """
        if list_fighter.get_category() != self.from_category:
            return False
        if self.restricted_to_houses.exists():
            if list_fighter.list.content_house not in self.restricted_to_houses.all():
                return False
        return True


# Canonical seed for the two promotions previously hardcoded in
# ``AdvancementTypeForm.ADVANCEMENT_CONFIGS``. Consumed by BOTH the Phase 1 data migration and
# the invariant test (A4/G6) — pytest runs with ``--nomigrations`` so data migrations never
# execute in the test DB; sharing one source of truth is what keeps the seed and the config
# from silently drifting apart (a drift there would make the Phase 2 refactor cost-changing).
# ``_legacy_choice`` maps each row to the hardcoded key it replaces, for the invariant test.
DEFAULT_CATEGORY_PROMOTIONS = [
    {
        "name": "Promote to Specialist",
        "from_category": FighterCategoryChoices.GANGER,
        "to_category": FighterCategoryChoices.SPECIALIST,
        "rank": 1,
        "xp_cost": 6,
        "cost_increase": 20,
        "rolls": [2, 12],
        "grants_skill": "primary_random",
        "_legacy_choice": "skill_promote_specialist",
    },
    {
        "name": "Promote to Champion",
        "from_category": FighterCategoryChoices.SPECIALIST,
        "to_category": FighterCategoryChoices.CHAMPION,
        "rank": 2,
        "xp_cost": 12,
        "cost_increase": 40,
        "rolls": [],
        "grants_skill": "primary_random",
        "_legacy_choice": "skill_promote_champion",
    },
]


def seed_category_promotions(model):
    """Create/refresh the default category promotions on ``model``.

    Shared by the Phase 1 data migration (passing ``apps.get_model(...)``) and tests (passing
    the real model). Idempotent — keyed on ``(from_category, to_category)`` so re-running never
    duplicates. Excludes the ``_legacy_choice`` bookkeeping key.
    """
    for entry in DEFAULT_CATEGORY_PROMOTIONS:
        model.objects.update_or_create(
            from_category=entry["from_category"],
            to_category=entry["to_category"],
            defaults={
                "name": entry["name"],
                "rank": entry["rank"],
                "xp_cost": entry["xp_cost"],
                "cost_increase": entry["cost_increase"],
                "rolls": entry["rolls"],
                "grants_skill": entry["grants_skill"],
            },
        )
