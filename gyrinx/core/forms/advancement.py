"""Forms for fighter advancement system."""

from dataclasses import dataclass
from typing import Optional

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q

from gyrinx.content.models import (
    ContentAdvancementAssignment,
    ContentAdvancementEquipment,
    ContentPromotionPath,
    ContentSkill,
    ContentSkillCategory,
    ContentStat,
)
from gyrinx.core.models.campaign import CampaignAction
from gyrinx.forms import group_select

# Human-readable suffix for what a promotion bundles, mirroring the old hardcoded labels
# ("Promote to Specialist (Random Primary Skill)").
GRANTS_SKILL_LABELS = {
    "primary_random": "Random Primary Skill",
    "primary_chosen": "Chosen Primary Skill",
    "secondary_random": "Random Secondary Skill",
    "secondary_chosen": "Chosen Secondary Skill",
    "any_random": "Random Skill (Any Set)",
}


def promotion_choice_key(path) -> str:
    return f"promotion_{path.id}"


def promotion_choice_label(path) -> str:
    suffix = GRANTS_SKILL_LABELS.get(path.grants_skill)
    return f"{path.name} ({suffix})" if suffix else path.name


def available_promotion_paths(fighter):
    """Promotion paths this fighter can currently be offered.

    The category gate applies in both source modes (see is_available_to_fighter), so it
    is pushed into SQL — blank from_category means any-category paths (e.g. 'Nominate as
    leader'), which every fighter must see; the source-fighter, house, and trigger
    checks run on the narrowed set.
    """
    paths = []
    for path in ContentPromotionPath.objects.filter(
        Q(from_category=fighter.get_category()) | Q(from_category="")
    ).prefetch_related("restricted_to_houses", "targets"):
        if not path.is_available_to_fighter(fighter):
            continue
        paths.append(path)
    return paths


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
    """
    Form for choosing whether to roll 2d6 for advancement.

    Includes fields for manual dice entry if the user opts not to roll, and a hidden action field
    to distinguish between the two submission types.
    """

    # Action field to distinguish which button was pressed
    roll_action = forms.CharField(required=False, widget=forms.HiddenInput())

    # Manual dice fields (only required for tabletop roll entry).
    # The template renders these as <select> dropdowns, overriding the HiddenInput widget.
    d6_1 = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=6,
        widget=forms.HiddenInput(),
    )
    d6_2 = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=6,
        widget=forms.HiddenInput(),
    )

    def clean(self):
        cleaned_data = super().clean()
        roll_action = cleaned_data.get("roll_action")
        d6_1 = cleaned_data.get("d6_1")
        d6_2 = cleaned_data.get("d6_2")

        if roll_action == "roll_manual":
            if d6_1 is None or d6_2 is None:
                raise ValidationError(
                    "Both dice values must be provided for manual entry."
                )
        return cleaned_data


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
        help_text="Fighter rating increase from this advancement.",
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

        # Generate promotion choices from content (data-driven; replaces the formerly
        # hardcoded skill_promote_specialist / skill_promote_champion entries).
        promotion_choices = []
        if fighter:
            for path in available_promotion_paths(fighter):
                key = promotion_choice_key(path)
                label = promotion_choice_label(path)
                promotion_choices.append((key, label))
                self.advancement_configs[key] = AdvancementConfig(
                    name=key,
                    display_name=label,
                    xp_cost=path.xp_cost,
                    cost_increase=path.cost_increase,
                )

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
            + promotion_choices
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
    def all_promotion_choices(cls) -> dict[str, str]:
        """
        Get a dictionary mapping promotion choice keys to their full names.

        Includes the two legacy hardcoded keys: stored advancement rows and old mid-flow
        URLs keep those strings forever, so they must remain valid/displayable.
        """
        choices = {
            promotion_choice_key(path): promotion_choice_label(path)
            for path in ContentPromotionPath.objects.all()
        }
        choices["skill_promote_specialist"] = (
            "Promote to Specialist (Random Primary Skill)"
        )
        choices["skill_promote_champion"] = "Promote to Champion (Random Primary Skill)"
        return choices

    @classmethod
    def all_advancement_choices(cls) -> dict[str, str]:
        """
        Get a dictionary mapping advancement choice keys to their full names.
        """
        return (
            cls.all_stat_choices()
            | cls.all_equipment_choices()
            | cls.all_promotion_choices()
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
        cls, campaign_action: Optional[CampaignAction] = None, fighter=None
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

        # Promotion rolls come from content: any path whose `rolls` list contains the 2d6
        # total (the rulebook's Ganger table promotes on a 2 AND a 12). Checked before the
        # stat configs, whose rolls (3–11) never overlap with promotion totals.
        for path in ContentPromotionPath.objects.filter(
            rolls__contains=campaign_action.dice_total
        ).prefetch_related("targets", "restricted_to_houses"):
            if fighter and not path.is_available_to_fighter(fighter):
                continue
            # Prefetched, so len() avoids a COUNT(*) per path. Multi-target paths can't
            # be prefilled — the roll flow has no target-selection step. (Dynamic
            # targets need the fighter to resolve; without one, only explicit targets
            # can be counted.)
            targets = path.resolve_targets(fighter) if fighter else path.targets.all()
            if len(targets) > 1:
                continue
            advancement_choice = promotion_choice_key(path)
            cost_increase = path.cost_increase
            break
        else:
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

    def __init__(self, *args, fighter=None, skill_type=None, packs=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fighter = fighter
        self.skill_type = skill_type

        # Use pack-aware queryset if packs provided, otherwise default manager.
        if packs is not None:
            base_skills_qs = ContentSkill.objects.with_packs(
                packs, include_archived_items=True
            )
        else:
            base_skills_qs = ContentSkill.objects.all()

        if fighter and skill_type:
            # Get existing skills to exclude: both default skills (from ContentFighter)
            # and user-added skills (from ListFighter M2M). Use pack-aware queryset
            # so pack skills are correctly identified.
            default_skill_ids = base_skills_qs.filter(
                contentfighter=fighter.content_fighter
            ).values_list("id", flat=True)
            user_skill_ids = base_skills_qs.filter(listfighter=fighter).values_list(
                "id", flat=True
            )
            existing_skill_ids = set(default_skill_ids) | set(user_skill_ids)

            if "primary" in skill_type:
                # Primary skills - show all skills from primary categories
                categories = fighter.get_primary_skill_categories()
                self.fields["skill"].queryset = (
                    base_skills_qs.filter(category__in=categories)
                    .exclude(id__in=existing_skill_ids)
                    .select_related("category")
                    .order_by("category__name", "name")
                )
            elif "secondary" in skill_type:
                # Secondary skills - show all skills from secondary categories
                categories = fighter.get_secondary_skill_categories()
                self.fields["skill"].queryset = (
                    base_skills_qs.filter(category__in=categories)
                    .exclude(id__in=existing_skill_ids)
                    .select_related("category")
                    .order_by("category__name", "name")
                )
            elif "any" in skill_type:
                # Any skill - show all skills
                self.fields["skill"].queryset = (
                    base_skills_qs.exclude(id__in=existing_skill_ids)
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

    def __init__(self, *args, fighter=None, skill_type=None, packs=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fighter = fighter
        self.skill_type = skill_type

        # Use pack-aware queryset if packs provided.
        if packs is not None:
            base_cats_qs = ContentSkillCategory.objects.with_packs(
                packs, include_archived_items=True
            )
        else:
            base_cats_qs = ContentSkillCategory.objects.all()

        if fighter and skill_type:
            if "primary" in skill_type:
                categories = fighter.get_primary_skill_categories()
                category_ids = [cat.id for cat in categories]
                self.fields["category"].queryset = base_cats_qs.filter(
                    id__in=category_ids
                )
            elif "secondary" in skill_type:
                categories = fighter.get_secondary_skill_categories()
                category_ids = [cat.id for cat in categories]
                self.fields["category"].queryset = base_cats_qs.filter(
                    id__in=category_ids
                )
            else:
                # For "any" skill type, show all categories
                self.fields["category"].queryset = base_cats_qs


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


class PromotionTargetSelectionForm(forms.Form):
    """Form for choosing which type a multi-target promotion turns the fighter into.

    The rulebook's "either a Forge Boss or a Stimmer as the controlling player wishes"
    choice — the heart of the Prospect promotion paths.
    """

    target = forms.ModelChoiceField(
        queryset=None,
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="Choose which type this fighter will be promoted to.",
        label="Promotion type",
    )

    def __init__(self, *args, path=None, fighter=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.path = path
        from gyrinx.content.models import ContentFighter

        # resolve_targets covers both target modes: explicit rows, and dynamic
        # resolution against the fighter's gang house (e.g. 'Nominate as leader').
        self.fields["target"].queryset = (
            path.resolve_targets(fighter)
            if path and fighter
            else ContentFighter.objects.none()
        )


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
