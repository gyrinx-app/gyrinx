"""
Models and utilities for managing fighter, equipment, rules, and related
content in Necromunda.

This module includes abstract base classes for shared data, plus concrete
models for fighters, equipment, rules, and more. Custom managers and querysets
provide streamlined data access.
"""

from difflib import SequenceMatcher

from django.core.cache import caches
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Case, Exists, OuterRef, Q, Subquery, When
from django.db.models.functions import Cast, Coalesce
from simple_history.models import HistoricalRecords

from gyrinx.models import Base, EquipmentCategoryChoices, FighterCategoryChoices

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

    name = models.CharField(max_length=255)
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
        return f"{self.name} ({self.category})"

    class Meta:
        verbose_name = "Skill"
        verbose_name_plural = "Skills"
        ordering = ["category", "name"]


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
                        Q(cost__regex=r"^\d+$"),
                        then=Cast("cost", models.IntegerField()),
                    ),
                    default=0,
                ),
                has_weapon_profiles=Exists(
                    ContentWeaponProfile.objects.filter(equipment=OuterRef("pk"))
                ),
            )
            .order_by("category", "name", "id")
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


class ContentEquipment(Content):
    """
    Represents an item of equipment that a fighter may acquire.
    Can be a weapon or other piece of gear. Cost and rarity are tracked.
    """

    name = models.CharField(max_length=255)
    category = models.CharField(max_length=255, choices=EquipmentCategoryChoices)

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
            ("C", "Common (C)"),
        ],
        blank=True,
        default="C",
        help_text="Use 'E' to exclude this equipment from the Trading Post.",
        verbose_name="Availability",
    )
    rarity_roll = models.IntegerField(
        blank=True, null=True, verbose_name="Availability Level"
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
        if not str(self.cost).isnumeric():
            return 0
        return int(self.cost)

    def cost_display(self):
        """
        Returns a readable cost string with a '¢' suffix.
        """
        if not str(self.cost).isnumeric():
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
        return EquipmentCategoryChoices[self.category].label

    def is_weapon(self):
        """
        Indicates whether this equipment is a weapon. If 'has_weapon_profiles'
        is annotated, uses that; otherwise checks the database.
        """
        if hasattr(self, "has_weapon_profiles"):
            return self.has_weapon_profiles
        return ContentWeaponProfile.objects.filter(equipment=self).exists()

    def profiles(self):
        """
        Returns all associated weapon profiles for this equipment.
        """
        return self.contentweaponprofile_set.all()

    def profiles_for_fighter(self, content_fighter):
        """
        Returns all weapon profiles for this equipment, annotated with
        fighter-specific cost if available.
        """
        return self.contentweaponprofile_set.with_cost_for_fighter(content_fighter)

    class Meta:
        verbose_name = "Equipment"
        verbose_name_plural = "Equipment"
        unique_together = ["name", "category"]
        ordering = ["name"]

    def clean(self):
        self.name = self.name.strip()
        if self.cost_int() < 0:
            raise ValidationError("Cost cannot be negative.")

    objects = ContentEquipmentManager.from_queryset(ContentEquipmentQuerySet)()


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

    def statline(self):
        """
        Returns a list of dictionaries describing the fighter's core stats,
        with additional styling indicators.
        """
        stats = [
            self._meta.get_field(field)
            for field in [
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
                "name": field.verbose_name,
                "value": getattr(self, field.name) or "-",
                "highlight": bool(
                    field.name in ["leadership", "cool", "willpower", "intelligence"]
                ),
                "classes": ("border-start" if field.name in ["leadership"] else ""),
            }
            for field in stats
        ]

    def ruleline(self):
        """
        Returns a list of rule names associated with this fighter.
        """
        return [rule.name for rule in self.rules.all()]

    class Meta:
        verbose_name = "Fighter"
        verbose_name_plural = "Fighters"
        ordering = [
            "house__name",
            Case(
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
            ),
            "type",
        ]


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
        return f"{self.fighter} {self.weapon_profile if self.weapon_profile else ''} ({self.cost})"

    class Meta:
        verbose_name = "Equipment List Item"
        verbose_name_plural = "Equipment List Items"
        unique_together = ["fighter", "equipment", "weapon_profile"]
        ordering = ["fighter__type", "equipment__name"]

    def clean(self):
        """
        Validation to ensure cost is not negative and that any weapon profile
        matches the correct equipment.
        """
        if self.cost_int() < 0:
            raise ValidationError("Cost cannot be negative.")

        if self.weapon_profile and self.weapon_profile.equipment != self.equipment:
            raise ValidationError("Weapon profile must be for the same equipment.")


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


class ContentWeaponProfileManager(models.Manager):
    """
    Custom manager for :model:`content.ContentWeaponProfile` model. Currently unused but available
    for future extensions.
    """

    pass


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
    cost_sign = models.CharField(
        max_length=1,
        choices=[("+", "+")],
        blank=True,
        null=False,
        default="",
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
    )
    rarity_roll = models.IntegerField(blank=True, null=True)

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

    def cost_tp(self) -> int | None:
        """
        Determines the cost if purchased at the Trading Post. Returns None if
        standard (zero cost), or a sum if the cost sign is '+', or just the
        cost otherwise.
        """
        if self.cost_int() == 0:
            return None

        # If the cost is positive, then the profile is an upgrade to the equipment.
        if self.cost_sign == "+":
            return self.equipment.cost_int() + self.cost_int()

        # Otherwise, the cost is the profile cost.
        # TODO: When is this a thing?
        return self.cost_int()

    def cost_display(self) -> str:
        """
        Returns a readable display for the cost, including any sign and '¢'.
        """
        if self.name == "" or self.cost_int() == 0:
            return ""
        return f"{self.cost_sign}{self.cost_int()}¢"

    def cost_for_fighter_int(self):
        if hasattr(self, "cost_for_fighter"):
            return self.cost_for_fighter

        raise AttributeError(
            "cost_for_fighter not available. Use with_cost_for_fighter()"
        )

    def statline(self):
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
            {
                "name": field.verbose_name,
                "classes": (
                    "border-start"
                    if field.name in ["accuracy_short", "strength"]
                    else ""
                ),
                "value": getattr(self, field.name) or "-",
            }
            for field in stats
        ]

    def traitline(self):
        """
        Returns a list of weapon trait names associated with this profile.
        """
        return [trait.name for trait in self.traits.all()]

    class Meta:
        verbose_name = "Weapon Profile"
        verbose_name_plural = "Weapon Profiles"
        unique_together = ["equipment", "name"]
        ordering = [
            "equipment__name",
            Case(
                When(name="", then=0),
                default=99,
            ),
            "cost",
        ]

    def clean(self):
        """
        Validation to ensure appropriate costs and cost signs for standard
        vs non-standard weapon profiles.
        """
        print("model clean", self)
        self.name = self.name.strip()

        if self.name.startswith("-"):
            raise ValidationError("Name should not start with a hyphen.")

        if self.name == "(Standard)":
            raise ValidationError('Name should not be "(Standard)".')

        # Ensure that specific fields are not hyphens
        for field in [
            "range_short",
            "range_long",
            "accuracy_short",
            "accuracy_long",
            "strength",
            "armour_piercing",
            "damage",
            "ammo",
        ]:
            setattr(self, field, getattr(self, field).strip())
            value = getattr(self, field)
            if value == "-":
                setattr(self, field, "")

            if field in [
                "range_short",
                "range_long",
            ]:
                if value and value[0].isdigit() and not value.endswith('"'):
                    setattr(self, field, f'{value}"')

        if self.cost_int() < 0:
            raise ValidationError("Cost cannot be negative.")

        if self.cost_int() == 0 and self.cost_sign != "":
            raise ValidationError("Cost sign should be empty for zero cost profiles.")

        if self.name == "" and self.cost_int() != 0:
            raise ValidationError("Standard profiles should have zero cost.")

        if self.cost_int() == 0 and self.cost_sign != "":
            raise ValidationError("Standard profiles should have zero cost.")

        if self.cost_int() != 0 and self.cost_sign == "":
            raise ValidationError("Non-standard profiles should have a cost sign.")

        if self.cost_int() != 0 and self.cost_sign != "+":
            raise ValidationError(
                "Non-standard profiles should have a positive cost sign."
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
        standard_profiles = list(self.standard_profiles())
        weapon_profiles = self.weapon_profiles()

        seen = set()
        result = []
        for p in standard_profiles + weapon_profiles:
            if p.id not in seen:
                seen.add(p.id)
                result.append(p)
        return result

    def standard_profiles(self):
        return ContentWeaponProfile.objects.filter(equipment=self.equipment, cost=0)

    def weapon_profiles(self):
        return list(self.weapon_profiles_field.all())

    def weapon_accessories(self):
        return list(self.weapon_accessories_field.all())

    def __str__(self):
        return f"{self.fighter} – {self.name()}"

    def name(self):
        profiles_names = ", ".join([profile.name for profile in self.weapon_profiles()])
        return f"{self.equipment}" + (f" ({profiles_names})" if profiles_names else "")

    class Meta:
        verbose_name = "Default Assignment"
        verbose_name_plural = "Default Assignments"
        unique_together = ["fighter", "equipment"]
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
        category = equipment.category.label
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
        return f"{self.book.shortname} - {self.category} - p{self.resolve_page()} - {self.title}".strip()

    def bookref(self):
        """
        Returns a short, human-readable reference string combining the
        book shortname and resolved page number.
        """
        return f"{self.book.shortname} p{self.resolve_page()}".strip()

    def resolve_page(self):
        """
        If the page field is empty, attempts to resolve the page
        through its parent. Returns None if no page can be resolved.
        """
        if self.page:
            return self.page

        if self.parent:
            return self.parent.resolve_page()

        return None

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
