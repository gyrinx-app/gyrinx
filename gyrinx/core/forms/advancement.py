"""Forms for fighter advancement system."""

from dataclasses import dataclass
from typing import Optional

from django import forms
from django.core.exceptions import ValidationError

from gyrinx.content.models import (
    ContentAdvancementAssignment,
    ContentAdvancementEquipment,
    ContentSkill,
    ContentSkillCategory,
    ContentStat,
)
from gyrinx.core.models.campaign import CampaignAction
from gyrinx.forms import group_select
from gyrinx.models import FighterCategoryChoices


@dataclass
class AdvancementConfig:
    """Configuration for an advancement type."""

    name: str
    display_name: str
    xp_cost: int
    cost_increase: int
    roll: Optional[int] = None  # For GANGER 2d6 rolls
    restricted_to_fighter_categories: Optional[list[str]] = None

    def is_available_to_category(self, category: str) -> bool:
        """Check if this advancement is available to a fighter category."""
        if self.restricted_to_fighter_categories is None:
            return True
        return category in self.restricted_to_fighter_categories


class AdvancementDiceChoiceForm(forms.Form):
    """Form for choosing whether to roll 2d6 for advancement."""

    roll_dice = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.HiddenInput(),
    )


class AdvancementTypeForm(forms.Form):
    """Form for choosing advancement type and costs."""

    # Define advancement configurations
    ADVANCEMENT_CONFIGS = {
        # Stat advancements
        "stat_willpower": AdvancementConfig(
            name="stat_willpower",
            display_name="Willpower",
            xp_cost=3,
            cost_increase=5,
            roll=8,
        ),
        "stat_intelligence": AdvancementConfig(
            name="stat_intelligence",
            display_name="Intelligence",
            xp_cost=3,
            cost_increase=5,
            roll=9,
        ),
        "stat_leadership": AdvancementConfig(
            name="stat_leadership",
            display_name="Leadership",
            xp_cost=4,
            cost_increase=10,
            roll=10,
        ),
        "stat_cool": AdvancementConfig(
            name="stat_cool",
            display_name="Cool",
            xp_cost=4,
            cost_increase=10,
            roll=11,
        ),
        "stat_initiative": AdvancementConfig(
            name="stat_initiative",
            display_name="Initiative",
            xp_cost=5,
            cost_increase=10,
        ),
        "stat_movement": AdvancementConfig(
            name="stat_movement",
            display_name="Movement",
            xp_cost=5,
            cost_increase=10,
            roll=7,
        ),
        "stat_weapon_skill": AdvancementConfig(
            name="stat_weapon_skill",
            display_name="Weapon Skill",
            xp_cost=6,
            cost_increase=20,
            roll=3,
        ),
        "stat_ballistic_skill": AdvancementConfig(
            name="stat_ballistic_skill",
            display_name="Ballistic Skill",
            xp_cost=6,
            cost_increase=20,
            roll=4,
        ),
        "stat_strength": AdvancementConfig(
            name="stat_strength",
            display_name="Strength",
            xp_cost=8,
            cost_increase=30,
            roll=5,
        ),
        "stat_toughness": AdvancementConfig(
            name="stat_toughness",
            display_name="Toughness",
            xp_cost=8,
            cost_increase=30,
            roll=6,
        ),
        "stat_wounds": AdvancementConfig(
            name="stat_wounds",
            display_name="Wounds",
            xp_cost=12,
            cost_increase=45,
        ),
        "stat_attacks": AdvancementConfig(
            name="stat_attacks",
            display_name="Attacks",
            xp_cost=12,
            cost_increase=45,
        ),
        # Skill advancements
        "skill_primary_random": AdvancementConfig(
            name="skill_primary_random",
            display_name="Random Primary Skill",
            xp_cost=6,
            cost_increase=20,
        ),
        "skill_primary_chosen": AdvancementConfig(
            name="skill_primary_chosen",
            display_name="Chosen Primary Skill",
            xp_cost=9,
            cost_increase=20,
        ),
        "skill_secondary_random": AdvancementConfig(
            name="skill_secondary_random",
            display_name="Random Secondary Skill",
            xp_cost=9,
            cost_increase=35,
        ),
        "skill_promote_specialist": AdvancementConfig(
            name="skill_promote_specialist",
            display_name="Promote to Specialist (Random Primary Skill)",
            xp_cost=6,
            cost_increase=20,
            roll=2,  # Also roll 12
            restricted_to_fighter_categories=[FighterCategoryChoices.GANGER],
        ),
        "skill_promote_champion": AdvancementConfig(
            name="skill_promote_champion",
            display_name="Promote to Champion",
            xp_cost=12,
            cost_increase=40,
            restricted_to_fighter_categories=[FighterCategoryChoices.SPECIALIST],
        ),
        "skill_secondary_chosen": AdvancementConfig(
            name="skill_secondary_chosen",
            display_name="Chosen Secondary Skill",
            xp_cost=12,
            cost_increase=35,
        ),
        "skill_any_random": AdvancementConfig(
            name="skill_any_random",
            display_name="Random Skill (Any Set)",
            xp_cost=15,
            cost_increase=50,
        ),
        # Other
        "other": AdvancementConfig(
            name="other",
            display_name="Other",
            xp_cost=0,  # Variable
            cost_increase=0,  # Variable
        ),
    }

    # Keep for backward compatibility
    ADVANCEMENT_CHOICES = [
        # Skill options
        ("skill_primary_random", "Random Primary Skill"),
        ("skill_primary_chosen", "Chosen Primary Skill"),
        ("skill_secondary_random", "Random Secondary Skill"),
        ("skill_secondary_chosen", "Chosen Secondary Skill"),
        ("skill_promote_specialist", "Promote to Specialist (Random Primary Skill)"),
        ("skill_promote_champion", "Promote to Champion"),
        ("skill_any_random", "Random Skill (Any Set)"),
        # Other
        ("other", "Other"),
    ]

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
        # Create instance-level copy of advancement configs to avoid modifying class-level dictionary
        # Start with a copy of the class-level configs
        self.advancement_configs = self.ADVANCEMENT_CONFIGS.copy()

        # Get fighter category for filtering
        fighter_category = fighter.get_category() if fighter else None

        # Dynamically generate stat choices for advancement_choice based on the fighter's statline
        all_stat_choices = AdvancementTypeForm.all_stat_choices()
        initial_advancement_choices = []
        additional_advancement_choices = []

        # Filter skill advancements based on fighter category
        for choice_key, choice_label in self.ADVANCEMENT_CHOICES:
            if choice_key in self.ADVANCEMENT_CONFIGS:
                config = self.ADVANCEMENT_CONFIGS[choice_key]
                if fighter_category and not config.is_available_to_category(
                    fighter_category
                ):
                    continue
            initial_advancement_choices.append((choice_key, choice_label))

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
            available_equipment = ContentAdvancementEquipment.objects.prefetch_related(
                "assignments", "restricted_to_houses"
            )

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

        # Update advancement choices with stat configs
        for stat_key in additional_advancement_choices:
            if stat_key[0] not in self.advancement_configs:
                # Create stat configs dynamically
                self.advancement_configs[stat_key[0]] = self._create_stat_config(
                    stat_key[0]
                )

        # Update advancement choices with equipment configs
        for equip_key, equip_label in equipment_choices:
            if equip_key not in self.advancement_configs:
                # Create equipment configs dynamically with actual ContentAdvancementEquipment data
                equipment_id = equip_key.split("_")[-1]  # Extract ID from key
                try:
                    adv_equipment = ContentAdvancementEquipment.objects.get(
                        id=equipment_id
                    )
                    self.advancement_configs[equip_key] = AdvancementConfig(
                        name=equip_key,
                        display_name=equip_label,
                        xp_cost=adv_equipment.xp_cost,
                        cost_increase=adv_equipment.cost_increase,
                    )
                except ContentAdvancementEquipment.DoesNotExist:
                    # Fallback if equipment not found
                    self.advancement_configs[equip_key] = self._create_equipment_config(
                        equip_key, equip_label
                    )

        self.fields["advancement_choice"].choices = (
            additional_advancement_choices
            + equipment_choices
            + initial_advancement_choices
        )

    def _create_stat_config(self, stat_key: str) -> AdvancementConfig:
        """Create a stat advancement config based on the stat type."""
        # Use existing ADVANCEMENT_CONFIGS if the stat is already defined there
        if stat_key in self.ADVANCEMENT_CONFIGS:
            return self.ADVANCEMENT_CONFIGS[stat_key]

        # Otherwise create a default stat config
        stat_name = stat_key.replace("stat_", "").replace("_", " ").title()
        return AdvancementConfig(
            name=stat_key,
            display_name=stat_name,
            xp_cost=6,  # Default values for stats not in the main config
            cost_increase=20,
        )

    def _create_equipment_config(
        self, equip_key: str, equip_label: str
    ) -> AdvancementConfig:
        """Create an equipment advancement config."""
        # Equipment advancements use costs from the ContentAdvancementEquipment model
        # For now, use default costs that can be overridden in the template
        return AdvancementConfig(
            name=equip_key,
            display_name=equip_label,
            xp_cost=0,  # Will be set from ContentAdvancementEquipment
            cost_increase=0,  # Will be set from ContentAdvancementEquipment
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
        cls, campaign_action: Optional[CampaignAction] = None
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

        # For GANGER dice rolls, find the config with matching roll number
        advancement_choice = "stat_willpower"  # default
        cost_increase = 5  # default

        for key, config in cls.ADVANCEMENT_CONFIGS.items():
            if config.roll == campaign_action.dice_total:
                advancement_choice = key
                cost_increase = config.cost_increase
                break

        # For GANGER dice rolls, always use 6 XP
        return {
            "xp_cost": 6,
            "cost_increase": cost_increase,
            "advancement_choice": advancement_choice,
            "campaign_action_id": str(campaign_action.id),
        }

    @classmethod
    def get_advancement_config(
        cls, advancement_choice: str
    ) -> Optional[AdvancementConfig]:
        """Get the AdvancementConfig for a given choice."""
        return cls.ADVANCEMENT_CONFIGS.get(advancement_choice)

    def get_all_configs_json(self) -> dict:
        """Get all advancement configs as JSON-serializable dict."""
        configs = {}
        for key, config in self.advancement_configs.items():
            configs[key] = {
                "name": config.name,
                "display_name": config.display_name,
                "xp_cost": config.xp_cost,
                "cost_increase": config.cost_increase,
                "roll": config.roll,
                "restricted_to_fighter_categories": config.restricted_to_fighter_categories,
            }
        return configs


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
                random_skill = available_skills.order_by("?").first()
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


class EquipmentAssignmentSelectionForm(forms.Form):
    """Form for selecting a specific equipment assignment from an advancement."""

    assignment = forms.ModelChoiceField(
        queryset=ContentAdvancementAssignment.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="Select an option for this fighter to gain.",
    )

    def __init__(self, *args, **kwargs):
        self.advancement = kwargs.pop("advancement", None)
        self.fighter = kwargs.pop("fighter", None)
        super().__init__(*args, **kwargs)
        self._no_options_available = False
        self._no_options_error_message = None

        if self.advancement:
            # Get all assignments from the advancement
            queryset = self.advancement.assignments.all()

            # If fighter is provided, exclude assignments with duplicate upgrades
            if self.fighter:
                from gyrinx.core.models import ListFighterEquipmentAssignment

                # Get all upgrade IDs from the fighter's existing equipment assignments
                existing_upgrade_ids = set(
                    ListFighterEquipmentAssignment.objects.filter(
                        list_fighter=self.fighter, archived=False
                    ).values_list("upgrades_field", flat=True)
                )
                # Remove None values if any
                existing_upgrade_ids.discard(None)

                # Filter out assignments that have any upgrade matching existing upgrades
                if existing_upgrade_ids:
                    # Exclude assignments that have any of the existing upgrades
                    queryset = queryset.exclude(
                        upgrades_field__in=existing_upgrade_ids
                    ).distinct()

            self.fields["assignment"].queryset = queryset

            # Check if there are no available assignments
            if not queryset.exists():
                self.fields["assignment"].widget.attrs["disabled"] = True
                self._no_options_available = True
                self._no_options_error_message = (
                    f"No available options from {self.advancement.name}."
                )

    @property
    def no_options_error_message(self):
        """Public property to access the no options error message for display."""
        return self._no_options_error_message

    def clean(self):
        cleaned_data = super().clean()
        if self._no_options_available:
            raise ValidationError(self._no_options_error_message)
        return cleaned_data
