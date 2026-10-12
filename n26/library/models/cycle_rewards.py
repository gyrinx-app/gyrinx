"""Modifiers that offer persistent rewards when an arbitrator resolves a cycle."""

from django.core.exceptions import ValidationError
from django.db import models

from n26.core.constraints import exactly_one_of


class OffersCycleRecruitment(models.Model):
    """Offers one recruitment with a discount after each campaign cycle."""

    profiles = models.ManyToManyField("library.Profile", blank=True, related_name="+")
    profile_type = models.ForeignKey(
        "library.ProfileType",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    discount = models.PositiveIntegerField(
        default=0,
        help_text="Credits deducted from this recruitment, with a minimum payment of 0.",
    )
    maximum = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Maximum existing models from these profiles or this profile type. Leave blank for no limit.",
    )

    def accepts(self, target_kind):
        return target_kind == "gang"

    def __str__(self):
        return f"recruitment discount {self.discount}¢ per cycle"

    def clean(self):
        has_profiles = bool(self.pk and self.profiles.exists())
        if has_profiles == bool(self.profile_type_id):
            raise ValidationError(
                "Select profiles or a profile type for this recruitment, but not both."
            )


class OffersCycleEquipment(models.Model):
    """Offers equipment to the gang's stash after each campaign cycle."""

    wargear = models.ForeignKey(
        "library.Wargear",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    weapon = models.ForeignKey(
        "library.Weapon",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    quantity = models.PositiveIntegerField(
        default=1, help_text="How many pieces of equipment to add to the stash."
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=exactly_one_of(("wargear", "weapon")),
                name="cycle_equipment_exactly_one",
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1),
                name="cycle_equipment_positive_quantity",
            ),
        ]

    @property
    def thing(self):
        return self.wargear or self.weapon

    def accepts(self, target_kind):
        return target_kind == "gang"

    def __str__(self):
        return f"{self.quantity} {self.thing} per cycle"
