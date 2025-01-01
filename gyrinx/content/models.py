from difflib import SequenceMatcher

from django.core.cache import caches
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Case, Q, When
from django.db.models.functions import Cast
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

    def fighters(self):
        return self.contentfighter_set.all().order_by(
            Case(
                When(category="LEADER", then=0),
                When(category="CHAMPION", then=1),
                When(category="PROSPECT", then=2),
                When(category="JUVE", then=3),
                default=99,
            ),
            "type",
        )

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "House"
        verbose_name_plural = "Houses"
        ordering = ["name"]


class ContentSkill(Content):
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=255, default="None")
    history = HistoricalRecords()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Skill"
        verbose_name_plural = "Skills"
        ordering = ["name"]


class ContentRule(Content):
    name = models.CharField(max_length=255)
    # TODO: Page refs

    history = HistoricalRecords()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Rule"
        verbose_name_plural = "Rules"
        ordering = ["name"]


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

    def cost_display(self):
        if not self.cost:
            return ""
        return f"{self.cost}¢"

    def cat(self):
        return EquipmentCategoryChoices[self.category].label

    def is_weapon(self):
        return ContentWeaponProfile.objects.filter(equipment=self).exists()

    def profiles(self):
        return self.contentweaponprofile_set.all().order_by(
            Case(
                When(name="", then=0),
                default=1,
            ),
            "cost",
        )

    class Meta:
        verbose_name = "Equipment"
        verbose_name_plural = "Equipment"
        unique_together = ["name", "category"]
        ordering = ["name"]


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

    def cost_int(self):
        return int(self.cost())

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
                "classes": ("border-start" if field.name in ["leadership"] else ""),
            }
            for field in stats
        ]

    def ruleline(self):
        return [rule.name for rule in self.rules.all()]

    class Meta:
        verbose_name = "Fighter"
        verbose_name_plural = "Fighters"
        ordering = ["house__name", "type"]


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

    def cost_int(self):
        return self.cost

    def cost_display(self):
        return f"{self.cost}¢"

    def __str__(self):
        return f"{self.fighter} {self.weapon_profile if self.weapon_profile else ''} ({self.cost})"

    class Meta:
        verbose_name = "Equipment List Item"
        verbose_name_plural = "Equipment List Items"
        unique_together = ["fighter", "equipment", "weapon_profile"]
        ordering = ["fighter__type", "equipment__name"]

    def clean(self):
        if self.cost_int() < 0:
            raise ValidationError("Cost cannot be negative.")

        if self.weapon_profile and self.weapon_profile.equipment != self.equipment:
            raise ValidationError("Weapon profile must be for the same equipment.")


class ContentWeaponTrait(Content):
    name = models.CharField(max_length=255, unique=True)
    history = HistoricalRecords()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Weapon Trait"
        verbose_name_plural = "Weapon Traits"
        ordering = ["name"]


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

    def cost_tp(self) -> int | None:
        # If the cost is zero, then the profile is free to use and "standard".
        # Note: this will not be shown in the Trading Post, because it's free. Only the base
        # equipment will be shown.
        if self.cost_int() == 0:
            return None

        # If the cost is positive, then the profile is an upgrade to the equipment.
        if self.cost_sign == "+":
            return self.equipment.cost_int() + self.cost_int()

        # Otherwise, the cost is the profile cost.
        # TODO: When is this a thing?
        return self.cost_int()

    def cost_display(self) -> str:
        if self.name == "" or self.cost_int() == 0:
            return ""
        return f"{self.cost_sign}{self.cost_int()}¢"

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
        return [trait.name for trait in self.traits.all()]

    class Meta:
        verbose_name = "Weapon Profile"
        verbose_name_plural = "Weapon Profiles"
        unique_together = ["equipment", "name"]
        ordering = ["equipment__name", "name"]

    def clean(self):
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


class ContentBook(Content):
    help_text = "The Content Book captures the rulebook information."
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
    lower_a = a.lower()
    lower_b = b.lower()
    if lower_a == lower_b:
        return 1.0
    if lower_a in lower_b or lower_b in lower_a:
        return 0.9
    return SequenceMatcher(None, a, b).ratio()


class ContentPageRef(Content):
    help_text = "The Content Page Ref captures the page references for game content."
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
        return f"{self.book.shortname} p{self.resolve_page()}".strip()

    def resolve_page(self):
        if self.page:
            return self.page

        if self.parent:
            return self.parent.resolve_page()

        return None

    class Meta:
        verbose_name = "Page Reference"
        verbose_name_plural = "Page References"
        ordering = ["category", "book__name", "title"]

    @classmethod
    def find(cls, *args, **kwargs):
        return ContentPageRef.objects.filter(*args, **kwargs).first()

    @classmethod
    def find_similar(cls, title: str, **kwargs):
        cache = caches["content_page_ref_cache"]
        key = f"content_page_ref_cache:{title}"
        cached = cache.get(key)
        if cached:
            return cached

        refs = ContentPageRef.objects.filter(**kwargs).filter(
            Q(title__icontains=title) | Q(title=title)
        )

        # list = sorted(
        #     refs,
        #     key=lambda ref: similar(ref.title.lower(), title.lower()),
        #     reverse=True,
        # )
        # top_10 = list[0:10]
        # result = [
        #     ref for ref in top_10 if similar(ref.title.lower(), title.lower()) > 0.8
        # ]
        cache.set(key, refs)
        return refs

    @classmethod
    def all_ordered(cls):
        return (
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

    def children_ordered(self):
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
        return self.children.filter(page="").order_by(
            Case(
                When(book__shortname="Core", then=0),
                default=99,
            ),
            "book__shortname",
            "title",
        )
