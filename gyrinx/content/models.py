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
        verbose_name = "Content House"
        verbose_name_plural = "Content Houses"


class ContentSkill(Content):
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=255, default="None")
    history = HistoricalRecords()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Content Skill"
        verbose_name_plural = "Content Skills"


class ContentEquipment(Content):
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=255, choices=EquipmentCategoryChoices)
    trading_post_available = models.BooleanField(
        default=False, help_text="Is the equipment available at the Trading Post?"
    )
    trading_post_cost = models.IntegerField(
        help_text="The cost of the equipment at the Trading Post.",
        blank=True,
        null=True,
    )
    history = HistoricalRecords()

    def __str__(self):
        return self.name

    def cost(self):
        return self.trading_post_cost

    class Meta:
        verbose_name = "Content Equipment"
        verbose_name_plural = "Content Equipment"


class ContentFighter(Content):
    help_text = "The Content Fighter captures the archetypal information about a fighter from the rulebooks."
    type = models.CharField(max_length=255)
    category = models.CharField(max_length=255, choices=FighterCategoryChoices)
    house = models.ForeignKey(
        ContentHouse, on_delete=models.CASCADE, null=True, blank=True
    )
    equipment = models.ManyToManyField(
        ContentEquipment, through="ContentFighterEquipmentAssignment"
    )
    skills = models.ManyToManyField(ContentSkill, blank=True)
    base_cost = models.IntegerField(default=0)
    history = HistoricalRecords()

    def __str__(self):
        house = f"{self.house}" if self.house else ""
        return f"{house} {self.type} ({self.category})".strip()

    def cost(self):
        # The equipment is a many-to-many field, and the through model contains
        # the quantity of each piece of equipment. We need to sum the cost of
        # each piece of equipment and the quantity.
        return self.base_cost + sum(
            [e.cost() for e in self.equipment.through.objects.filter(fighter=self)]
        )

    class Meta:
        verbose_name = "Content Fighter"
        verbose_name_plural = "Content Fighters"


class ContentFighterEquipmentAssignment(Content):
    help_text = "The Content Fighter Equipment Assignment captures the default equipment assigned to a fighter in the rulebook."
    fighter = models.ForeignKey(ContentFighter, on_delete=models.CASCADE, db_index=True)
    equipment = models.ForeignKey(
        ContentEquipment, on_delete=models.CASCADE, db_index=True
    )
    qty = models.IntegerField(default=0)
    history = HistoricalRecords()

    def cost(self):
        return self.qty * self.equipment.cost()

    def __str__(self):
        return f"{self.fighter} {self.equipment} Equipment Assignment ({self.qty})"

    class Meta:
        verbose_name = "Content Fighter Equipment Assignment"
        verbose_name_plural = "Content Fighter Equipment Assignments"
        unique_together = ["fighter", "equipment"]


class ContentFighterEquipment(Content):
    help_text = "The Content Fighter Equipment captures the equipment list available to a fighter in the rulebook."
    fighter = models.ForeignKey(ContentFighter, on_delete=models.CASCADE, db_index=True)
    equipment = models.ForeignKey(
        ContentEquipment, on_delete=models.CASCADE, db_index=True
    )
    cost = models.IntegerField(default=0)
    history = HistoricalRecords()

    def __str__(self):
        return f"{self.fighter} Equipment"

    class Meta:
        verbose_name = "Content Fighter Equipment List"
        verbose_name_plural = "Content Fighter Equipment Lists"
        unique_together = ["fighter", "equipment"]


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
        verbose_name = "Content Policy"
        verbose_name_plural = "Content Policies"
