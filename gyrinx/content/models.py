"""
Models and utilities for managing fighter, equipment, rules, and related
content in Necromunda.

This module includes abstract base classes for shared data, plus concrete
models for fighters, equipment, rules, and more. Custom managers and querysets
provide streamlined data access.
"""

from dataclasses import dataclass, field, replace
from difflib import SequenceMatcher

from django.core.cache import caches
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Case, Exists, OuterRef, Q, Subquery, When
from django.db.models.functions import Cast, Coalesce, Lower
from django.utils.functional import cached_property
from polymorphic.models import PolymorphicModel
from simple_history.models import HistoricalRecords

from gyrinx.models import (
    Base,
    FighterCategoryChoices,
    QuerySetOf,
    equipment_category_group_choices,
    is_int,
)

##
## Content Models
##


class Content(Base):
    """
    An abstract base model that captures common fields for all content-related
    models. Subclasses should inherit from this to store standard metadata.
    """

    class Meta:
        abstract = True


class ContentHouse(Content):
    """
    Represents a faction or house that fighters can belong to.
    """

    help_text = "The Content House identifies the house or faction of a fighter."
    name = models.CharField(max_length=255)
    skill_categories = models.ManyToManyField(
        "ContentSkillCategory",
        blank=True,
        related_name="houses",
        verbose_name="Unique Skill Categories",
    )
    generic = models.BooleanField(
        default=False,
        help_text="If checked, fighters in this House can join lists and gangs of any other House.",
    )

    house_additional_rules_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="House Additional Rules Type",
        help_text="If applicable, the name of the unique additional rules for this house (e.g. Legendary Name).",
    )

    history = HistoricalRecords()

    def fighters(self):
        """
        Returns all fighters associated with this house.
        """
        return self.contentfighter_set.all()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "House"
        verbose_name_plural = "Houses"
        ordering = ["name"]


class ContentSkillCategory(Content):
    """
    Represents a category of skills that fighters may possess.
    """

    name = models.CharField(max_length=255, unique=True)
    restricted = models.BooleanField(
        default=False,
        help_text="If checked, this skill tree is only available to specific gangs.",
    )
    history = HistoricalRecords()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Skill Tree"
        verbose_name_plural = "Skill Trees"
        ordering = ["name"]


class ContentSkill(Content):
    """
    Represents a skill that fighters may possess.
    """

    name = models.CharField(max_length=255)
    category = models.ForeignKey(
        ContentSkillCategory,
        on_delete=models.CASCADE,
        null=False,
        blank=False,
        related_name="skills",
        verbose_name="tree",
    )
    history = HistoricalRecords()

    def __str__(self):
        return f"{self.name}"

    class Meta:
        verbose_name = "Skill"
        verbose_name_plural = "Skills"
        ordering = ["category", "name"]
        unique_together = ["name", "category"]


class ContentHouseAdditionalRuleTree(Content):
    """
    Represents a unique set of additional rules for a specific house.
    """

    house = models.ForeignKey(
        ContentHouse,
        on_delete=models.CASCADE,
        related_name="house_additional_rule_trees",
    )
    name = models.CharField(max_length=255)
    history = HistoricalRecords()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "House Additional Rule Tree"
        verbose_name_plural = "House Additional Rule Trees"
        ordering = ["house__name", "name"]


class ContentHouseAdditionalRule(Content):
    """
    Represents a unique additional rule for a specific house.
    """

    tree = models.ForeignKey(
        ContentHouseAdditionalRuleTree,
        on_delete=models.CASCADE,
        related_name="rules",
    )
    name = models.CharField(max_length=255)
    history = HistoricalRecords()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "House Additional Rule"
        verbose_name_plural = "House Additional Rules"
        ordering = ["tree__house__name", "tree__name", "name"]


class ContentPsykerDiscipline(Content):
    """
    Represents a discipline of Psyker/Wyrd powers.
    """

    name = models.CharField(max_length=255, unique=True)
    generic = models.BooleanField(
        default=False,
        help_text="If checked, this discipline can be used by any psyker.",
    )
    history = HistoricalRecords()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Psyker Discipline"
        verbose_name_plural = "Psyker Disciplines"
        ordering = ["name"]


class ContentPsykerPower(Content):
    """
    Represents a specific power within a discipline of Psyker/Wyrd powers.
    """

    name = models.CharField(max_length=255)
    discipline = models.ForeignKey(
        ContentPsykerDiscipline,
        on_delete=models.CASCADE,
        related_name="powers",
    )
    history = HistoricalRecords()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Psyker Power"
        verbose_name_plural = "Psyker Powers"
        ordering = ["discipline__name", "name"]
        unique_together = ["name", "discipline"]


class ContentFighterPsykerDisciplineAssignment(Content):
    """
    Represents a discipline assignment for a Psyker content fighter.
    """

    fighter = models.ForeignKey(
        "ContentFighter",
        on_delete=models.CASCADE,
        related_name="psyker_disciplines",
    )
    discipline = models.ForeignKey(
        ContentPsykerDiscipline,
        on_delete=models.CASCADE,
        related_name="fighter_assignments",
    )
    history = HistoricalRecords()

    def clean(self):
        """
        Validation to ensure that a generic discipline cannot be assigned to a fighter.
        """
        if not self.fighter.is_psyker:
            raise ValidationError(
                {
                    "fighter": "Cannot assign a psyker discipline to a non-psyker fighter."
                }
            )

        if self.discipline.generic:
            raise ValidationError(
                {
                    "discipline": "Cannot assign a generic psyker discipline to a fighter."
                }
            )

    def __str__(self):
        return f"{self.fighter} {self.discipline}"

    class Meta:
        verbose_name = "Fighter Psyker Discipline"
        verbose_name_plural = "Fighter Psyker Disciplines"
        unique_together = ["fighter", "discipline"]
        ordering = ["fighter__type", "discipline__name"]


class ContentFighterPsykerPowerDefaultAssignment(Content):
    """
    Represents a default power assignment for a Psyker content fighter.
    """

    fighter = models.ForeignKey(
        "ContentFighter",
        on_delete=models.CASCADE,
        related_name="default_psyker_powers",
    )
    psyker_power = models.ForeignKey(
        ContentPsykerPower,
        on_delete=models.CASCADE,
        related_name="fighter_assignments",
    )
    history = HistoricalRecords()

    def clean_fields(self, exclude={}):
        """
        Validation to ensure that defaults cannot be assigned to a non-Psyker fighter.
        """
        if "fighter" not in exclude and not self.fighter.is_psyker:
            raise ValidationError(
                {"fighter": "Cannot assign a psyker power to a non-psyker fighter."}
            )

    def name(self):
        return f"{self.psyker_power.name} ({self.psyker_power.discipline})"

    def __str__(self):
        return f"{self.fighter} {self.psyker_power}"

    class Meta:
        verbose_name = "Psyker Fighter-Power Default Assignment"
        verbose_name_plural = "Psyker Fighter-Power Default Assignments"
        unique_together = ["fighter", "psyker_power"]
        ordering = ["fighter__type", "psyker_power__name"]


class ContentRule(Content):
    """
    Represents a specific rule from the game system.
    """

    name = models.CharField(max_length=255)

    history = HistoricalRecords()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Rule"
        verbose_name_plural = "Rules"
        ordering = ["name"]


class ContentEquipmentCategory(Content):
    name = models.CharField(max_length=255, unique=True)
    group = models.CharField(max_length=255, choices=equipment_category_group_choices)
    restricted_to = models.ManyToManyField(
        ContentHouse,
        blank=True,
        related_name="restricted_equipment_categories",
        verbose_name="Restricted To",
        help_text="If provided, this equipment category is only available to specific gang houses.",
    )

    history = HistoricalRecords()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Equipment Category"
        verbose_name_plural = "Equipment Categories"
        ordering = ["name"]


class ContentEquipmentManager(models.Manager):
    """
    Custom manager for :model:`content.ContentEquipment` model, providing annotated
    default querysets (cost as integer, presence of weapon profiles, etc.).
    """

    def get_queryset(self):
        """
        Returns the default annotated queryset for equipment.
        """
        return (
            super()
            .get_queryset()
            .annotate(
                cost_cast_int=Case(
                    When(
                        Q(cost__regex=r"^-?\d+$"),
                        then=Cast("cost", models.IntegerField()),
                    ),
                    default=0,
                ),
                has_weapon_profiles=Exists(
                    ContentWeaponProfile.objects.filter(equipment=OuterRef("pk"))
                ),
            )
            .order_by("category__name", "name", "id")
        )


class ContentEquipmentQuerySet(models.QuerySet):
    """
    Custom QuerySet for ContentEquipment. Provides filtering and annotations
    for weapons vs. non-weapons, and fighter-specific cost.
    """

    def weapons(self) -> "ContentEquipmentQuerySet":
        """
        Filters the queryset to include only equipment items identified as weapons.
        """
        return self.filter(has_weapon_profiles=True)

    def non_weapons(self) -> "ContentEquipmentQuerySet":
        """
        Filters the queryset to include only equipment items that are not weapons.
        """
        return self.exclude(has_weapon_profiles=True)

    def house_restricted(self, house: "ContentHouse") -> "ContentEquipmentQuerySet":
        return self.filter(Q(category__restricted_to=house))

    def with_cost_for_fighter(
        self, content_fighter: "ContentFighter"
    ) -> "ContentEquipmentQuerySet":
        """
        Annotates the queryset with fighter-specific cost overrides, if any.
        """
        equipment_list_items = ContentFighterEquipmentListItem.objects.filter(
            fighter=content_fighter,
            equipment=OuterRef("pk"),
            # This is critical to make sure we only annotate the cost of the base equipment.
            weapon_profile__isnull=True,
        )
        return self.annotate(
            cost_override=Subquery(
                equipment_list_items.values("cost")[:1],
                output_field=models.IntegerField(),
            ),
            cost_for_fighter=Coalesce("cost_override", "cost_cast_int"),
        )

    def with_profiles_for_fighter(
        self, content_fighter: "ContentFighter"
    ) -> "ContentEquipmentQuerySet":
        """
        Annotates the queryset with weapon profiles for a given fighter, if any.
        """
        # contentweaponprofile_set.with_cost_for_fighter(content_fighter)
        return self.prefetch_related(
            models.Prefetch(
                "contentweaponprofile_set",
                queryset=ContentWeaponProfile.objects.with_cost_for_fighter(
                    content_fighter
                ),
                to_attr="pre_profiles_for_fighter",
            )
        )


class ContentEquipment(Content):
    """
    Represents an item of equipment that a fighter may acquire.
    Can be a weapon or other piece of gear. Cost and rarity are tracked.
    """

    name = models.CharField(max_length=255)
    category = models.ForeignKey(
        ContentEquipmentCategory,
        on_delete=models.CASCADE,
        null=True,
        blank=False,
        related_name="equipment",
    )

    cost = models.CharField(
        help_text="The credit cost of the equipment at the Trading Post. Note that, in weapons, "
        "this is overridden by the 'Standard' weapon profile cost.",
        blank=True,
        null=False,
    )

    rarity = models.CharField(
        max_length=1,
        choices=[
            ("R", "Rare (R)"),
            ("I", "Illegal (I)"),
            ("E", "Exclusive (E)"),
            ("U", "Unique (U)"),
            ("C", "Common (C)"),
        ],
        blank=True,
        default="C",
        help_text="Use 'E' to exclude this equipment from the Trading Post. Use 'U' for equipment that is unique to a fighter.",
        verbose_name="Availability",
    )
    rarity_roll = models.IntegerField(
        blank=True, null=True, verbose_name="Availability Level"
    )

    class UpgradeMode(models.TextChoices):
        SINGLE = "SINGLE", "Single"
        MULTI = "MULTI", "Multi"

    upgrade_mode = models.CharField(
        max_length=6,
        choices=UpgradeMode.choices,
        default=UpgradeMode.SINGLE,
        help_text="If applicable, does this equipment have an upgrade stack (single, e.g. cyberteknika) or options (multi, e.g. genesmithing)?",
    )

    upgrade_stack_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        default="",
        help_text="If applicable, the name of the stack of upgrades for this equipment (e.g. Upgrade or Augmentation). Use the singular form.",
    )

    modifiers = models.ManyToManyField(
        "ContentMod",
        blank=True,
        help_text="Modifiers to apply to the fighter's statline and traits.",
    )

    history = HistoricalRecords()

    def __str__(self):
        return self.name

    def cost_int(self):
        """
        Returns the integer cost of this equipment or zero if not specified.
        """
        if not self.cost:
            return 0

        if not is_int(self.cost):
            return 0

        return int(self.cost)

    def cost_display(self):
        """
        Returns a readable cost string with a '¢' suffix.
        """
        if not is_int(self.cost):
            return f"{self.cost}"

        if not self.cost:
            return ""

        return f"{self.cost}¢"

    def cost_for_fighter_int(self):
        if hasattr(self, "cost_for_fighter"):
            return self.cost_for_fighter

        raise AttributeError(
            "cost_for_fighter not available. Use with_cost_for_fighter()"
        )

    def cat(self):
        """
        Returns the human-readable label of the equipment's category.
        """
        return self.category.name

    def is_weapon(self):
        """
        Indicates whether this equipment is a weapon. If 'has_weapon_profiles'
        is annotated, uses that; otherwise checks the database.
        """
        if hasattr(self, "has_weapon_profiles"):
            return self.has_weapon_profiles
        return ContentWeaponProfile.objects.filter(equipment=self).exists()

    @cached_property
    def is_weapon_cached(self):
        return self.is_weapon()

    @cached_property
    def is_house_additional(self):
        """
        Indicates whether this equipment is house-specific additional gear.
        """
        return self.category.restricted_to.exists()

    @cached_property
    def upgrade_mode_single(self):
        """
        Indicates whether this equipment is a multi-upgrade mode.
        """
        return self.upgrade_mode == ContentEquipment.UpgradeMode.SINGLE

    @cached_property
    def upgrade_mode_multi(self):
        """
        Indicates whether this equipment is a single-upgrade mode.
        """
        return self.upgrade_mode == ContentEquipment.UpgradeMode.MULTI

    def profiles(self):
        """
        Returns all associated weapon profiles for this equipment.
        """
        return self.contentweaponprofile_set.all()

    def profiles_for_fighter(
        self, content_fighter
    ) -> QuerySetOf["ContentWeaponProfile"]:
        """
        Returns all weapon profiles for this equipment, annotated with
        fighter-specific cost if available.
        """
        if hasattr(self, "pre_profiles_for_fighter"):
            return self.pre_profiles_for_fighter

        return self.contentweaponprofile_set.with_cost_for_fighter(content_fighter)

    class Meta:
        verbose_name = "Equipment"
        verbose_name_plural = "Equipment"
        unique_together = ["name", "category"]
        ordering = ["name"]

    def clean(self):
        self.name = self.name.strip()

    objects: ContentEquipmentManager = ContentEquipmentManager.from_queryset(
        ContentEquipmentQuerySet
    )()


class ContentFighterManager(models.Manager):
    """
    Custom manager for :model:`content.ContentFighter` model.
    """

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .annotate(
                _category_order=Case(
                    *[
                        When(category=category, then=index)
                        for index, category in enumerate(
                            [
                                "LEADER",
                                "CHAMPION",
                                "PROSPECT",
                                "SPECIALIST",
                                "GANGER",
                                "JUVE",
                            ]
                        )
                    ],
                    default=99,
                )
            )
            .order_by(
                "house__name",
                "_category_order",
                "type",
            )
        )


class ContentFighterQuerySet(models.QuerySet):
    """
    Custom QuerySet for :model:`content.ContentFighter`.
    """

    pass


class ContentFighter(Content):
    """
    Represents a fighter or character archetype. Includes stats, base cost,
    and relationships to skills, rules, and a house/faction.
    """

    help_text = "The Content Fighter captures archetypal information about a fighter from the rulebooks."
    type = models.CharField(max_length=255)
    category = models.CharField(max_length=255, choices=FighterCategoryChoices)
    house = models.ForeignKey(
        ContentHouse, on_delete=models.CASCADE, null=True, blank=True
    )
    skills = models.ManyToManyField(
        ContentSkill, blank=True, verbose_name="Default Skills"
    )
    primary_skill_categories = models.ManyToManyField(
        ContentSkillCategory,
        blank=True,
        related_name="primary_fighters",
        verbose_name="Primary Skill Trees",
    )
    secondary_skill_categories = models.ManyToManyField(
        ContentSkillCategory,
        blank=True,
        related_name="secondary_fighters",
        verbose_name="Secondary Skill Trees",
    )
    rules = models.ManyToManyField(ContentRule, blank=True)
    base_cost = models.IntegerField(default=0)

    movement = models.CharField(
        max_length=12, blank=True, null=False, default="", verbose_name="M"
    )
    weapon_skill = models.CharField(
        max_length=12, blank=True, null=False, default="", verbose_name="WS"
    )
    ballistic_skill = models.CharField(
        max_length=12, blank=True, null=False, default="", verbose_name="BS"
    )
    strength = models.CharField(
        max_length=12, blank=True, null=False, default="", verbose_name="S"
    )
    toughness = models.CharField(
        max_length=12, blank=True, null=False, default="", verbose_name="T"
    )
    wounds = models.CharField(
        max_length=12, blank=True, null=False, default="", verbose_name="W"
    )
    initiative = models.CharField(
        max_length=12, blank=True, null=False, default="", verbose_name="I"
    )
    attacks = models.CharField(
        max_length=12, blank=True, null=False, default="", verbose_name="A"
    )
    leadership = models.CharField(
        max_length=12, blank=True, null=False, default="", verbose_name="Ld"
    )
    cool = models.CharField(
        max_length=12, blank=True, null=False, default="", verbose_name="Cl"
    )
    willpower = models.CharField(
        max_length=12, blank=True, null=False, default="", verbose_name="Wil"
    )
    intelligence = models.CharField(
        max_length=12, blank=True, null=False, default="", verbose_name="Int"
    )

    history = HistoricalRecords()

    def __str__(self):
        """
        Returns a string representation, including house and fighter category.
        """
        house = f"{self.house}" if self.house else ""
        return f"{house} {self.type} ({FighterCategoryChoices[self.category].label})".strip()

    def cat(self):
        """
        Returns the human-readable label of the fighter's category.
        """
        return FighterCategoryChoices[self.category].label

    def name(self):
        """
        Returns a composite name combining fighter type and category label.
        """
        return f"{self.type} ({self.cat()})"

    def cost(self):
        """
        Returns the cost of the fighter (base cost only, unless additional
        equipment costs are considered).
        """
        return self.base_cost

    def cost_int(self):
        """
        Returns the fighter's cost as an integer.
        """
        return int(self.cost())

    def cost_for_house(self, house):
        """
        Returns the cost of the fighter for a specific house, including
        any overrides.
        """
        cost_override = ContentFighterHouseOverride.objects.filter(
            fighter=self,
            house=house,
            cost__isnull=False,
        ).first()
        if cost_override:
            return cost_override.cost

        return self.cost_int()

    def statline(self):
        """
        Returns a list of dictionaries describing the fighter's core stats,
        with additional styling indicators.
        """
        stats = [
            (f, self._meta.get_field(f))
            for f in [
                "movement",
                "weapon_skill",
                "ballistic_skill",
                "strength",
                "toughness",
                "wounds",
                "initiative",
                "attacks",
                "leadership",
                "cool",
                "willpower",
                "intelligence",
            ]
        ]
        return [
            {
                "field_name": f,
                "name": field.verbose_name,
                "value": getattr(self, field.name) or "-",
                "highlight": bool(
                    field.name in ["leadership", "cool", "willpower", "intelligence"]
                ),
                "classes": ("border-start" if field.name in ["leadership"] else ""),
            }
            for f, field in stats
        ]

    def ruleline(self) -> list[str]:
        """
        Returns a list of rule names associated with this fighter.
        """
        return [rule.name for rule in self.rules.all()]

    @cached_property
    def is_psyker(self):
        """
        Indicates whether this fighter is a psyker.
        """
        return (
            self.rules.annotate(name_lower=Lower("name"))
            .filter(
                name_lower__in=["psyker", "non-sanctioned psyker", "sanctioned psyker"]
            )
            .exists()
        )

    def copy_to_house(self, house):
        skills = self.skills.all()
        primary_skill_categories = self.primary_skill_categories.all()
        secondary_skill_categories = self.secondary_skill_categories.all()
        rules = self.rules.all()
        equipment_list_items = ContentFighterEquipmentListItem.objects.filter(
            fighter=self
        )
        equipment_list_weapon_accessories = (
            ContentFighterEquipmentListWeaponAccessory.objects.filter(fighter=self)
        )
        default_assignments = ContentFighterDefaultAssignment.objects.filter(
            fighter=self
        )

        # Copy the fighter
        self.pk = None
        self.house = house
        self.save()
        fighter_id = self.pk

        self.skills.set(skills)
        self.primary_skill_categories.set(primary_skill_categories)
        self.secondary_skill_categories.set(secondary_skill_categories)
        self.rules.set(rules)

        for equipment in equipment_list_items:
            equipment.pk = None
            equipment.fighter_id = fighter_id
            equipment.save()

        for accessory in equipment_list_weapon_accessories:
            accessory.pk = None
            accessory.fighter_id = fighter_id
            accessory.save()

        for assignment in default_assignments:
            weapon_profiles = assignment.weapon_profiles_field.all()
            weapon_accessories = assignment.weapon_accessories_field.all()

            assignment.pk = None
            assignment.fighter_id = fighter_id
            assignment.save()
            assignment.weapon_profiles_field.set(weapon_profiles)
            assignment.weapon_accessories_field.set(weapon_accessories)
            assignment.save()

        self.save()

        # self is now the new fighter
        return self

    class Meta:
        verbose_name = "Fighter"
        verbose_name_plural = "Fighters"

    objects = ContentFighterManager.from_queryset(ContentFighterQuerySet)()


class ContentFighterEquipmentListItem(Content):
    """
    Associates :model:`content.ContentEquipment` with a given fighter in the rulebook, optionally
    specifying a weapon profile and cost override.
    """

    help_text = "Captures the equipment list available to a fighter in the rulebook."
    fighter = models.ForeignKey(ContentFighter, on_delete=models.CASCADE, db_index=True)
    equipment = models.ForeignKey(
        ContentEquipment, on_delete=models.CASCADE, db_index=True
    )
    weapon_profile = models.ForeignKey(
        "ContentWeaponProfile",
        on_delete=models.CASCADE,
        db_index=True,
        null=True,
        blank=True,
        help_text="The weapon profile to use for this equipment list item.",
    )
    cost = models.IntegerField(default=0)
    history = HistoricalRecords()

    def cost_int(self):
        """
        Returns the integer cost of this item.
        """
        return self.cost

    def cost_display(self):
        """
        Returns a cost display string with '¢'.
        """
        return f"{self.cost}¢"

    def __str__(self):
        profile = f" ({self.weapon_profile})" if self.weapon_profile else ""
        return f"{self.fighter}: {self.equipment}{profile}"

    class Meta:
        verbose_name = "Equipment List Item"
        verbose_name_plural = "Equipment List Items"
        unique_together = ["fighter", "equipment", "weapon_profile"]
        ordering = ["fighter__type", "equipment__name"]

    def clean(self):
        """
        Validation to ensure that the weapon profile matches the correct equipment.
        """
        if not self.equipment_id:
            raise ValidationError({"equipment": "Equipment must be specified."})

        if self.weapon_profile and self.weapon_profile.equipment != self.equipment:
            raise ValidationError(
                {"weapon_profile": "Weapon profile must match the equipment selected."}
            )


class ContentFighterEquipmentListWeaponAccessory(Content):
    """
    Associates :model:`content.ContentWeaponAccessory` with a given fighter in the rulebook, optionally
    specifying a cost override.
    """

    help_text = (
        "Captures the weapon accessories available to a fighter in the rulebook."
    )
    fighter = models.ForeignKey(ContentFighter, on_delete=models.CASCADE, db_index=True)
    weapon_accessory = models.ForeignKey(
        "ContentWeaponAccessory", on_delete=models.CASCADE, db_index=True
    )
    cost = models.IntegerField(default=0)
    history = HistoricalRecords()

    def cost_int(self):
        """
        Returns the integer cost of this item.
        """
        return self.cost

    def cost_display(self):
        """
        Returns a cost display string with '¢'.
        """
        return f"{self.cost}¢"

    def __str__(self):
        return f"{self.fighter} {self.weapon_accessory} ({self.cost})"

    class Meta:
        verbose_name = "Equipment List Weapon Accessory"
        verbose_name_plural = "Equipment List Weapon Accessories"
        unique_together = ["fighter", "weapon_accessory"]
        ordering = ["fighter__type", "weapon_accessory__name"]

    def clean(self):
        """
        Validation to ensure cost is not negative.
        """
        if self.cost_int() < 0:
            raise ValidationError("Cost cannot be negative.")


class ContentWeaponTrait(Content):
    """
    Represents a trait that can be associated with a weapon, such as 'Knockback'
    or 'Rapid Fire'.
    """

    name = models.CharField(max_length=255, unique=True)
    history = HistoricalRecords()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Weapon Trait"
        verbose_name_plural = "Weapon Traits"
        ordering = ["name"]


class ContentEquipmentFighterProfile(models.Model):
    """
    Links ContentEquipment to a ContentFighter for assigning Exotic Beasts and Vehicles.
    """

    equipment = models.ForeignKey(
        ContentEquipment, on_delete=models.CASCADE, verbose_name="Equipment"
    )
    content_fighter = models.ForeignKey(
        ContentFighter,
        on_delete=models.CASCADE,
        verbose_name="Fighter",
        help_text="This type of Fighter will be created when this Equipment is assigned",
    )
    history = HistoricalRecords()

    def __str__(self):
        return f"{self.content_fighter}"

    class Meta:
        verbose_name = "Equipment-Fighter Link"
        verbose_name_plural = "Equipment-Fighter Links"
        unique_together = ["equipment", "content_fighter"]


class ContentEquipmentEquipmentProfile(models.Model):
    """
    Links ContentEquipment to another ContentEquipment for auto-assigns.
    """

    equipment = models.ForeignKey(
        ContentEquipment,
        on_delete=models.CASCADE,
        verbose_name="Equipment",
    )
    linked_equipment = models.ForeignKey(
        ContentEquipment,
        on_delete=models.CASCADE,
        verbose_name="Auto-assigned Equipment",
        related_name="equip_equip_link_profiles",
        help_text="This Equipment will be auto-assigned when the main Equipment is assigned",
    )
    history = HistoricalRecords()

    def __str__(self):
        return f"{self.equipment} -> {self.linked_equipment}"

    def clean(self):
        """
        Validation to ensure that the linked equipment is not the same as the main equipment.
        """
        if self.equipment == self.linked_equipment:
            raise ValidationError(
                "The linked equipment cannot be the same as the main equipment."
            )

        if self.equipment.equip_equip_link_profiles.exists():
            raise ValidationError(
                "The linked equipment cannot itself be linked equipment."
            )

    class Meta:
        verbose_name = "Equipment-Equipment Link"
        verbose_name_plural = "Equipment-Equipment Links"
        unique_together = ["equipment", "linked_equipment"]


class ContentWeaponProfileManager(models.Manager):
    """
    Custom manager for :model:`content.ContentWeaponProfile` model.
    """

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .annotate(
                _name_order=Case(
                    When(name="", then=0),
                    default=1,
                    output_field=models.IntegerField(),
                )
            )
            .order_by(
                "equipment__name",
                "_name_order",
                "name",
                "cost",
            )
        )


class ContentWeaponProfileQuerySet(models.QuerySet):
    """
    Custom QuerySet for :model:`content.ContentWeaponProfile`. Provides fighter-specific cost overrides.
    """

    def with_cost_for_fighter(
        self, content_fighter: "ContentFighter"
    ) -> "ContentEquipmentQuerySet":
        """
        Annotates the queryset with cost overrides for a given fighter, if present.
        """
        equipment_list_items = ContentFighterEquipmentListItem.objects.filter(
            fighter=content_fighter,
            equipment=OuterRef("equipment"),
            # This is critical to make sure we only annotate the cost of this profile.
            weapon_profile=OuterRef("pk"),
        )
        return self.annotate(
            cost_override=Subquery(
                equipment_list_items.values("cost")[:1],
                output_field=models.IntegerField(),
            ),
            cost_for_fighter=Coalesce("cost_override", "cost"),
        )


@dataclass
class RulelineDisplay:
    value: str
    modded: bool = False


@dataclass
class StatlineDisplay:
    name: str
    field_name: str
    value: str
    classes: str = ""
    modded: bool = False
    highlight: bool = False


class ContentWeaponProfile(Content):
    """
    Represents a specific profile for :model:`content.ContentEquipment`. "Standard" profiles have zero cost.
    """

    equipment = models.ForeignKey(
        ContentEquipment,
        on_delete=models.CASCADE,
        db_index=True,
        null=True,
        blank=False,
    )
    name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Leave blank if the profile has no name (i.e. is the default statline). Don't include the hyphen for named profiles.",
    )
    help_text = "Captures the cost, rarity and statline for a weapon."

    # If the cost is zero, then the profile is free to use and "standard".
    cost = models.IntegerField(
        default=0,
        help_text="The credit cost of the weapon profile at the Trading Post. If the cost is zero, "
        "then the profile is free to use and standard. This cost can be overridden by the "
        "fighter's equipment list.",
    )
    rarity = models.CharField(
        max_length=1,
        choices=[
            ("R", "Rare (R)"),
            ("I", "Illegal (I)"),
            ("E", "Exclusive (E)"),
            ("C", "Common (C)"),
        ],
        blank=True,
        default="C",
        help_text="Use 'E' to exclude this profile from the Trading Post.",
        verbose_name="Availability",
    )
    rarity_roll = models.IntegerField(
        blank=True, null=True, verbose_name="Availability Level"
    )

    # Stat line
    range_short = models.CharField(
        max_length=12, blank=True, null=False, default="", verbose_name="Rng S"
    )
    range_long = models.CharField(
        max_length=12, blank=True, null=False, default="", verbose_name="Rng L"
    )
    accuracy_short = models.CharField(
        max_length=12, blank=True, null=False, default="", verbose_name="Acc S"
    )
    accuracy_long = models.CharField(
        max_length=12, blank=True, null=False, default="", verbose_name="Acc L"
    )
    strength = models.CharField(
        max_length=12, blank=True, null=False, default="", verbose_name="Str"
    )
    armour_piercing = models.CharField(
        max_length=12, blank=True, null=False, default="", verbose_name="Ap"
    )
    damage = models.CharField(
        max_length=12, blank=True, null=False, default="", verbose_name="D"
    )
    ammo = models.CharField(
        max_length=12, blank=True, null=False, default="", verbose_name="Am"
    )

    traits = models.ManyToManyField(ContentWeaponTrait, blank=True)
    history = HistoricalRecords()

    def __str__(self):
        return f"{self.equipment} {self.name if self.name else '(Standard)'}"

    def cost_int(self):
        """
        Returns the integer cost of this weapon profile.
        """
        return self.cost

    def cost_display(self) -> str:
        """
        Returns a readable display for the cost, including any sign and '¢'.
        """
        if self.name == "" or self.cost_int() == 0:
            return ""
        return f"+{self.cost_int()}¢"

    def cost_for_fighter_int(self):
        if hasattr(self, "cost_for_fighter"):
            return self.cost_for_fighter

        raise AttributeError(
            "cost_for_fighter not available. Use with_cost_for_fighter()"
        )

    def statline(self) -> list[StatlineDisplay]:
        """
        Returns a list of dictionaries describing the weapon profile's stats,
        including range, accuracy, strength, and so forth.
        """
        stats = [
            self._meta.get_field(field)
            for field in [
                "range_short",
                "range_long",
                "accuracy_short",
                "accuracy_long",
                "strength",
                "armour_piercing",
                "damage",
                "ammo",
            ]
        ]
        return [
            StatlineDisplay(
                **{
                    "name": field.verbose_name,
                    "field_name": field.name,
                    "classes": (
                        "border-start"
                        if field.name in ["accuracy_short", "strength"]
                        else ""
                    ),
                    "value": getattr(self, field.name) or "-",
                }
            )
            for field in stats
        ]

    def traitline(self):
        """
        Returns a list of weapon trait names associated with this profile.
        """
        return [trait.name for trait in self.traits.all()]

    @cached_property
    def traitline_cached(self):
        return self.traitline()

    class Meta:
        verbose_name = "Weapon Profile"
        verbose_name_plural = "Weapon Profiles"
        unique_together = ["equipment", "name"]

    def clean(self):
        """
        Validation to ensure appropriate costs and cost signs for standard
        vs non-standard weapon profiles.
        """
        self.name = self.name.strip()

        if self.name.startswith("-"):
            raise ValidationError("Name should not start with a hyphen.")

        if self.name == "(Standard)":
            raise ValidationError('Name should not be "(Standard)".')

        # Ensure that specific fields are not hyphens
        for pf in [
            "range_short",
            "range_long",
            "accuracy_short",
            "accuracy_long",
            "strength",
            "armour_piercing",
            "damage",
            "ammo",
        ]:
            setattr(self, pf, getattr(self, pf).strip())
            value = getattr(self, pf)
            if value == "-":
                setattr(self, pf, "")

            if pf in [
                "range_short",
                "range_long",
            ]:
                if value and value[0].isdigit() and not value.endswith('"'):
                    setattr(self, pf, f'{value}"')

        if self.cost_int() < 0:
            raise ValidationError({"cost": "Cost cannot be negative."})

        if self.name == "" and self.cost_int() != 0:
            raise ValidationError(
                {
                    "cost": "Standard (un-named) profiles should have zero cost.",
                }
            )

    objects = ContentWeaponProfileManager.from_queryset(ContentWeaponProfileQuerySet)()


class ContentWeaponAccessoryManager(models.Manager):
    """
    Custom manager for :model:`content.ContentWeaponAccessory` model. Currently unused but available
    for future extensions.
    """

    pass


class ContentWeaponAccessoryQuerySet(models.QuerySet):
    """
    Custom QuerySet for :model:`content.ContentWeaponAccessory`. Provides fighter-specific cost overrides.
    """

    def with_cost_for_fighter(
        self, content_fighter: "ContentFighter"
    ) -> "ContentWeaponAccessoryQuerySet":
        """
        Annotates the queryset with cost overrides for a given fighter, if present.
        """
        equipment_list_entries = (
            ContentFighterEquipmentListWeaponAccessory.objects.filter(
                fighter=content_fighter,
                weapon_accessory=OuterRef("pk"),
            )
        )
        return self.annotate(
            cost_override=Subquery(
                equipment_list_entries.values("cost")[:1],
                output_field=models.IntegerField(),
            ),
            cost_for_fighter=Coalesce("cost_override", "cost"),
        )


class ContentWeaponAccessory(Content):
    """
    Represents an accessory that can be associated with a weapon.
    """

    name = models.CharField(max_length=255, unique=True)
    cost = models.IntegerField(
        default=0,
        help_text="The credit cost of the weapon accessory at the Trading Post. This cost can be "
        "overridden by the fighter's equipment list.",
    )
    rarity = models.CharField(
        max_length=1,
        choices=[
            ("R", "Rare (R)"),
            ("I", "Illegal (I)"),
            ("E", "Exclusive (E)"),
            ("C", "Common (C)"),
        ],
        blank=True,
        default="C",
        help_text="Use 'E' to exclude this profile from the Trading Post.",
        verbose_name="Availability",
    )
    rarity_roll = models.IntegerField(
        blank=True, null=True, verbose_name="Availability Level"
    )

    modifiers = models.ManyToManyField(
        "ContentMod",
        blank=True,
        help_text="Modifiers to apply to the weapon's statline and traits.",
    )

    history = HistoricalRecords()

    def cost_int(self):
        """
        Returns the integer cost of this weapon accessory.
        """
        return self.cost

    def cost_for_fighter_int(self):
        if hasattr(self, "cost_for_fighter"):
            return self.cost_for_fighter

        raise AttributeError(
            "cost_for_fighter not available. Use with_cost_for_fighter()"
        )

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Weapon Accessory"
        verbose_name_plural = "Weapon Accessories"
        ordering = ["name"]

    objects = ContentWeaponAccessoryManager.from_queryset(
        ContentWeaponAccessoryQuerySet
    )()


class ContentEquipmentUpgrade(Content):
    """
    Represents an upgrade that can be associated with a piece of equipment.
    """

    equipment = models.ForeignKey(
        ContentEquipment,
        on_delete=models.CASCADE,
        db_index=True,
        related_name="upgrades",
    )
    name = models.CharField(max_length=255)
    position = models.IntegerField(
        default=0,
        help_text="The position in which this upgrade sits in the stack, if applicable.",
    )
    cost = models.IntegerField(
        default=0,
        help_text="The credit cost of the equipment upgrade. Costs are cumulative based on position.",
    )
    modifiers = models.ManyToManyField(
        "ContentMod",
        blank=True,
        help_text="Modifiers to apply to the equipment or fighter's statline and traits.",
    )

    history = HistoricalRecords()

    def cost_int(self):
        """
        Returns the integer cost of this item.
        """
        # If the equipment is in multi-upgrade mode, return the cost directly.
        if self.equipment.upgrade_mode == ContentEquipment.UpgradeMode.MULTI:
            return self.cost

        # Otherwise, sum the costs of all upgrades up to this position.
        upgrades = self.equipment.upgrades.filter(position__lte=self.position)
        return sum(upgrade.cost for upgrade in upgrades)

    @cached_property
    def cost_int_cached(self):
        return self.cost_int()

    def cost_display(self):
        """
        Returns a cost display string with '¢'.
        """
        return f"{self.cost_int_cached}¢"

    class Meta:
        verbose_name = "Equipment Upgrade"
        verbose_name_plural = "Equipment Upgrades"
        ordering = ["equipment__name", "name"]
        unique_together = ["equipment", "name"]

    def __str__(self):
        return f"{self.equipment.upgrade_stack_name or 'Upgrade'} – {self.name}"


class ContentFighterDefaultAssignment(Content):
    """
    Associates a fighter with a piece of equipment by default, including weapon profiles.
    """

    help_text = "Captures the default equipment assignments for a fighter."
    fighter = models.ForeignKey(
        ContentFighter,
        on_delete=models.CASCADE,
        db_index=True,
        related_name="default_assignments",
    )
    equipment = models.ForeignKey(
        ContentEquipment, on_delete=models.CASCADE, db_index=True
    )
    weapon_profiles_field = models.ManyToManyField(
        ContentWeaponProfile,
        blank=True,
    )
    weapon_accessories_field = models.ManyToManyField(
        ContentWeaponAccessory,
        blank=True,
    )
    cost = models.IntegerField(
        default=0, help_text="You typically should not overwrite this."
    )
    history = HistoricalRecords()

    def cost_int(self):
        """
        Returns the integer cost of this item.
        """
        return self.cost

    def cost_display(self):
        """
        Returns a cost display string with '¢'.
        """
        return f"{self.cost}¢"

    def is_weapon(self):
        return self.equipment.is_weapon()

    def all_profiles(self):
        """Return all profiles for the equipment, including the default profiles."""
        standard_profiles = self.standard_profiles_cached
        weapon_profiles = self.weapon_profiles_cached

        seen = set()
        result = []
        for p in standard_profiles + weapon_profiles:
            if p.id not in seen:
                seen.add(p.id)
                result.append(p)
        return result

    def standard_profiles(self):
        return [
            VirtualWeaponProfile(p, self._mods)
            for p in ContentWeaponProfile.objects.filter(
                equipment=self.equipment, cost=0
            )
        ]

    @cached_property
    def standard_profiles_cached(self):
        return list(self.standard_profiles())

    def weapon_profiles(self):
        return [
            VirtualWeaponProfile(p, self._mods)
            for p in self.weapon_profiles_field.all()
        ]

    @cached_property
    def weapon_profiles_cached(self):
        return list(self.weapon_profiles())

    # Accessories

    def weapon_accessories(self):
        return list(self.weapon_accessories_field.all())

    @cached_property
    def weapon_accessories_cached(self):
        return self.weapon_accessories()

    # Mods

    @cached_property
    def _mods(self):
        accessories = self.weapon_accessories_cached
        mods = [m for a in accessories for m in a.modifiers.all()]
        return mods

    # Behaviour

    def __str__(self):
        return f"{self.fighter} – {self.name()}"

    def name(self):
        profiles_names = ", ".join(
            [profile.name for profile in self.weapon_profiles_cached]
        )
        return f"{self.equipment}" + (f" ({profiles_names})" if profiles_names else "")

    class Meta:
        verbose_name = "Default Equipment Assignment"
        verbose_name_plural = "Default Equipment Assignments"
        ordering = ["fighter__type", "equipment__name"]

    def clean(self):
        """
        Validation to ensure cost is not negative and that any weapon profiles
        are associated with the correct equipment.
        """
        if self.cost_int() < 0:
            raise ValidationError("Cost cannot be negative.")

        for profile in self.weapon_profiles_field.all():
            if profile.equipment != self.equipment:
                raise ValidationError("Weapon profiles must be for the same equipment.")


class ContentFighterHouseOverride(Content):
    """
    Captures cases where a fighter has specific modifications (i.e. cost) when being added to
    a specific house.
    """

    fighter = models.ForeignKey(
        ContentFighter,
        on_delete=models.CASCADE,
        db_index=True,
        related_name="house_overrides",
    )
    house = models.ForeignKey(
        ContentHouse,
        on_delete=models.CASCADE,
        db_index=True,
        related_name="fighter_overrides",
    )
    cost = models.IntegerField(
        null=True,
        blank=True,
        help_text="What should this Fighter cost when added to this House?",
    )

    class Meta:
        verbose_name = "Fighter-House Override"
        verbose_name_plural = "Fighter-House Overrides"
        ordering = ["house__name", "fighter__type"]
        unique_together = ["fighter", "house"]

    def __str__(self):
        return f"{self.fighter} for {self.house}"


def check(rule, category, name):
    """
    Check if the rule applies to the given category and name.
    A rule matches if its 'category' and 'name' entries are either
    None or match the input.
    """
    dc = rule.get("category") in [None, category]
    dn = rule.get("name") in [None, name]
    return dc and dn


class ContentPolicy(Content):
    """
    Captures rules for restricting or allowing certain equipment to fighters.
    """

    help_text = (
        "Not used currently. Captures the rules for equipment availability to fighters."
    )
    fighter = models.ForeignKey(ContentFighter, on_delete=models.CASCADE, db_index=True)
    rules = models.JSONField()
    history = HistoricalRecords()

    def allows(self, equipment: ContentEquipment) -> bool:
        """
        Determines if the equipment is allowed by the policy. This is evaluated
        by checking rules from last to first.
        """
        name = equipment.name
        # TODO: This won't work — this model should be dropped for now as it's not used
        #       and is deadwood.
        category = equipment.category.name
        # Work through the rules in reverse order. If any of them
        # allow, then the equipment is allowed.
        # If we get to an explicit deny, then the equipment is denied.
        # If we get to the end, then the equipment is allowed.
        for rule in reversed(self.rules):
            deny = rule.get("deny", [])
            if deny == "all":
                return False
            # The deny rule is an AND rule. The category and name must
            # both match, or be missing, for the rule to apply.
            deny_fail = any([check(d, category, name) for d in deny])
            if deny_fail:
                return False

            allow = rule.get("allow", [])
            if allow == "all":
                return True
            # The allow rule is an AND rule. The category and name must
            # both match, or be missing, for the allow to apply.
            allow_pass = any([check(a, category, name) for a in allow])
            if allow_pass:
                return True

        return True

    class Meta:
        verbose_name = "Policy"
        verbose_name_plural = "Policies"


class ContentBook(Content):
    """
    Represents a rulebook, including its name, shortname, year of publication,
    and whether it is obsolete.
    """

    help_text = "Captures rulebook information."
    name = models.CharField(max_length=255)
    shortname = models.CharField(max_length=50, blank=True, null=False)
    year = models.CharField(blank=True, null=False)
    description = models.TextField(blank=True, null=False)
    type = models.CharField(max_length=50, blank=True, null=False)
    obsolete = models.BooleanField(default=False)
    history = HistoricalRecords()

    def __str__(self):
        return f"{self.name} ({self.type}, {self.year})"

    class Meta:
        verbose_name = "Book"
        verbose_name_plural = "Books"
        ordering = ["name"]


def similar(a, b):
    """
    Returns a similarity ratio between two strings, ignoring case.
    If one is contained in the other, returns 0.9 for partial matches,
    or 1.0 if they are identical.
    """
    lower_a = a.lower()
    lower_b = b.lower()
    if lower_a == lower_b:
        return 1.0
    if lower_a in lower_b or lower_b in lower_a:
        return 0.9
    return SequenceMatcher(None, a, b).ratio()


class ContentPageRef(Content):
    """
    Represents a reference to a page (or pages) in a rulebook (:model:`content.ContentBook`). Provides a parent
    relationship for nested references, used to resolve page numbers.
    """

    help_text = "Captures the page references for game content. Title is used to match with other entities (e.g. Skills)."
    book = models.ForeignKey(ContentBook, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    page = models.CharField(max_length=50, blank=True, null=False)
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="children"
    )
    category = models.CharField(max_length=255, blank=True, null=False)
    description = models.TextField(blank=True, null=False)
    history = HistoricalRecords()

    def __str__(self):
        return f"{self.book.shortname} - {self.category} - p{self.resolve_page_cached} - {self.title}".strip()

    def bookref(self):
        """
        Returns a short, human-readable reference string combining the
        book shortname and resolved page number.
        """
        return f"{self.book.shortname} p{self.resolve_page_cached}".strip()

    def resolve_page(self):
        """
        If the page field is empty, attempts to resolve the page
        through its parent. Returns None if no page can be resolved.
        """
        if self.page:
            return self.page

        if self.parent:
            return self.parent.resolve_page_cached

        return None

    @cached_property
    def resolve_page_cached(self):
        return self.resolve_page()

    class Meta:
        verbose_name = "Page Reference"
        verbose_name_plural = "Page References"
        ordering = ["category", "book__name", "title"]

    # TODO: Move this to a custom Manager
    @classmethod
    def find(cls, *args, **kwargs):
        """
        Finds a single page reference matching the given query parameters.
        Returns the first match or None if no match is found.
        """
        return ContentPageRef.objects.filter(*args, **kwargs).first()

    # TODO: Move this to a custom Manager
    @classmethod
    def find_similar(cls, title: str, **kwargs):
        """
        Finds references whose titles match or are similar to the given string.
        Uses caching to avoid repeated lookups. Returns a QuerySet.
        """
        cache = caches["content_page_ref_cache"]
        key = f"content_page_ref_cache:{title}"
        cached = cache.get(key)
        if cached:
            return cached

        refs = ContentPageRef.objects.filter(**kwargs).filter(
            Q(title__icontains=title) | Q(title=title)
        )
        cache.set(key, refs)
        return refs

    # TODO: Move this to a custom Manager
    @classmethod
    def all_ordered(cls):
        """
        Returns top-level page references (no parent) with numeric pages, ordered by:
        - Core book first
        - Then by book shortname
        - Then ascending by numeric page
        """
        return (
            # TODO: Implement this as a method on the Manager/QuerySet
            ContentPageRef.objects.filter(parent__isnull=True)
            .exclude(page="")
            .annotate(page_int=Cast("page", models.IntegerField(null=True, blank=True)))
            .order_by(
                Case(
                    When(book__shortname="Core", then=0),
                    default=99,
                ),
                "book__shortname",
                "page_int",
            )
        )

    # TODO: Add default ordering to the Meta class, possibly with default annotations from the Manager
    def children_ordered(self):
        """
        Returns any child references of this reference that have a page specified,
        ordered similarly (Core first, then shortname, then ascending page, then title).
        """
        return (
            self.children.exclude(page="")
            .annotate(page_int=Cast("page", models.IntegerField(null=True, blank=True)))
            .order_by(
                Case(
                    When(book__shortname="Core", then=0),
                    default=99,
                ),
                "book__shortname",
                "page_int",
                "title",
            )
        )

    def children_no_page(self):
        """
        Returns any child references of this reference that do not have a page
        specified, ordered similarly (Core first, then shortname, then title).
        """
        return self.children.filter(page="").order_by(
            Case(
                When(book__shortname="Core", then=0),
                default=99,
            ),
            "book__shortname",
            "title",
        )


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
    ]

    def apply(self, input_value: str) -> str:
        """
        Apply the modification to a given value.
        """

        if self.mode == "set":
            return self.value

        direction = 1 if self.mode == "improve" else -1
        # For some stats, we need to reverse the direction
        # e.g. if the stat is a target roll value
        if self.stat in self.inverted_stats:
            direction = -direction

        # Stats can be:
        #   - (meaning 0)
        #   X" (meaning X inches) — Rng
        #   X (meaning X) — Str, D
        #   S (meaning fighter Str) — Str
        #   S+X (meaning fighter Str+X) — Str
        #   +X (meaning add X to roll) — Acc and Ap
        #   X+ (meaning target X on roll) — Am
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
        elif self.stat in self.inch_stats:
            # Inches
            return f'{output_str}"'
        elif self.stat in self.modifier_stats:
            # Modifier
            if mod_value > 0:
                return f"+{output_str}"
            return f"{output_str}"
        elif self.stat in self.target_roll_stats:
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
    Weapon stat modifier
    """

    help_text = "A modification to a specific value in a weapon statline"
    stat = models.CharField(
        max_length=50,
        choices=[
            ("movement", "Movement"),
            ("weapon_skill", "Weapon Skill"),
            ("ballistic_skill", "Ballistic Skill"),
            ("strength", "Strength"),
            ("toughness", "Toughness"),
            ("wounds", "Wounds"),
            ("initiative", "Initiative"),
            ("attacks", "Attacks"),
            ("leadership", "Leadership"),
            ("cool", "Cool"),
            ("willpower", "Willpower"),
            ("intelligence", "Intelligence"),
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
        return f"{mode_choices[self.mode]} fighter {stat_choices[self.stat]} by {self.value}"

    class Meta:
        verbose_name = "Fighter Stat Modifier"
        verbose_name_plural = "Fighter Stat Modifiers"
        ordering = ["stat"]


class ContentModTrait(ContentMod):
    """
    Trait modifier
    """

    help_text = "A modification to a weapon trait"
    trait = models.ForeignKey(
        ContentWeaponTrait,
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
        ContentRule,
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
        ContentSkill,
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


@dataclass
class VirtualWeaponProfile:
    """
    A virtual container for profiles that applies mods.
    """

    profile: ContentWeaponProfile
    mods: list[ContentMod] = field(default_factory=list)

    @property
    def id(self):
        return self.profile.id

    @property
    def name(self):
        return self.profile.name

    def cost_int(self):
        return self.profile.cost_int()

    def cost_display(self):
        return f"{self.cost_int()}¢"

    def _statmods(self, stat=None) -> list[ContentModStat]:
        return [
            mod
            for mod in self.mods
            if isinstance(mod, ContentModStat) and (stat is None or mod.stat == stat)
        ]

    def _traitmods(self) -> list[ContentModTrait]:
        return [mod for mod in self.mods if isinstance(mod, ContentModTrait)]

    def __post_init__(self):
        stats = [
            "range_short",
            "range_long",
            "accuracy_short",
            "accuracy_long",
            "strength",
            "armour_piercing",
            "damage",
            "ammo",
        ]
        for stat in stats:
            value = self.profile.__getattribute__(stat)
            setattr(
                self,
                stat,
                self._apply_mods(stat, value, self._statmods(stat=stat)),
            )

    def _apply_mods(self, stat: str, value: str, mods: list[ContentModStat]):
        for mod in mods:
            value = mod.apply(value)
        return value

    @property
    def traits(self):
        mods = self._traitmods()
        value = list(self.profile.traits.all())
        for mod in mods:
            if mod.mode == "add" and mod.trait not in value:
                value.append(mod.trait)
            elif mod.mode == "remove" and mod.trait in value:
                value.remove(mod.trait)
        return value

    def statline(self):
        statline = self.profile.statline()
        output = []
        for stat in statline:
            base_value = stat.value
            value = getattr(self, stat.field_name) or "-"
            if value != base_value:
                stat = replace(stat, value=value, modded=True)
            output.append(stat)
        return output

    def traitline(self):
        # TODO: We need some kind of TraitDisplay thing
        return sorted([trait.name for trait in self.traits])

    @cached_property
    def traitline_cached(self):
        return self.traitline()

    @cached_property
    def rarity(self):
        return self.profile.rarity

    @cached_property
    def rarity_roll(self):
        return self.profile.rarity_roll

    def __str__(self):
        return self.name()

    def __eq__(self, value):
        return self.profile == value
