import logging
from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import models
from simple_history.models import HistoricalRecords

from gyrinx.base_models import AppBase
from n23.content.models import (
    ContentFighter,
    ContentModStatApplyMixin,
    ContentPromotionPath,
    ContentSkill,
)
from n23.core.models.list.assignment import ListFighterEquipmentAssignment
from n23.core.models.list.fighter import ListFighter
from n23.models import FighterCategoryChoices

logger = logging.getLogger(__name__)
pylist = list

# Choice-key prefix for data-driven promotions: "promotion_{ContentPromotionPath.id}".
PROMOTION_CHOICE_PREFIX = "promotion_"


@dataclass(frozen=True)
class ResolvedPromotion:
    """What a promotion advancement_choice means, independent of its era.

    New-era choices ("promotion_{uuid}") resolve from a ContentPromotionPath row; the two
    legacy hardcoded strings resolve from a static map so historical rows keep applying and
    reversing correctly even if the seeded content rows are edited or removed.
    ``target`` is the fighter type the fighter counts as after a type-change promotion
    (the chosen target, or the path's sole target) — None for pure relabels and legacy rows.
    """

    to_category: str
    rank: int
    path: ContentPromotionPath | None = None
    target: ContentFighter | None = None


# The two promotion choices that were hardcoded before promotions became content-driven.
# Stored ListFighterAdvancement rows keep these strings forever (never rewritten); the map
# preserves their outcome (target category) and seniority (Champion outranks Specialist).
LEGACY_PROMOTION_CHOICES = {
    "skill_promote_specialist": ResolvedPromotion(
        to_category=FighterCategoryChoices.SPECIALIST, rank=1
    ),
    "skill_promote_champion": ResolvedPromotion(
        to_category=FighterCategoryChoices.CHAMPION, rank=2
    ),
}


def resolve_promotion_choice(choice: str | None) -> ResolvedPromotion | None:
    """Resolve an advancement_choice string to its promotion meaning, if it is one.

    Returns None for non-promotion choices, and for new-era choices whose path row no
    longer exists (deletion is blocked by PROTECT while advancements reference it, so
    that only happens for never-applied choices).
    """
    if not choice:
        return None
    if choice in LEGACY_PROMOTION_CHOICES:
        return LEGACY_PROMOTION_CHOICES[choice]
    if choice.startswith(PROMOTION_CHOICE_PREFIX):
        path = ContentPromotionPath.objects.filter(
            id=choice.removeprefix(PROMOTION_CHOICE_PREFIX)
        ).first()
        if path is None:
            return None
        return ResolvedPromotion(
            to_category=path.effective_to_category(), rank=path.rank, path=path
        )
    return None


class AdvancementStatMod(ContentModStatApplyMixin):
    """
    Virtual mod object that wraps a stat advancement.

    This allows stat advancements to be applied via the mod system rather than
    mutating fighter override fields. The mod is computed on-the-fly from the
    advancement data.

    Stat advancements always improve the stat by 1.
    """

    def __init__(self, stat_increased: str):
        self.stat = stat_increased
        self.mode = "improve"  # Advancements always improve stats
        self.value = "1"  # Always by 1

    def __repr__(self):
        return (
            f"<AdvancementStatMod stat={self.stat} mode={self.mode} value={self.value}>"
        )


class ListFighterAdvancement(AppBase):
    """Track advancements purchased by fighters using XP in campaign mode."""

    # Types of advancements
    ADVANCEMENT_STAT = "stat"
    ADVANCEMENT_SKILL = "skill"
    ADVANCEMENT_EQUIPMENT = "equipment"
    ADVANCEMENT_PROMOTION = "promotion"
    ADVANCEMENT_OTHER = "other"

    ADVANCEMENT_TYPE_CHOICES = [
        (ADVANCEMENT_STAT, "Characteristic Increase"),
        (ADVANCEMENT_SKILL, "New Skill"),
        (ADVANCEMENT_EQUIPMENT, "New Equipment"),
        (ADVANCEMENT_PROMOTION, "Promotion"),
        (ADVANCEMENT_OTHER, "Other"),
    ]

    fighter = models.ForeignKey(
        ListFighter,
        on_delete=models.CASCADE,
        related_name="advancements",
        help_text="The fighter who purchased this advancement.",
    )

    advancement_type = models.CharField(
        max_length=10,
        choices=ADVANCEMENT_TYPE_CHOICES,
        help_text="The type of advancement purchased.",
    )

    advancement_choice = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="The option selected in the advancement form",
    )

    # For stat advancements
    stat_increased = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        # Choices will be dynamically generated in the form
        help_text="For stat increases, which characteristic was improved.",
    )

    # For skill advancements
    skill = models.ForeignKey(
        ContentSkill,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="For skill advancements, which skill was gained.",
    )

    # For equipment advancements
    equipment_assignment = models.ForeignKey(
        "content.ContentAdvancementAssignment",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="For equipment advancements, which assignment configuration was selected.",
    )

    # For promotion advancements (data-driven era; legacy rows carry only the
    # advancement_choice string). PROTECT: a path row can't be deleted from under the
    # advancements that were purchased through it.
    promotion_path = models.ForeignKey(
        "content.ContentPromotionPath",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="advancements",
        help_text="For promotion advancements, which promotion path was taken.",
    )

    promotion_target = models.ForeignKey(
        "content.ContentFighter",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="promotion_advancements",
        help_text=(
            "For type-change promotions with a choice of targets, which fighter type "
            "was chosen (e.g. Forge Boss vs Stimmer)."
        ),
    )

    # For other advancements
    description = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="For 'other' advancements, a free text description.",
    )

    xp_cost = models.PositiveIntegerField(
        help_text="The XP cost of this advancement.",
    )

    cost_increase = models.IntegerField(
        default=0,
        help_text="The increase in fighter cost from this advancement.",
    )

    # A permanent marker for advancements predating the mod system, not a
    # migration in progress. Nineteen rows across eleven gangs still carry
    # False; everything since #1861 Track B is True and nothing sets it False.
    #
    # They are deliberately left alone. Each one's improvement is already
    # inside a plain stat override on its fighter, so switching them on would
    # apply it a second time; deleting them would take 295 credits of gang
    # rating with them. Seven of the twelve in live gangs hold override values
    # no code path produces (a bare "5" against a "4+" base, in one case just
    # "+"), so they look hand-typed — "correcting" those would be overruling
    # what a player chose rather than fixing a bug. See #1861.
    uses_mod_system = models.BooleanField(
        default=True,
        help_text=(
            "If True (all new advancements), a stat advancement is applied by "
            "the mod system, computed when the card is rendered. If False, the "
            "advancement predates that system: it applies nothing, and the "
            "improvement it bought is held as a stat override on the fighter."
        ),
    )

    # Link to campaign action if dice were rolled
    campaign_action = models.OneToOneField(
        "CampaignAction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="advancement",
        help_text="The campaign action recording the dice roll for this advancement.",
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ["fighter", "created"]
        verbose_name = "Fighter Advancement"
        verbose_name_plural = "Fighter Advancements"

    def __str__(self):
        if self.advancement_type == self.ADVANCEMENT_STAT:
            return f"{self.fighter.name} - {self.get_stat_increased_display()}"
        elif self.advancement_type == self.ADVANCEMENT_SKILL and self.skill:
            return f"{self.fighter.name} - {self.skill.name}"
        elif self.advancement_type == self.ADVANCEMENT_EQUIPMENT:
            if self.equipment_assignment:
                return f"{self.fighter.name} - {str(self.equipment_assignment)}"
        elif self.advancement_type == self.ADVANCEMENT_PROMOTION:
            return f"{self.fighter.name} - {self.promotion_display}"
        elif self.advancement_type == self.ADVANCEMENT_OTHER and self.description:
            return f"{self.fighter.name} - {self.description}"
        return f"{self.fighter.name} - Advancement"

    def resolved_promotion(self) -> ResolvedPromotion | None:
        """Resolve this advancement's promotion meaning, if it is one (either era).

        The type-change target is the stored chosen target, or the path's sole target
        for single-target type changes; None for pure relabels and legacy rows.
        """
        if self.promotion_path is not None:
            path = self.promotion_path
            target = self.promotion_target
            if target is None and path.kind == ContentPromotionPath.Kind.TYPE_CHANGE:
                # Only infer the target when the path has exactly one — a multi-target
                # path with no stored choice must not resolve to an arbitrary pick.
                # (The wizard always stores the choice; this guards programmatic writes.)
                # resolve_targets covers dynamically-targeted paths too (e.g. a house
                # with a single Leader type under 'Nominate as leader').
                targets = pylist(path.resolve_targets(self.fighter))
                if len(targets) == 1:
                    target = targets[0]
            return ResolvedPromotion(
                to_category=path.effective_to_category(target),
                rank=path.rank,
                path=path,
                target=target,
            )
        return resolve_promotion_choice(self.advancement_choice)

    @property
    def promotion_display(self) -> str:
        """Human-readable label for a promotion advancement."""
        if self.promotion_path:
            base = self.promotion_path.name
            if self.promotion_target:
                base = f"{base}: {self.promotion_target.type}"
        else:
            resolved = resolve_promotion_choice(self.advancement_choice)
            base = (
                f"Promote to {FighterCategoryChoices[resolved.to_category].label}"
                if resolved and resolved.to_category
                else "Promotion"
            )
        if self.skill:
            return f"{base} ({self.skill.name})"
        return base

    def get_stat_increased_display(self):
        # Import here to avoid circular imports
        from n23.core.forms.advancement import AdvancementTypeForm

        return AdvancementTypeForm.all_stat_choices().get(
            f"stat_{self.stat_increased}", "Unknown"
        )

    @property
    def display_description(self):
        """Return a human-readable description of what this advancement provides."""
        if self.advancement_type == self.ADVANCEMENT_STAT:
            return self.get_stat_increased_display()
        elif self.advancement_type == self.ADVANCEMENT_SKILL and self.skill:
            return self.skill.name
        elif self.advancement_type == self.ADVANCEMENT_PROMOTION:
            return self.promotion_display
        elif self.advancement_type in (
            self.ADVANCEMENT_OTHER,
            self.ADVANCEMENT_EQUIPMENT,
        ):
            if self.description:
                return self.description
            else:
                return str(self.equipment_assignment)
        return "Advancement"

    def apply_advancement(self):
        """Apply this advancement to the fighter."""
        if self.advancement_type == self.ADVANCEMENT_STAT and self.stat_increased:
            # Nothing to write: the stat improvement is computed from the mod
            # system at display time. The legacy branch that mutated a
            # `<stat>_override` column is gone with #1861 Track C3 — those
            # columns are no longer read, and `uses_mod_system` defaults to
            # True, so nothing has taken that path since Track B.
            pass
        elif self.advancement_type == self.ADVANCEMENT_SKILL and self.skill:
            # Add skill to fighter
            self.fighter.skills.add(self.skill)
        elif self.advancement_type == self.ADVANCEMENT_EQUIPMENT:
            if self.equipment_assignment:
                # Create equipment assignment with upgrades from advancement assignment
                assignment = ListFighterEquipmentAssignment.objects.create(
                    list_fighter=self.fighter,
                    content_equipment=self.equipment_assignment.equipment,
                )
                # Add the upgrades from the advancement assignment
                assignment.upgrades_field.set(
                    self.equipment_assignment.upgrades_field.all()
                )

                # Acquisition writes the receipt (#1826 Phase 7).
                from n23.core.cost.pinning import pin_assignment

                pin_assignment(assignment)
                # Recalculate cached values now that upgrades are added
                assignment.facts_from_db(update=True)
        elif self.advancement_type == self.ADVANCEMENT_PROMOTION:
            # Promotions may bundle a skill (e.g. the core Ganger→Specialist path grants a
            # random Primary skill); house Juve/Prospect promotions typically grant none.
            if self.skill:
                self.fighter.skills.add(self.skill)
        elif self.advancement_type == self.ADVANCEMENT_OTHER:
            # For "other" advancements, nothing specific to apply
            # The description is just stored for display purposes
            pass

        # If this is a promotion (either era: promotion_path row, "promotion_{id}" choice,
        # or a legacy hardcoded string), relabel the fighter's category and — for type
        # changes — point the fighter at the type it now counts as for equipment, skill,
        # and special-rule access. Per the rules, promotion never changes statline or
        # base cost — cost impact is only the flat cost_increase summed with all other
        # advancements.
        resolved = self.resolved_promotion()
        if resolved:
            changed = False
            if resolved.target is not None:
                # Guardrail: a promotion must never turn a fighter into a stash/vehicle.
                ContentPromotionPath.clean_target(resolved.target)
                self.fighter.promoted_content_fighter = resolved.target
                changed = True
                # Persist the resolved target on the row (single-target paths skip the
                # chooser, so nothing stored it yet). Pins what this fighter counts as
                # to what was true at purchase — an admin later adding a second target
                # to the path must not rewrite existing fighters' history.
                if self.promotion_target_id is None:
                    self.promotion_target = resolved.target
                    self.save()
            if resolved.to_category:
                self.fighter.category_override = resolved.to_category
                changed = True
            if changed:
                self.fighter.save()

        # Deduct XP cost from fighter
        self.fighter.xp_current -= self.xp_cost
        self.fighter.save()

    def clean(self):
        """Validate the advancement."""
        if self.advancement_type == self.ADVANCEMENT_STAT and not self.stat_increased:
            raise ValidationError("Stat advancement requires a stat to be selected.")
        if self.advancement_type == self.ADVANCEMENT_SKILL and not self.skill:
            raise ValidationError("Skill advancement requires a skill to be selected.")
        if (
            self.advancement_type == self.ADVANCEMENT_EQUIPMENT
            and not self.equipment_assignment
        ):
            raise ValidationError(
                "Equipment advancement requires equipment assignment to be selected."
            )
        if self.advancement_type == self.ADVANCEMENT_OTHER and not self.description:
            raise ValidationError("Other advancement requires a description.")

        # Ensure only appropriate fields are set
        if self.advancement_type == self.ADVANCEMENT_STAT and (
            self.skill or self.equipment_assignment
        ):
            raise ValidationError(
                "Stat advancement should not have skill or equipment selected."
            )
        if self.advancement_type == self.ADVANCEMENT_SKILL and (
            self.stat_increased or self.equipment_assignment
        ):
            raise ValidationError(
                "Skill advancement should not have stat or equipment selected."
            )
        if self.advancement_type == self.ADVANCEMENT_EQUIPMENT and (
            self.stat_increased or self.skill
        ):
            raise ValidationError(
                "Equipment advancement should not have stat or skill selected."
            )
        if self.advancement_type == self.ADVANCEMENT_PROMOTION and (
            self.stat_increased or self.equipment_assignment
        ):
            # A promotion may carry a skill (bundled random Primary) but never a stat or
            # equipment selection.
            raise ValidationError(
                "Promotion advancement should not have stat or equipment selected."
            )
        if self.advancement_type == self.ADVANCEMENT_OTHER and (
            self.stat_increased or self.skill or self.equipment_assignment
        ):
            raise ValidationError(
                "Other advancement should not have stat, skill, or equipment selected."
            )
