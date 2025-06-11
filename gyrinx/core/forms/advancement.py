"""Forms for fighter advancement system."""

import random

from django import forms
from django.core.exceptions import ValidationError

from gyrinx.content.models import ContentSkill, ContentSkillCategory


class AdvancementDiceChoiceForm(forms.Form):
    """Form for choosing whether to roll 2d6 for advancement."""

    roll_dice = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        help_text="Check this box to roll 2d6 for your advancement.",
    )


class AdvancementTypeForm(forms.Form):
    """Form for choosing advancement type and costs."""

    ADVANCEMENT_CHOICES = [
        # Stat improvements
        ("stat_movement", "Movement"),
        ("stat_weapon_skill", "Weapon Skill"),
        ("stat_ballistic_skill", "Ballistic Skill"),
        ("stat_strength", "Strength"),
        ("stat_toughness", "Toughness"),
        ("stat_wounds", "Wounds"),
        ("stat_attacks", "Attacks"),
        ("stat_initiative", "Initiative"),
        ("stat_leadership", "Leadership"),
        ("stat_cool", "Cool"),
        ("stat_willpower", "Willpower"),
        ("stat_intelligence", "Intelligence"),
        # Skill options
        ("skill_primary_random", "Random Primary Skill"),
        ("skill_primary_chosen", "Chosen Primary Skill"),
        ("skill_secondary_random", "Random Secondary Skill"),
        ("skill_secondary_chosen", "Chosen Secondary Skill"),
        ("skill_promote_specialist", "Promote to Specialist (Random Primary Skill)"),
        ("skill_any_random", "Random Skill (Any Set)"),
    ]

    advancement_choice = forms.ChoiceField(
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

    def clean(self):
        cleaned_data = super().clean()
        xp_cost = cleaned_data.get("xp_cost", 0)

        if self.fighter and xp_cost > self.fighter.xp_current:
            raise ValidationError(
                f"Fighter only has {self.fighter.xp_current} XP available, "
                f"but advancement costs {xp_cost} XP."
            )

        return cleaned_data


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
                categories = fighter.content_fighter.primary_skill_categories.all()
                self.fields["skill"].queryset = (
                    ContentSkill.objects.filter(category__in=categories)
                    .exclude(id__in=existing_skills.values_list("id", flat=True))
                    .select_related("category")
                    .order_by("category__name", "name")
                )
            elif "secondary" in skill_type:
                # Secondary skills - show all skills from secondary categories
                categories = fighter.content_fighter.secondary_skill_categories.all()
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


class SkillCategorySelectionForm(forms.Form):
    """Form for selecting a skill category for random skills."""

    category = forms.ModelChoiceField(
        queryset=ContentSkillCategory.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="Select a skill category to roll from.",
    )

    def __init__(self, *args, fighter=None, skill_type=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fighter = fighter
        self.skill_type = skill_type

        if fighter and skill_type:
            if "primary" in skill_type:
                categories = fighter.content_fighter.primary_skill_categories.all()
            elif "secondary" in skill_type:
                categories = fighter.content_fighter.secondary_skill_categories.all()
            else:
                # For "any" skill type, show all categories
                categories = ContentSkillCategory.objects.all()

            self.fields["category"].queryset = categories


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

    # Store the skill object for display
    _skill = None

    def __init__(
        self, *args, fighter=None, skill_type=None, category_id=None, **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.fighter = fighter

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
                self._skill = random_skill
