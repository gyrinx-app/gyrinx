import json
from dataclasses import dataclass
from pathlib import Path

import jsonschema
import pytest
from django.core.exceptions import ValidationError
from referencing import Registry, Resource

from gyrinx.content.models import (
    ContentEquipment,
    ContentFighter,
    ContentHouse,
    ContentPolicy,
    ContentRule,
    ContentWeaponProfile,
)
from gyrinx.models import EquipmentCategoryChoices, FighterCategoryChoices


@pytest.mark.django_db
def test_basic_fighter():
    category = FighterCategoryChoices.JUVE
    house = ContentHouse.objects.create(
        name="Squat Prospectors",
    )
    fighter = ContentFighter.objects.create(
        type="Prospector Digger", category=category, house=house
    )

    fighter.save()
    assert fighter.type == "Prospector Digger"
    assert fighter.category.name == FighterCategoryChoices.JUVE


@pytest.mark.django_db
def test_fighter_stats():
    category = FighterCategoryChoices.JUVE
    house = ContentHouse.objects.create(
        name="Squat Prospectors",
    )
    fighter = ContentFighter.objects.create(
        type="Prospector Digger",
        category=category,
        house=house,
        movement='5"',
        weapon_skill="5+",
        ballistic_skill="5+",
        strength="4",
        toughness="3",
        wounds="1",
        initiative="4+",
        attacks="1",
        leadership="8+",
        cool="7+",
        willpower="6+",
        intelligence="7+",
    )
    fighter.save()

    assert fighter.statline() == [
        {"name": "M", "value": '5"', "highlight": False, "classes": ""},
        {"name": "WS", "value": "5+", "highlight": False, "classes": ""},
        {"name": "BS", "value": "5+", "highlight": False, "classes": ""},
        {"name": "S", "value": "4", "highlight": False, "classes": ""},
        {"name": "T", "value": "3", "highlight": False, "classes": ""},
        {"name": "W", "value": "1", "highlight": False, "classes": ""},
        {"name": "I", "value": "4+", "highlight": False, "classes": ""},
        {"name": "A", "value": "1", "highlight": False, "classes": ""},
        {"name": "Ld", "value": "8+", "highlight": True, "classes": "border-start"},
        {"name": "Cl", "value": "7+", "highlight": True, "classes": ""},
        {"name": "Wil", "value": "6+", "highlight": True, "classes": ""},
        {"name": "Int", "value": "7+", "highlight": True, "classes": ""},
    ]


@pytest.mark.django_db
def test_fighter_rules():
    r_gang_fighter, _ = ContentRule.objects.get_or_create(name="Gang Fighter (Juve)")
    r_promotion, _ = ContentRule.objects.get_or_create(name="Promotion (Specialist)")
    r_fast_learner, _ = ContentRule.objects.get_or_create(name="Fast Learner")

    category = FighterCategoryChoices.JUVE
    house = ContentHouse.objects.create(
        name="Squat Prospectors",
    )
    fighter = ContentFighter.objects.create(
        type="Prospector Digger",
        category=category,
        house=house,
    )
    fighter.rules.set([r_gang_fighter, r_promotion, r_fast_learner])
    fighter.save()

    assert [rule.name for rule in fighter.rules.all()] == [
        "Fast Learner",
        "Gang Fighter (Juve)",
        "Promotion (Specialist)",
    ]
    assert fighter.ruleline() == [
        "Fast Learner",
        "Gang Fighter (Juve)",
        "Promotion (Specialist)",
    ]


# class ContentWeaponProfile(Content):
#     """
#     Represents a specific profile for :model:`content.ContentEquipment`. "Standard" profiles have zero cost.
#     """

#     equipment = models.ForeignKey(
#         ContentEquipment,
#         on_delete=models.CASCADE,
#         db_index=True,
#         null=True,
#         blank=False,
#     )
#     name = models.CharField(max_length=255, blank=True)
#     help_text = "Captures the cost, rarity and statline for a weapon."

#     # If the cost is zero, then the profile is free to use and "standard".
#     cost = models.IntegerField(
#         default=0,
#         help_text="The credit cost of the weapon profile at the Trading Post. If the cost is zero, "
#         "then the profile is free to use and standard. This cost is overridden if the "
#         "profile is in the fighter's equipment list.",
#     )
#     cost_sign = models.CharField(
#         max_length=1,
#         choices=[("+", "+")],
#         blank=True,
#         null=False,
#         default="",
#     )
#     rarity = models.CharField(
#         max_length=1,
#         choices=[
#             ("R", "Rare (R)"),
#             ("I", "Illegal (I)"),
#             ("E", "Exclusive (E)"),
#             ("C", "Common (C)"),
#         ],
#         blank=True,
#         default="C",
#     )
#     rarity_roll = models.IntegerField(blank=True, null=True)

#     # Stat line
#     range_short = models.CharField(
#         max_length=12, blank=True, null=False, default="", verbose_name="Rng S"
#     )
#     range_long = models.CharField(
#         max_length=12, blank=True, null=False, default="", verbose_name="Rng L"
#     )
#     accuracy_short = models.CharField(
#         max_length=12, blank=True, null=False, default="", verbose_name="Acc S"
#     )
#     accuracy_long = models.CharField(
#         max_length=12, blank=True, null=False, default="", verbose_name="Acc L"
#     )
#     strength = models.CharField(
#         max_length=12, blank=True, null=False, default="", verbose_name="Str"
#     )
#     armour_piercing = models.CharField(
#         max_length=12, blank=True, null=False, default="", verbose_name="Ap"
#     )
#     damage = models.CharField(
#         max_length=12, blank=True, null=False, default="", verbose_name="D"
#     )
#     ammo = models.CharField(
#         max_length=12, blank=True, null=False, default="", verbose_name="Am"
#     )

#     traits = models.ManyToManyField(ContentWeaponTrait, blank=True)
#     history = HistoricalRecords()

#     def __str__(self):
#         return f"{self.equipment} {self.name if self.name else '(Standard)'}"

#     def cost_int(self):
#         """
#         Returns the integer cost of this weapon profile.
#         """
#         return self.cost

#     def cost_tp(self) -> int | None:
#         """
#         Determines the cost if purchased at the Trading Post. Returns None if
#         standard (zero cost), or a sum if the cost sign is '+', or just the
#         cost otherwise.
#         """
#         if self.cost_int() == 0:
#             return None

#         # If the cost is positive, then the profile is an upgrade to the equipment.
#         if self.cost_sign == "+":
#             return self.equipment.cost_int() + self.cost_int()

#         # Otherwise, the cost is the profile cost.
#         # TODO: When is this a thing?
#         return self.cost_int()

#     def cost_display(self) -> str:
#         """
#         Returns a readable display for the cost, including any sign and '¢'.
#         """
#         if self.name == "" or self.cost_int() == 0:
#             return ""
#         return f"{self.cost_sign}{self.cost_int()}¢"

#     def cost_for_fighter_int(self):
#         if hasattr(self, "cost_for_fighter"):
#             return self.cost_for_fighter

#         raise AttributeError(
#             "cost_for_fighter not available. Use with_cost_for_fighter()"
#         )

#     def statline(self):
#         """
#         Returns a list of dictionaries describing the weapon profile's stats,
#         including range, accuracy, strength, and so forth.
#         """
#         stats = [
#             self._meta.get_field(field)
#             for field in [
#                 "range_short",
#                 "range_long",
#                 "accuracy_short",
#                 "accuracy_long",
#                 "strength",
#                 "armour_piercing",
#                 "damage",
#                 "ammo",
#             ]
#         ]
#         return [
#             {
#                 "name": field.verbose_name,
#                 "classes": (
#                     "border-start"
#                     if field.name in ["accuracy_short", "strength"]
#                     else ""
#                 ),
#                 "value": getattr(self, field.name) or "-",
#             }
#             for field in stats
#         ]

#     def traitline(self):
#         """
#         Returns a list of weapon trait names associated with this profile.
#         """
#         return [trait.name for trait in self.traits.all()]

#     class Meta:
#         verbose_name = "Weapon Profile"
#         verbose_name_plural = "Weapon Profiles"
#         unique_together = ["equipment", "name"]
#         ordering = [
#             "equipment__name",
#             Case(
#                 When(name="", then=0),
#                 default=99,
#             ),
#             "cost",
#         ]

#     def clean(self):
#         """
#         Validation to ensure appropriate costs and cost signs for standard
#         vs non-standard weapon profiles.
#         """
#         self.name = self.name.strip()

#         if self.name.startswith("-"):
#             raise ValidationError("Name should not start with a hyphen.")

#         if self.name == "(Standard)":
#             raise ValidationError('Name should not be "(Standard)".')

#         # Ensure that specific fields are not hyphens
#         for field in [
#             "range_short",
#             "range_long",
#             "accuracy_short",
#             "accuracy_long",
#             "strength",
#             "armour_piercing",
#             "damage",
#             "ammo",
#         ]:
#             setattr(self, field, getattr(self, field).strip())
#             value = getattr(self, field)
#             if value == "-":
#                 raise ValidationError(
#                     f"Use a blank value for {field.verbose_name} rather than a hyphen."
#                 )

#             if field in [
#                 "range_short",
#                 "range_long",
#                 "accuracy_short",
#                 "accuracy_long",
#             ]:
#                 if value and value[0].isdigit() and not value.endswith('"'):
#                     raise ValidationError(
#                         f"{field.verbose_name} should end with a double quote if it starts with a number."
#                     )

#         if self.cost_int() < 0:
#             raise ValidationError("Cost cannot be negative.")

#         if self.cost_int() == 0 and self.cost_sign != "":
#             raise ValidationError("Cost sign should be empty for zero cost profiles.")

#         if self.name == "" and self.cost_int() != 0:
#             raise ValidationError("Standard profiles should have zero cost.")

#         if self.cost_int() == 0 and self.cost_sign != "":
#             raise ValidationError("Standard profiles should have zero cost.")

#         if self.cost_int() != 0 and self.cost_sign == "":
#             raise ValidationError("Non-standard profiles should have a cost sign.")

#         if self.cost_int() != 0 and self.cost_sign != "+":
#             raise ValidationError(
#                 "Non-standard profiles should have a positive cost sign."
#             )

#     objects = ContentWeaponProfileManager.from_queryset(ContentWeaponProfileQuerySet)()


@pytest.mark.django_db
def test_content_weapon_profile_validation():
    equipment = ContentEquipment.objects.create(name="Laser Gun")

    # Test valid profile
    profile = ContentWeaponProfile(
        equipment=equipment,
        name="Standard",
        cost=0,
        cost_sign="",
        rarity="C",
        range_short='12"',
        range_long='24"',
        accuracy_short="+1",
        accuracy_long="0",
        strength="4",
        armour_piercing="-1",
        damage="1",
        ammo="4+",
    )
    profile.clean()  # Should not raise any exception

    # Test invalid profile with negative cost
    profile.cost = -10
    with pytest.raises(ValidationError, match="Cost cannot be negative."):
        profile.clean()

    # Test invalid profile with non-empty cost sign for zero cost
    profile.cost = 0
    profile.cost_sign = "+"
    with pytest.raises(
        ValidationError, match="Cost sign should be empty for zero cost profiles."
    ):
        profile.clean()

    # Test invalid profile with empty name and non-zero cost
    profile.name = ""
    profile.cost = 10
    profile.cost_sign = "+"
    with pytest.raises(
        ValidationError, match="Standard profiles should have zero cost."
    ):
        profile.clean()

    # Test invalid profile with non-standard profile missing cost sign
    profile.name = "Special"
    profile.cost = 10
    profile.cost_sign = ""
    with pytest.raises(
        ValidationError, match="Non-standard profiles should have a cost sign."
    ):
        profile.clean()

    # Test invalid profile with non-standard profile having incorrect cost sign
    profile.cost_sign = "-"
    with pytest.raises(
        ValidationError, match="Non-standard profiles should have a positive cost sign."
    ):
        profile.clean()

    # Test invalid profile with hyphen in name
    profile.name = "-Special"
    with pytest.raises(ValidationError, match="Name should not start with a hyphen."):
        profile.clean()

    # Test invalid profile with "(Standard)" in name
    profile.name = "(Standard)"
    with pytest.raises(ValidationError, match='Name should not be "\(Standard\)".'):
        profile.clean()

    # Test invalid profile with hyphen in specific fields
    profile.name = "Special"
    profile.cost_sign = "+"
    profile.range_short = "-"
    profile.clean()
    assert profile.range_short == ""

    profile.range_short = "4"
    profile.clean()
    assert profile.range_short == '4"'


@pytest.mark.django_db
def test_equipment_with_cost_2D6X10():
    equipment = ContentEquipment.objects.create(
        name="Random Cost Equipment",
        cost="2D6X10",
    )

    assert equipment.cost == "2D6X10"
    assert equipment.cost_int() == 0
    assert equipment.cost_display() == "2D6X10"


@dataclass
class PolicyCase:
    name: str
    equipment: ContentEquipment
    policy: dict
    expected: bool


@pytest.mark.django_db
def test_equipment_policy():
    # Create a fighter, some equipment, and a set of policies
    # Check that the policies are applied correctly

    # Load the policy.schema.json file so we can check created policies
    # against it
    file = (
        Path(__file__).parent
        / "../../../content/necromunda-2018/schema/policy.schema.json"
    )
    with file.open() as f:
        policy_schema = json.load(f)

    registry = Resource.from_contents(policy_schema) @ Registry()

    big_gun = ContentEquipment.objects.create(
        name="Big Gun",
        category=EquipmentCategoryChoices.HEAVY_WEAPONS,
    )

    fighter = ContentFighter.objects.create(
        type="Ganger",
        category=FighterCategoryChoices.GANGER,
    )

    # Create some
    test_cases = [
        PolicyCase(
            name="Allow all",
            equipment=big_gun,
            policy={
                "name": "Allow all",
                "rules": [],
            },
            expected=True,
        ),
        PolicyCase(
            name="Explicit allow all",
            equipment=big_gun,
            policy={
                "name": "Allow all",
                "rules": [
                    {
                        "allow": "all",
                    }
                ],
            },
            expected=True,
        ),
        PolicyCase(
            name="Deny sandwich",
            equipment=big_gun,
            policy={
                "name": "Allow all",
                "rules": [
                    {
                        "allow": "all",
                    },
                    {
                        "deny": "all",
                    },
                    {
                        "allow": "all",
                    },
                ],
            },
            expected=True,
        ),
        PolicyCase(
            name="No Heavy Weapons",
            equipment=big_gun,
            policy={
                "name": "No Heavy Weapons",
                "rules": [
                    {
                        "deny": [
                            {
                                "category": "Heavy Weapons",
                            }
                        ]
                    }
                ],
            },
            expected=False,
        ),
        PolicyCase(
            name="No Heavy Weapons except Allow Big Gun",
            equipment=big_gun,
            policy={
                "name": "No Heavy Weapons except Big Gun",
                "rules": [
                    {
                        "deny": [
                            {
                                "category": "Heavy Weapons",
                            }
                        ],
                    },
                    {
                        "allow": [
                            {
                                "name": "Big Gun",
                            }
                        ],
                    },
                ],
            },
            expected=True,
        ),
        PolicyCase(
            name="Deny all except Big Gun",
            equipment=big_gun,
            policy={
                "name": "Only Big Gun",
                "rules": [
                    {
                        "deny": "all",
                    },
                    {
                        "allow": [
                            {
                                "name": "Big Gun",
                            }
                        ],
                    },
                ],
            },
            expected=True,
        ),
        PolicyCase(
            name="Allow all except Big Gun",
            equipment=big_gun,
            policy={
                "name": "No Big Gun",
                "rules": [
                    {
                        "deny": [
                            {
                                "name": "Big Gun",
                            }
                        ],
                    },
                ],
            },
            expected=False,
        ),
        PolicyCase(
            name="Deny all",
            equipment=big_gun,
            policy={
                "name": "Deny all",
                "rules": [
                    {
                        "deny": "all",
                    }
                ],
            },
            expected=False,
        ),
        PolicyCase(
            name="Deny all except Heavy Weapons",
            equipment=big_gun,
            policy={
                "name": "Deny all",
                "rules": [
                    {
                        "deny": "all",
                    },
                    {
                        "allow": [
                            {
                                "category": "Heavy Weapons",
                            }
                        ],
                    },
                ],
            },
            expected=True,
        ),
        PolicyCase(
            name="Deny all except the Big Gun within Heavy Weapons",
            equipment=big_gun,
            policy={
                "name": "Deny all",
                "rules": [
                    {
                        "deny": "all",
                    },
                    {
                        "allow": [
                            {
                                "category": "Heavy Weapons",
                                "name": "Big Gun",
                            }
                        ],
                    },
                ],
            },
            expected=True,
        ),
        PolicyCase(
            name="Deny all except the Huge Gun within Heavy Weapons",
            equipment=big_gun,
            policy={
                "name": "Deny all",
                "rules": [
                    {
                        "deny": "all",
                    },
                    {
                        "allow": [
                            {
                                "category": "Heavy Weapons",
                                "name": "Huge Gun",
                            }
                        ],
                    },
                ],
            },
            expected=False,
        ),
        PolicyCase(
            name="Allow the Big Gun but deny in another category",
            equipment=big_gun,
            policy={
                "name": "Deny a Big Gun Pistol",
                "rules": [
                    {
                        "deny": [
                            {
                                "category": "Pistols",
                                "name": "Big Gun",
                            }
                        ],
                    },
                ],
            },
            expected=True,
        ),
        PolicyCase(
            name="Deny Pistols",
            equipment=big_gun,
            policy={
                "name": "Deny Pistols",
                "rules": [
                    {
                        "deny": [
                            {
                                "category": "Pistols",
                            }
                        ],
                    },
                ],
            },
            expected=True,
        ),
    ]

    for case in test_cases:
        jsonschema.validate(case.policy, policy_schema, registry=registry)

        policy = ContentPolicy.objects.create(
            fighter=fighter,
            rules=case.policy["rules"],
        )

        assert (
            policy.allows(case.equipment) == case.expected
        ), f"Failed for {case.name}: expected {case.expected}"
