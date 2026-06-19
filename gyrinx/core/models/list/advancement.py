import logging

from django.core.exceptions import ValidationError
from django.db import models
from simple_history.models import HistoricalRecords

from gyrinx.content.models import (
    ContentModStatApplyMixin,
    ContentSkill,
)
from gyrinx.core.models.base import AppBase
from gyrinx.core.models.list.assignment import ListFighterEquipmentAssignment
from gyrinx.core.models.list.fighter import ListFighter
from gyrinx.models import (
    FighterCategoryChoices,
)

logger = logging.getLogger(__name__)
pylist = list


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
    ADVANCEMENT_OTHER = "other"

    ADVANCEMENT_TYPE_CHOICES = [
        (ADVANCEMENT_STAT, "Characteristic Increase"),
        (ADVANCEMENT_SKILL, "New Skill"),
        (ADVANCEMENT_EQUIPMENT, "New Equipment"),
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

    # Mod system flag - determines whether this advancement uses the mod system
    # or the legacy override fields for stat modifications.
    # New advancements default to True (use mods), existing advancements are False.
    uses_mod_system = models.BooleanField(
        default=True,
        help_text=(
            "If True, stat advancements use the mod system (computed at display time). "
            "If False, uses legacy override fields (mutates fighter state)."
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
        elif self.advancement_type == self.ADVANCEMENT_OTHER and self.description:
            return f"{self.fighter.name} - {self.description}"
        return f"{self.fighter.name} - Advancement"

    def get_stat_increased_display(self):
        # Import here to avoid circular imports
        from gyrinx.core.forms.advancement import AdvancementTypeForm

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
            # For mod-based advancements, skip setting override fields.
            # The stat improvement will be computed via the mod system at display time.
            if not self.uses_mod_system:
                # Legacy behavior: Apply stat increase via override fields
                override_field = f"{self.stat_increased}_override"

                # Get the base value from content_fighter
                base_value = getattr(self.fighter.content_fighter, self.stat_increased)

                # Get current override value, defaulting to None if not set
                current_override = getattr(self.fighter, override_field)

                # Stats are stored as strings like "3+" or "4", we need to handle numeric increases
                # For stats like WS/BS/Initiative with "+", extract the numeric part
                if base_value and "+" in base_value:
                    base_numeric = int(base_value.replace("+", ""))
                    if current_override is None:
                        # First advancement: improve by 1 (e.g., "4+" becomes "3+")
                        new_value = f"{base_numeric - 1}+"
                    else:
                        # Further advancements: extract numeric from override and improve
                        current_numeric = int(current_override.replace("+", ""))
                        new_value = f"{current_numeric - 1}+"
                else:
                    # For stats without "+" (like S, T, W), just add 1
                    try:
                        base_numeric = (
                            int(base_value.replace('"', "")) if base_value else 0
                        )
                        if current_override is None:
                            new_value = str(base_numeric + 1)
                        else:
                            current_numeric = int(current_override.replace('"', ""))
                            new_value = str(current_numeric + 1)
                    except (ValueError, TypeError):
                        # If we can't parse it as a number, just use the base value
                        new_value = base_value

                if '"' in base_value:
                    # If the base value is a distance (e.g., "4\""), ensure we keep the format
                    new_value = f'{new_value}"'

                setattr(self.fighter, override_field, new_value)
                self.fighter.save()
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
                # Recalculate cached values now that upgrades are added
                assignment.facts_from_db(update=True)
        elif self.advancement_type == self.ADVANCEMENT_OTHER:
            # For "other" advancements, nothing specific to apply
            # The description is just stored for display purposes
            pass

        # If this is a promotion, use the category override to set the fighter's category
        if (
            self.advancement_choice
            and self.advancement_choice == "skill_promote_specialist"
        ):
            self.fighter.category_override = FighterCategoryChoices.SPECIALIST
            self.fighter.save()

        if (
            self.advancement_choice
            and self.advancement_choice == "skill_promote_champion"
        ):
            self.fighter.category_override = FighterCategoryChoices.CHAMPION
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
        if self.advancement_type == self.ADVANCEMENT_OTHER and (
            self.stat_increased or self.skill or self.equipment_assignment
        ):
            raise ValidationError(
                "Other advancement should not have stat, skill, or equipment selected."
            )
