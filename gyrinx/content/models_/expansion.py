import logging
from dataclasses import dataclass
from typing import Optional

from django.db import models
from django.db.models import Case, When
from multiselectfield import MultiSelectField
from polymorphic.models import PolymorphicModel
from simple_history.models import HistoricalRecords

from gyrinx.content.models import (
    Content,
    ContentAttribute,
    ContentAttributeValue,
    ContentEquipment,
    ContentHouse,
)
from gyrinx.core.models.list import List, ListFighter
from gyrinx.models import (
    FighterCategoryChoices,
    format_cost_display,
)

logger = logging.getLogger(__name__)

##
## Equipment List Expansion Models
##


@dataclass
class ExpansionRuleInputs:
    """Inputs for evaluating equipment list expansion rules."""

    list: Optional[List] = None
    fighter: Optional[ListFighter] = None


class ContentEquipmentListExpansion(Content):
    """
    Represents an expansion to equipment lists based on certain conditions.
    When all rules match for a fighter/list, the expansion items become available.
    """

    help_text = "An expansion to equipment lists that applies based on gang attributes, house, or fighter categories."
    name = models.CharField(
        max_length=255, unique=True, help_text="Name of this equipment list expansion"
    )
    rules = models.ManyToManyField(
        "ContentEquipmentListExpansionRule",
        related_name="expansions",
        help_text="All rules must match (AND logic) for this expansion to apply",
    )

    history = HistoricalRecords()

    def applies_to(self, rule_inputs: ExpansionRuleInputs) -> bool:
        """
        Check if this expansion applies to the given list and fighter.
        All rules must match (AND logic).
        """

        # All rules must match
        for rule in self.rules.all():
            if not rule.match(rule_inputs):
                return False

        return True

    @classmethod
    def get_applicable_expansions(cls, rule_inputs: ExpansionRuleInputs):
        """
        Get all expansions that apply to the given rule inputs.
        """
        applicable = []
        for expansion in cls.objects.prefetch_related(
            "rules", "items__equipment"
        ).all():
            if expansion.applies_to(rule_inputs):
                applicable.append(expansion)
        return applicable

    @classmethod
    def get_expansion_equipment(cls, rule_inputs: ExpansionRuleInputs):
        """
        Get all equipment available from expansions based on rule inputs.
        Returns a queryset of ContentEquipment with cost annotations.
        """
        expansions = cls.get_applicable_expansions(rule_inputs)

        # Get all equipment IDs from applicable expansions
        equipment_ids = []
        cost_overrides = {}

        # Prefetch items to avoid N+1 queries
        prefetched_expansions = cls.objects.filter(
            id__in=[e.id for e in expansions]
        ).prefetch_related("items")

        for expansion in prefetched_expansions:
            for item in expansion.items.all():
                equipment_ids.append(item.equipment_id)
                if item.cost is not None:
                    # Store the cost override for this equipment
                    cost_overrides[item.equipment_id] = item.cost

        # Get the equipment and annotate with cost overrides
        equipment = ContentEquipment.objects.filter(id__in=equipment_ids)

        # Apply cost overrides using Case/When
        if cost_overrides:
            when_clauses = [
                When(id=eq_id, then=cost) for eq_id, cost in cost_overrides.items()
            ]
            equipment = equipment.annotate(
                expansion_cost_override=Case(
                    *when_clauses,
                    default=models.F("cost_cast_int"),
                    output_field=models.IntegerField(),
                )
            )
        else:
            equipment = equipment.annotate(
                expansion_cost_override=models.F("cost_cast_int")
            )

        return equipment

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Equipment List Expansion"
        verbose_name_plural = "Equipment List Expansions"
        ordering = ["name"]


class ContentEquipmentListExpansionItem(Content):
    """
    Represents a single equipment item that becomes available as part of an expansion.
    """

    help_text = "A piece of equipment that becomes available as part of an expansion."
    expansion = models.ForeignKey(
        ContentEquipmentListExpansion,
        on_delete=models.CASCADE,
        related_name="items",
        help_text="The expansion this item belongs to",
    )
    equipment = models.ForeignKey(
        ContentEquipment,
        on_delete=models.CASCADE,
        help_text="The equipment that becomes available",
    )
    cost = models.IntegerField(
        null=True,
        blank=True,
        help_text="Override cost for this equipment in the expansion (null = use base cost)",
    )

    history = HistoricalRecords()

    def __str__(self):
        cost_str = (
            f" ({format_cost_display(self.cost)})" if self.cost is not None else ""
        )
        return f"{self.equipment.name}{cost_str} in {self.expansion.name}"

    class Meta:
        verbose_name = "Equipment List Expansion Item"
        verbose_name_plural = "Equipment List Expansion Items"
        unique_together = ["expansion", "equipment"]
        ordering = ["expansion", "equipment__name"]


class ContentEquipmentListExpansionRule(PolymorphicModel, Content):
    """
    Base polymorphic model for expansion rules.
    Each subclass implements specific matching logic.
    """

    help_text = "Base class for equipment list expansion rules."
    history = HistoricalRecords()

    def match(self, rule_inputs) -> bool:
        """
        Check if this rule matches the given inputs.

        Args:
            rule_inputs: A dataclass containing the list and fighter to evaluate.

        Returns:
            bool: True if the rule matches, False otherwise.
        """
        raise NotImplementedError("Subclasses must implement match()")

    def __str__(self):
        return "Base Expansion Rule"

    class Meta:
        verbose_name = "Equipment List Expansion Rule"
        verbose_name_plural = "Equipment List Expansion Rules"


class ContentEquipmentListExpansionRuleByAttribute(ContentEquipmentListExpansionRule):
    """
    Rule that matches based on gang attributes.
    If no attribute values are specified, matches any value except "not set".
    """

    help_text = (
        "Rule that matches based on gang attributes (e.g., affiliation, alignment)."
    )
    attribute = models.ForeignKey(
        ContentAttribute,
        on_delete=models.CASCADE,
        help_text="The attribute to match on",
    )
    attribute_values = models.ManyToManyField(
        ContentAttributeValue,
        blank=True,
        help_text="Specific values to match (empty = any value except 'not set')",
    )

    def match(self, rule_inputs: ExpansionRuleInputs) -> bool:
        """Check if the list has the required attribute value."""
        list_obj: "List" = rule_inputs.list

        # Get the list's attribute values for this attribute
        list_values = list_obj.attributes.filter(
            attribute=self.attribute, listattributeassignment__archived=False
        )

        # If no list values, the rule doesn't match
        if not list_values.exists():
            return False

        # Get the specified values for this rule
        rule_values = self.attribute_values.all()

        # If no specific values specified, match any value (except not having the attribute)
        if not rule_values.exists():
            return True

        # Check if any of the list's values match the rule's values
        return any(list_value in rule_values for list_value in list_values)

    def __str__(self):
        values = self.attribute_values.all()
        if values.exists():
            values_str = ", ".join(str(v) for v in values[:3])
            if values.count() > 3:
                values_str += "..."
        else:
            values_str = "any"
        return f"Attribute Rule: {self.attribute} = {values_str}"

    class Meta:
        verbose_name = "Expansion Rule by Attribute"
        verbose_name_plural = "Expansion Rules by Attribute"


class ContentEquipmentListExpansionRuleByHouse(ContentEquipmentListExpansionRule):
    """
    Rule that matches based on the gang's house.
    """

    help_text = "Rule that matches based on the gang's house (e.g., Delaque, Goliath)."
    house = models.ForeignKey(
        ContentHouse,
        on_delete=models.CASCADE,
        help_text="The house to match",
    )

    def match(self, rule_inputs) -> bool:
        """Check if the list belongs to the required house."""
        return rule_inputs.list.content_house == self.house

    def __str__(self):
        return f"House Rule: {self.house}"

    class Meta:
        verbose_name = "Expansion Rule by House"
        verbose_name_plural = "Expansion Rules by House"


class ContentEquipmentListExpansionRuleByFighterCategory(
    ContentEquipmentListExpansionRule
):
    """
    Rule that matches based on fighter categories.
    """

    help_text = "Rule that matches based on fighter categories (e.g., Leader, Champion, Vehicle)."
    fighter_categories = MultiSelectField(
        choices=FighterCategoryChoices.choices,
        help_text="Fighter categories that must match",
    )

    def match(self, rule_inputs: ExpansionRuleInputs) -> bool:
        """Check if the fighter is one of the required categories."""
        fighter: "ListFighter" = rule_inputs.fighter
        if not fighter:
            return False

        category = fighter.get_category()
        if not category:
            return False

        return category in self.fighter_categories

    def __str__(self):
        categories = ", ".join(
            FighterCategoryChoices(cat).label for cat in self.fighter_categories[:3]
        )
        if len(self.fighter_categories) > 3:
            categories += "..."
        return f"Fighter Category Rule: {categories}"

    class Meta:
        verbose_name = "Expansion Rule by Fighter Category"
        verbose_name_plural = "Expansion Rules by Fighter Category"
