import pytest

from gyrinx.content.models import (
    ContentHouse,
    ContentHouseAdditionalRule,
    ContentHouseAdditionalRuleTree,
)


@pytest.mark.django_db
def test_house_skills():
    house = ContentHouse.objects.create(
        name="Squat Prospectors", house_additional_rules_name="Battle Name"
    )
    tree = ContentHouseAdditionalRuleTree.objects.create(
        house=house,
        name="Some Battle Name Category",
    )
    ContentHouseAdditionalRule.objects.create(tree=tree, name="Some Battle Name")
    ContentHouseAdditionalRule.objects.create(tree=tree, name="Another Battle Name")

    assert house.house_additional_rules_name == "Battle Name"
    assert tree.name == "Some Battle Name Category"
    assert tree.rules.count() == 2
    # Test default ordering — added in a different order
    assert tree.rules.first().name == "Another Battle Name"
    assert tree.rules.last().name == "Some Battle Name"
    assert tree.rules.first().tree == tree
