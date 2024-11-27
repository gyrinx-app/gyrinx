from django.db import models
from simple_history.models import HistoricalRecords

from gyrinx.models import Base, EquipmentCategoryChoices, FighterCategoryChoices

##
## Content Models
##


class Content(Base):
    class Meta:
        abstract = True


class ContentHouse(Content):
    help_text = "The Content House identifies the house or faction of a fighter."
    name = models.CharField(max_length=255)
    history = HistoricalRecords()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "House"
        verbose_name_plural = "Houses"


class ContentSkill(Content):
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=255, default="None")
    history = HistoricalRecords()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Skill"
        verbose_name_plural = "Skills"


class ContentRule(Content):
    name = models.CharField(max_length=255)
    # TODO: Page refs

    history = HistoricalRecords()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Rule"
        verbose_name_plural = "Rules"


class ContentEquipment(Content):
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=255, choices=EquipmentCategoryChoices)

    cost = models.CharField(
        help_text="The credit cost of the equipment at the Trading Post. Note that, in weapons, this is overridden by the 'Standard' weapon profile cost.",
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
    )
    rarity_roll = models.IntegerField(
        blank=True,
        null=True,
    )

    history = HistoricalRecords()

    def __str__(self):
        return self.name

    def cost_int(self):
        if not self.cost:
            return 0
        return int(self.cost)

    def cat(self):
        return EquipmentCategoryChoices[self.category].label

    class Meta:
        verbose_name = "Equipment"
        verbose_name_plural = "Equipment"
        unique_together = ["name", "category"]


class ContentFighter(Content):
    help_text = "The Content Fighter captures the archetypal information about a fighter from the rulebooks."
    type = models.CharField(max_length=255)
    category = models.CharField(max_length=255, choices=FighterCategoryChoices)
    house = models.ForeignKey(
        ContentHouse, on_delete=models.CASCADE, null=True, blank=True
    )
    skills = models.ManyToManyField(ContentSkill, blank=True)
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
        house = f"{self.house}" if self.house else ""
        return f"{house} {self.type} ({FighterCategoryChoices[self.category].label})".strip()

    def cat(self):
        return FighterCategoryChoices[self.category].label

    def name(self):
        return f"{self.type} ({self.cat()})"

    def cost(self):
        # TODO: This might be completely wrong — do we actually want to copy over the item to the fighter at purchase time?
        # The equipment is a many-to-many field, and the through model contains
        # the quantity of each piece of equipment. We need to sum the cost of
        # each piece of equipment and the quantity.
        # return self.base_cost + sum(
        #     [e.cost() for e in self.equipment.through.objects.filter(fighter=self)]
        # )
        return self.base_cost

    def statline(self):
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
            }
            for field in stats
        ]

    def ruleline(self):
        return [rule.name for rule in self.rules.all()]

    class Meta:
        verbose_name = "Fighter"
        verbose_name_plural = "Fighters"


class ContentFighterEquipmentListItem(Content):
    help_text = "The Content Fighter Equipment captures the equipment list available to a fighter in the rulebook."
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

    def __str__(self):
        return f"{self.fighter} {self.weapon_profile if self.weapon_profile else ''} ({self.cost})"

    class Meta:
        verbose_name = "Equipment List Item"
        verbose_name_plural = "Equipment List Items"
        unique_together = ["fighter", "equipment", "weapon_profile"]


class ContentWeaponTrait(Content):
    name = models.CharField(max_length=255, unique=True)
    history = HistoricalRecords()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Weapon Trait"
        verbose_name_plural = "Weapon Traits"


class ContentWeaponProfile(Content):
    equipment = models.ForeignKey(
        ContentEquipment,
        on_delete=models.CASCADE,
        db_index=True,
        null=True,
        blank=False,
    )

    name = models.CharField(max_length=255, blank=True)
    help_text = (
        "The Content Weapon Profile captures the profile information for a weapon."
    )

    # If the cost is zero, then the profile is free to use and "standard".
    cost = models.IntegerField(
        default=0,
        help_text="The credit cost of the weapon profile at the Trading Post. If the cost is zero, then the profile is free to use and standard. Note that this can be overridden in a fighter's equipment list.",
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
    )
    rarity_roll = models.IntegerField(
        blank=True,
        null=True,
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
        return self.cost

    def statline(self):
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
            {"name": field.verbose_name, "value": getattr(self, field.name) or "-"}
            for field in stats
        ]

    class Meta:
        verbose_name = "Weapon Profile"
        verbose_name_plural = "Weapon Profiles"
        unique_together = ["equipment", "name"]


def check(rule, category, name):
    """Check if the rule applies to the category and name."""
    dc = rule.get("category") in [None, category]
    dn = rule.get("name") in [None, name]
    return dc and dn


class ContentPolicy(Content):
    help_text = (
        "The Content Policy captures the rules for equipment availability to fighters."
    )
    fighter = models.ForeignKey(ContentFighter, on_delete=models.CASCADE, db_index=True)
    rules = models.JSONField()
    history = HistoricalRecords()

    def allows(self, equipment: ContentEquipment) -> bool:
        """Check if the policy allows the equipment."""
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
