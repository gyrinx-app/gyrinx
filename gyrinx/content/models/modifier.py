"""
Modifier models for content data.

This module contains:
- ContentMod: Base polymorphic modifier class
- ContentModStatApplyMixin: Shared logic for stat modifications
- ContentModStat: Weapon stat modifiers
- ContentModFighterStat: Fighter stat modifiers
- ContentModTrait: Weapon trait modifiers
- ContentModFighterRule: Fighter rule modifiers
- ContentModFighterSkill: Fighter skill modifiers
- ContentModSkillTreeAccess: Skill tree access modifiers
- ContentModPsykerDisciplineAccess: Psyker discipline access modifiers
"""

from typing import Optional

from django.core.exceptions import ValidationError
from django.db import models
from polymorphic.models import PolymorphicModel
from simple_history.models import HistoricalRecords

from gyrinx.core.models.util import ModContext
from gyrinx.tracker import track

from .base import Content


class ContentMod(PolymorphicModel, Content):
    """
    Base class for all modifications.
    """

    help_text = "Base class for all modifications."
    history = HistoricalRecords()

    def __str__(self):
        return "Base Modification"

    class Meta:
        verbose_name = "Modification"
        verbose_name_plural = "Modifications"


class ContentModStatApplyMixin:
    inverted_stats = [
        "ammo",
        "armour_piercing",
        "weapon_skill",
        "ballistic_skill",
        "intelligence",
        "leadership",
        "cool",
        "willpower",
        "initiative",
        "handling",
        "save",
    ]

    inch_stats = ["range_short", "range_long", "movement"]

    modifier_stats = ["accuracy_short", "accuracy_long", "armour_piercing"]

    target_roll_stats = [
        "ammo",
        "weapon_skill",
        "ballistic_skill",
        "intelligence",
        "leadership",
        "cool",
        "willpower",
        "initiative",
        "handling",
        "save",
    ]

    def _get_stat_configuration(self, all_stats: Optional[dict[str, dict]] = None):
        """
        Get stat configuration from ContentStat or fallback to hardcoded values.
        Returns a tuple of (is_inverted, is_inches, is_modifier, is_target).
        """
        from .statline import ContentStat

        # all_stats is an optimisation to reduce the N+1 query problem from
        # fetching ContentStat objects individually
        if all_stats:
            content_stat = all_stats.get(self.stat, {})
            return (
                content_stat.get("is_inverted", False),
                content_stat.get("is_inches", False),
                content_stat.get("is_modifier", False),
                content_stat.get("is_target", False),
            )
        # Check if we have a ContentStat object with the new fields
        try:
            content_stat = ContentStat.objects.get(field_name=self.stat)
            if content_stat:
                # Use ContentStat fields if available
                return (
                    content_stat.is_inverted,
                    content_stat.is_inches,
                    content_stat.is_modifier,
                    content_stat.is_target,
                )
        except ContentStat.DoesNotExist:
            # Track that we're using fallback values
            track(
                "stat_config_fallback_used",
                stat_name=self.stat,
                model_class=self.__class__.__name__,
            )
            pass

        # Fallback to hardcoded values for backwards compatibility
        return (
            self.stat in self.inverted_stats,
            self.stat in self.inch_stats,
            self.stat in self.modifier_stats,
            self.stat in self.target_roll_stats,
        )

    def apply(self, input_value: str, mod_ctx: Optional[ModContext] = None) -> str:
        """
        Apply the modification to a given value.
        """

        if self.mode == "set":
            return self.value

        # Get stat configuration
        is_inverted_stat, is_inch_stat, is_modifier_stat, is_target_stat = (
            self._get_stat_configuration(
                all_stats=mod_ctx.all_stats if mod_ctx else None
            )
        )

        direction = 1 if self.mode == "improve" else -1
        # For some stats, we need to reverse the direction
        # e.g. if the stat is a target roll value
        if is_inverted_stat:
            direction = -direction

        # Stats can be:
        #   - (meaning 0)
        #   X" (meaning X inches) - Rng
        #   X (meaning X) - Str, D
        #   S (meaning fighter Str) - Str
        #   S+X (meaning fighter Str+X) - Str
        #   +X (meaning add X to roll) - Acc and Ap
        #   X+ (meaning target X on roll) - Am
        current_value = input_value.strip()
        join = None
        # A developer has a problem. She uses a regex... Now she has two problems.
        if current_value in ["-", ""]:
            current_value = 0
        elif current_value.endswith('"'):
            # Inches
            current_value = int(current_value[:-1])
        elif current_value.endswith("+"):
            # Target roll
            current_value = int(current_value[:-1])
        elif current_value.startswith("+"):
            # Modifier
            current_value = int(current_value[1:])
        elif current_value == "S":
            # Stat-linked: e.g. S
            current_value = 0
            join = ["S"]
        elif "+" in current_value:
            # Stat-linked: e.g. S+1
            split = current_value.split("+")
            join = split[:-1]
            current_value = int(split[-1])
        elif "-" in current_value:
            # Stat-linked: e.g. S-1
            split = current_value.split("-")
            join = split[:-1]
            # Note! Negative
            current_value = -int(split[-1])
        else:
            current_value = int(current_value)

        # TODO: We should validate that the value is number in improve/worsen mode
        mod_value = int(self.value.strip()) * direction
        output_value = current_value + mod_value
        output_str = str(output_value)

        if join:
            # Stat-linked: e.g. S+1
            # The else case handles negative case
            if output_str == "0":
                return f"{''.join(join)}"
            sign = "+" if output_value > 0 else ""
            return f"{''.join(join)}{sign}{output_value}"
        elif output_str == "0":
            return ""
        elif is_inch_stat:
            # Inches
            return f'{output_str}"'
        elif is_modifier_stat:
            # Modifier
            if output_value > 0:
                return f"+{output_str}"
            return f"{output_str}"
        elif is_target_stat:
            # Target roll
            return f"{output_str}+"

        return output_str


class ContentModStat(ContentMod, ContentModStatApplyMixin):
    """
    Weapon stat modifier
    """

    help_text = "A modification to a specific value in a weapon statline"
    stat = models.CharField(
        max_length=50,
        choices=[
            ("strength", "Strength"),
            ("range_short", "Range (Short)"),
            ("range_long", "Range (Long)"),
            ("accuracy_short", "Accuracy (Short)"),
            ("accuracy_long", "Accuracy (Long)"),
            ("armour_piercing", "Armour Piercing"),
            ("damage", "Damage"),
            ("ammo", "Ammo"),
        ],
    )
    mode = models.CharField(
        max_length=10,
        choices=[("improve", "Improve"), ("worsen", "Worsen"), ("set", "Set")],
    )
    value = models.CharField(max_length=5)

    def __str__(self):
        mode_choices = dict(self._meta.get_field("mode").choices)
        stat_choices = dict(self._meta.get_field("stat").choices)
        return f"{mode_choices[self.mode]} weapon {stat_choices[self.stat]} by {self.value}"

    class Meta:
        verbose_name = "Weapon Stat Modifier"
        verbose_name_plural = "Weapon Stat Modifiers"
        ordering = ["stat"]


class ContentModFighterStat(ContentMod, ContentModStatApplyMixin):
    """
    Fighter stat modifier.

    Note: The choices for the `stat` field are auto-generated dynamically in the admin form
    from ContentStat objects to ensure consistency across the system.
    """

    help_text = "A modification to a specific value in a fighter statline"
    stat = models.CharField(
        max_length=50,
        # Choices are dynamically generated in ContentModFighterStatAdminForm
        # from ContentStat objects to ensure all defined stats are available
    )
    mode = models.CharField(
        max_length=10,
        choices=[("improve", "Improve"), ("worsen", "Worsen"), ("set", "Set")],
    )
    value = models.CharField(max_length=5)

    def __str__(self):
        from .statline import ContentStat

        mode_choices = dict(self._meta.get_field("mode").choices)
        stat = ContentStat.objects.filter(field_name=self.stat).first()
        verb = "to" if self.mode == "set" else "by"
        return f"{mode_choices[self.mode]} fighter {stat.full_name if stat else f'`{self.stat}`'} {verb} {self.value}"

    class Meta:
        verbose_name = "Fighter Stat Modifier"
        verbose_name_plural = "Fighter Stat Modifiers"
        ordering = ["stat"]

    def clean(self):
        # Check that there isn't a duplicate of this already
        duplicate = ContentModFighterStat.objects.filter(
            stat=self.stat, mode=self.mode, value=self.value
        ).exists()

        if duplicate:
            raise ValidationError("This fighter stat modifier already exists.")


class ContentModTrait(ContentMod):
    """
    Trait modifier
    """

    help_text = "A modification to a weapon trait"
    trait = models.ForeignKey(
        "ContentWeaponTrait",
        on_delete=models.CASCADE,
        related_name="modified_by",
        null=False,
        blank=False,
    )
    mode = models.CharField(
        max_length=255,
        choices=[("add", "Add"), ("remove", "Remove")],
    )

    def __str__(self):
        choices = dict(self._meta.get_field("mode").choices)
        return f"{choices[self.mode]} {self.trait}"

    class Meta:
        verbose_name = "Weapon Trait Modifier"
        verbose_name_plural = "Weapon Trait Modifiers"
        ordering = ["trait__name", "mode"]


class ContentModFighterRule(ContentMod):
    """
    Rule modifier
    """

    help_text = "A modification to a fighter rule"
    rule = models.ForeignKey(
        "ContentRule",
        on_delete=models.CASCADE,
        related_name="modified_by",
        null=False,
        blank=False,
    )
    mode = models.CharField(
        max_length=255,
        choices=[("add", "Add"), ("remove", "Remove")],
    )

    def __str__(self):
        choices = dict(self._meta.get_field("mode").choices)
        return f"{choices[self.mode]} rule {self.rule}"

    class Meta:
        verbose_name = "Fighter Rule Modifier"
        verbose_name_plural = "Fighter Rule Modifiers"
        ordering = ["rule__name", "mode"]


class ContentModFighterSkill(ContentMod):
    """
    Skill modifier
    """

    help_text = "A modification to a fighter skills"
    skill = models.ForeignKey(
        "ContentSkill",
        on_delete=models.CASCADE,
        related_name="modified_by",
        null=False,
        blank=False,
    )
    mode = models.CharField(
        max_length=255,
        choices=[("add", "Add"), ("remove", "Remove")],
    )

    def __str__(self):
        choices = dict(self._meta.get_field("mode").choices)
        return f"{choices[self.mode]} skill {self.skill}"

    class Meta:
        verbose_name = "Fighter Skill Modifier"
        verbose_name_plural = "Fighter Skill Modifiers"
        ordering = ["skill__name", "mode"]


class ContentModSkillTreeAccess(ContentMod):
    """
    Modifies fighter skill tree access (primary/secondary)
    """

    help_text = "A modification to fighter skill tree access"

    skill_category = models.ForeignKey(
        "ContentSkillCategory",
        on_delete=models.CASCADE,
        related_name="modified_by_skill_tree_access",
        null=False,
        blank=False,
    )

    mode = models.CharField(
        max_length=20,
        choices=[
            ("add_primary", "Add as Primary"),
            ("add_secondary", "Add as Secondary"),
            ("remove_primary", "Remove from Primary"),
            ("remove_secondary", "Remove from Secondary"),
            ("disable", "Disable Access"),
        ],
    )

    def __str__(self):
        choices = dict(self._meta.get_field("mode").choices)
        return f"{choices[self.mode]} - {self.skill_category}"

    class Meta:
        verbose_name = "Skill Tree Access Modifier"
        verbose_name_plural = "Skill Tree Access Modifiers"
        ordering = ["skill_category__name", "mode"]


class ContentModPsykerDisciplineAccess(ContentMod):
    """
    Modifies fighter psyker discipline access.
    Allows adding or removing psyker discipline access to fighters.
    """

    help_text = "A modification to fighter psyker discipline access"

    discipline = models.ForeignKey(
        "ContentPsykerDiscipline",
        on_delete=models.CASCADE,
        related_name="modified_by_psyker_discipline_access",
        null=False,
        blank=False,
    )

    mode = models.CharField(
        max_length=20,
        choices=[
            ("add", "Add Discipline"),
            ("remove", "Remove Discipline"),
        ],
    )

    def __str__(self):
        choices = dict(self._meta.get_field("mode").choices)
        return f"{choices[self.mode]} - {self.discipline}"

    class Meta:
        verbose_name = "Psyker Discipline Access Modifier"
        verbose_name_plural = "Psyker Discipline Access Modifiers"
        ordering = ["discipline__name", "mode"]
