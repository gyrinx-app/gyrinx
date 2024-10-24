import json
import uuid
from dataclasses import dataclass
from pathlib import Path

import jsonschema
import pytest
from referencing import Registry, Resource

from gyrinx.core.models import (
    ContentCategory,
    ContentEquipment,
    ContentEquipmentCategory,
    ContentFighter,
    ContentHouse,
    ContentPolicy,
)


@pytest.mark.django_db
def test_basic_fighter():
    version = uuid.uuid4()
    category = ContentCategory.objects.create(
        name=ContentCategory.Choices.JUVE,
        uuid=uuid.uuid4(),
        version=version,
    )
    house = ContentHouse.objects.create(
        name=ContentHouse.Choices.SQUAT_PROSPECTORS,
        uuid=uuid.uuid4(),
        version=version,
    )
    fighter = ContentFighter.objects.create(
        uuid=uuid.uuid4(), type="Prospector Digger", category=category, house=house
    )

    fighter.save()
    assert fighter.type == "Prospector Digger"
    assert fighter.category.name == ContentCategory.Choices.JUVE


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
        uuid=uuid.uuid4(),
        name="Big Gun",
        category=ContentEquipmentCategory.objects.create(
            uuid=uuid.uuid4(),
            name=ContentEquipmentCategory.Choices.HEAVY_WEAPONS,
        ),
    )

    fighter = ContentFighter.objects.create(
        uuid=uuid.uuid4(),
        type="Ganger",
        category=ContentCategory.objects.create(
            uuid=uuid.uuid4(), name=ContentCategory.Choices.GANGER
        ),
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
            uuid=uuid.uuid4(),
            fighter=fighter,
            name=case.policy["name"],
            rules=case.policy["rules"],
        )

        assert (
            policy.allows(case.equipment) == case.expected
        ), f"Failed for {case.name}: expected {case.expected}"
