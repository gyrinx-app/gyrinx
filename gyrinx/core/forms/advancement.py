"""Forms for fighter advancement system."""

import random
from typing import Optional

from django import forms
from django.core.exceptions import ValidationError

from gyrinx.content.models import (
    ContentAdvancementEquipment,
    ContentEquipment,
    ContentSkill,
    ContentSkillCategory,
    ContentStat,
)
from gyrinx.core.models.campaign import CampaignAction
from gyrinx.forms import group_select


class AdvancementDiceChoiceForm(forms.Form):
    """Form for choosing whether to roll 2d6 for advancement."""

    roll_dice = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.HiddenInput(),
    )


class AdvancementTypeForm(forms.Form):
    """Form for choosing advancement type and costs."""

    ADVANCEMENT_CHOICES = [
        # Stat improvements
        # ... are dynamically generated based on fighter statline
        # Skill options
        ("skill_primary_random", "Random Primary Skill"),
        ("skill_primary_chosen", "Chosen Primary Skill"),
        ("skill_secondary_random", "Random Secondary Skill"),
        ("skill_secondary_chosen", "Chosen Secondary Skill"),
        ("skill_promote_specialist", "Promote to Specialist (Random Primary Skill)"),
        ("skill_any_random", "Random Skill (Any Set)"),
        # Other
        ("other", "Other"),
    ]

    ROLL_TO_COST = {
        2: 20,
        3: 20,
        4: 20,
        5: 30,
        6: 30,
        7: 10,
        8: 5,
        9: 5,
        10: 10,
        11: 10,
        12: 20,
    }

    ROLL_TO_ADVANCEMENT_CHOICE = {
        2: "skill_promote_specialist",
        3: "stat_weapon_skill",
        4: "stat_ballistic_skill",
        5: "stat_strength",
        6: "stat_toughness",
        7: "stat_movement",
        8: "stat_willpower",
        9: "stat_intelligence",
        10: "stat_leadership",
        11: "stat_cool",
        12: "skill_promote_specialist",
    }

    advancement_choice = forms.ChoiceField(
        # Note that these choices are overridden by __init__()
        choices=ADVANCEMENT_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="Select the type of advancement for this fighter.",
    )

    xp_cost = forms.IntegerField(
        min_value=0,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
        help_text="XP cost for this advancement.",
    )

    cost_increase = forms.IntegerField(
        initial=0,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
        help_text="Fighter cost increase from this advancement.",
    )

    campaign_action_id = forms.UUIDField(
        required=False,
        widget=forms.HiddenInput(),
    )

    def __init__(self, *args, fighter=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fighter = fighter

        # Dynamically generate stat choices for advancement_choice based on the fighter's statline
        all_stat_choices = AdvancementTypeForm.all_stat_choices()
        initial_advancement_choices = self.fields["advancement_choice"].choices
        additional_advancement_choices = []
        if fighter:
            statline_stats = [
                (f"stat_{stat['field_name']}", stat)
                for stat in fighter.content_fighter_statline
            ]
            additional_advancement_choices = [
                (
                    opt_val,
                    all_stat_choices.get(opt_val, stat["field_name"].title()),
                )
                for opt_val, stat in statline_stats
            ]
        else:
            additional_advancement_choices = [
                (opt_val, full_name) for opt_val, full_name in all_stat_choices.items()
            ]

        # Generate equipment advancement choices
        equipment_choices = []
        if fighter:
            # Get all available equipment advancements for this fighter
            available_equipment = ContentAdvancementEquipment.objects.select_related()

            for adv_equipment in available_equipment:
                if adv_equipment.is_available_to_fighter(fighter):
                    # Add chosen option if enabled
                    if adv_equipment.enable_chosen:
                        choice_key = f"equipment_chosen_{adv_equipment.id}"
                        choice_label = f"Chosen {adv_equipment.name}"
                        equipment_choices.append((choice_key, choice_label))

                    # Add random option if enabled
                    if adv_equipment.enable_random:
                        choice_key = f"equipment_random_{adv_equipment.id}"
                        choice_label = f"Random {adv_equipment.name}"
                        equipment_choices.append((choice_key, choice_label))

        self.fields["advancement_choice"].choices = (
            additional_advancement_choices
            + equipment_choices
            + initial_advancement_choices
        )

    @classmethod
    def all_stat_choices(cls) -> dict[str, str]:
        """
        Get a dictionary mapping stat field names to their full names.
        """
        return dict(
            (f"stat_{s['field_name']}", s["full_name"])
            for s in ContentStat.objects.all().order_by("full_name").values()
        )

    @classmethod
    def all_equipment_choices(cls) -> dict[str, str]:
        """
        Get a dictionary mapping equipment advancement choice keys to their full names.
        """
        equipment_choices = {}
        for adv_equipment in ContentAdvancementEquipment.objects.all():
            if adv_equipment.enable_chosen:
                choice_key = f"equipment_chosen_{adv_equipment.id}"
                equipment_choices[choice_key] = f"Chosen {adv_equipment.name}"
            if adv_equipment.enable_random:
                choice_key = f"equipment_random_{adv_equipment.id}"
                equipment_choices[choice_key] = f"Random {adv_equipment.name}"
        return equipment_choices

    @classmethod
    def all_advancement_choices(cls) -> dict[str, str]:
        """
        Get a dictionary mapping advancement choice keys to their full names.
        """
        return (
            cls.all_stat_choices()
            | cls.all_equipment_choices()
            | dict(cls.ADVANCEMENT_CHOICES)
        )

    def clean(self):
        cleaned_data = super().clean()
        xp_cost = cleaned_data.get("xp_cost", 0)

        if self.fighter and xp_cost > self.fighter.xp_current:
            raise ValidationError(
                f"Fighter only has {self.fighter.xp_current} XP available, "
                f"but advancement costs {xp_cost} XP."
            )

        return cleaned_data

    @classmethod
    def get_initial_for_action(
        self, campaign_action: Optional[CampaignAction] = None
    ) -> dict:
        """
        Extract initial parameters from a CampaignAction.
        """
        if not campaign_action:
            return {
                "xp_cost": 3,
                "cost_increase": 5,
                "advancement_choice": "stat_willpower",
            }

        return {
            "xp_cost": 6,
            "cost_increase": AdvancementTypeForm.ROLL_TO_COST.get(
                campaign_action.dice_total, 5
            ),
            "advancement_choice": AdvancementTypeForm.ROLL_TO_ADVANCEMENT_CHOICE.get(
                campaign_action.dice_total, "stat_willpower"
            ),
            "campaign_action_id": str(campaign_action.id),
        }


class StatSelectionForm(forms.Form):
    """Form for confirming a specific stat increase."""

    stat = forms.CharField(
        widget=forms.HiddenInput(),
    )

    confirm = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        label="Confirm this stat increase",
    )


class SkillSelectionForm(forms.Form):
    """Form for selecting a specific skill."""

    skill = forms.ModelChoiceField(
        queryset=ContentSkill.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="Select a skill for this fighter.",
    )

    def __init__(self, *args, fighter=None, skill_type=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fighter = fighter
        self.skill_type = skill_type

        if fighter and skill_type:
            # Get existing skills to exclude
            existing_skills = fighter.skills.all()

            if "primary" in skill_type:
                # Primary skills - show all skills from primary categories
                categories = fighter.get_primary_skill_categories()
                self.fields["skill"].queryset = (
                    ContentSkill.objects.filter(category__in=categories)
                    .exclude(id__in=existing_skills.values_list("id", flat=True))
                    .select_related("category")
                    .order_by("category__name", "name")
                )
            elif "secondary" in skill_type:
                # Secondary skills - show all skills from secondary categories
                categories = fighter.get_secondary_skill_categories()
                self.fields["skill"].queryset = (
                    ContentSkill.objects.filter(category__in=categories)
                    .exclude(id__in=existing_skills.values_list("id", flat=True))
                    .select_related("category")
                    .order_by("category__name", "name")
                )
            elif "any" in skill_type:
                # Any skill - show all skills
                self.fields["skill"].queryset = (
                    ContentSkill.objects.exclude(
                        id__in=existing_skills.values_list("id", flat=True)
                    )
                    .select_related("category")
                    .order_by("category__name", "name")
                )

        group_select(self, "skill", lambda x: x.category.name)


class SkillCategorySelectionForm(forms.Form):
    """Form for selecting a skill category for random skills."""

    category = forms.ModelChoiceField(
        queryset=ContentSkillCategory.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="Select a skill set from which a skill will be randomly picked.",
    )

    def __init__(self, *args, fighter=None, skill_type=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fighter = fighter
        self.skill_type = skill_type

        if fighter and skill_type:
            if "primary" in skill_type:
                categories = fighter.get_primary_skill_categories()
                # Convert set of model instances to list of IDs
                category_ids = [cat.id for cat in categories]
                self.fields["category"].queryset = ContentSkillCategory.objects.filter(
                    id__in=category_ids
                )
            elif "secondary" in skill_type:
                categories = fighter.get_secondary_skill_categories()
                # Convert set of model instances to list of IDs
                category_ids = [cat.id for cat in categories]
                self.fields["category"].queryset = ContentSkillCategory.objects.filter(
                    id__in=category_ids
                )
            else:
                # For "any" skill type, show all categories
                self.fields["category"].queryset = ContentSkillCategory.objects.all()


class RandomSkillForm(forms.Form):
    """Form for confirming a randomly selected skill."""

    skill_id = forms.IntegerField(
        widget=forms.HiddenInput(),
    )

    confirm = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        label="Accept this skill",
    )

    def __init__(
        self, *args, fighter=None, skill_type=None, category_id=None, **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.fighter = fighter
        self.skill = None  # Store the skill object for display

        if not self.is_bound and fighter and category_id:
            # Select a random skill from the specified category
            existing_skills = fighter.skills.all()

            category = ContentSkillCategory.objects.get(id=category_id)
            available_skills = ContentSkill.objects.filter(category=category).exclude(
                id__in=existing_skills.values_list("id", flat=True)
            )

            if available_skills.exists():
                random_skill = random.choice(available_skills)
                self.initial["skill_id"] = random_skill.id
                self.skill = random_skill


class OtherAdvancementForm(forms.Form):
    """Form for entering a free text advancement description."""

    description = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={"class": "form-control"}),
        help_text="Enter a short description of the advancement (e.g., 'Wyrd Powers').",
        label="Advancement Description",
    )

    def clean_description(self):
        description = self.cleaned_data.get("description", "").strip()
        if not description:
            raise ValidationError("Please enter a description for the advancement.")
        return description


class EquipmentSelectionForm(forms.Form):
    """Form for selecting a specific equipment from an advancement."""

    equipment = forms.ModelChoiceField(
        queryset=ContentEquipment.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="Select equipment for this fighter.",
    )

    def __init__(self, *args, advancement=None, **kwargs):
        super().__init__(*args, **kwargs)

        if advancement:
            # Show all equipment from the advancement
            self.fields["equipment"].queryset = advancement.equipment.all().order_by(
                "name"
            )


class RandomEquipmentForm(forms.Form):
    """Form for confirming a randomly selected equipment."""

    equipment_id = forms.IntegerField(
        widget=forms.HiddenInput(),
    )

    confirm = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        label="Accept this equipment",
    )

    def __init__(self, *args, advancement=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.equipment = None  # Store the equipment object for display

        if not self.is_bound and advancement:
            # Select a random equipment from the advancement
            available_equipment = advancement.equipment.all()

            if available_equipment.exists():
                random_equipment = random.choice(available_equipment)
                self.initial["equipment_id"] = random_equipment.id
                self.equipment = random_equipment
