import pytest

from gyrinx.content.models import ContentEquipmentUpgrade
from gyrinx.core.models.list import (
    List,
    ListFighter,
    VirtualListFighterEquipmentAssignment,
)


@pytest.mark.django_db
def test_basic_list_clone(make_list, make_list_fighter, make_equipment):
    list_: List = make_list("Test List", narrative="This is a test list.")
    fighter: ListFighter = make_list_fighter(list_, "Test Fighter")
    spoon = make_equipment("Spoon")
    fighter.assign(spoon)

    list_clone: List = list_.clone(
        name="Test List (Clone)",
    )

    assert list_clone.name == "Test List (Clone)"
    assert list_clone.owner == list_.owner
    assert list_clone.content_house == list_.content_house
    assert list_clone.public == list_.public
    assert list_clone.narrative == "This is a test list."
    assert list_clone.fighters().count() == 1

    fighter_clone = list_clone.fighters().first()

    assert fighter_clone.name == "Test Fighter"
    assert fighter_clone.content_fighter == fighter.content_fighter
    assert fighter_clone.owner == fighter.owner
    assert fighter_clone.archived == fighter.archived

    assert fighter_clone.equipment.all().count() == 1
    assert fighter_clone.equipment.all().first().name == "Spoon"


@pytest.mark.django_db
def test_list_clone_with_mods(make_list, make_user):
    list_ = make_list("Test List")
    new_owner = make_user("new_owner", "password")

    list_clone: List = list_.clone(
        name="Test List (Clone)",
        owner=new_owner,
        public=False,
    )

    assert list_clone.public is False
    assert list_clone.owner == new_owner


@pytest.mark.django_db
def test_fighter_clone_with_mods(
    make_list,
    make_list_fighter,
    make_equipment,
    make_content_fighter,
    make_weapon_profile,
    make_weapon_accessory,
):
    list_ = make_list("Test List")
    fighter: ListFighter = make_list_fighter(list_, "Test Fighter")
    spoon = make_equipment("Spoon")
    spoon_spike = make_weapon_profile(spoon, name="Spoon Spike", cost=5)
    spoon_sight = make_weapon_accessory("Spoon Sight", cost=5)
    ContentEquipmentUpgrade.objects.create(
        equipment=spoon, name="Alpha", cost=20, position=0
    )
    u2 = ContentEquipmentUpgrade.objects.create(
        equipment=spoon, name="Beta", cost=30, position=1
    )
    assign = fighter.assign(
        spoon, weapon_profiles=[spoon_spike], weapon_accessories=[spoon_sight]
    )
    assign.upgrades_field.add(u2)
    assign.save()

    new_fighter = fighter.clone(
        name="Test Fighter (Clone)",
        narrative="This is a clone.",
    )

    assert new_fighter.name == "Test Fighter (Clone)"
    assert new_fighter.owner == fighter.owner
    assert new_fighter.archived == fighter.archived
    assert new_fighter.narrative == "This is a clone."
    assert new_fighter.equipment.all().count() == 1

    cloned_assign: VirtualListFighterEquipmentAssignment = new_fighter.assignments()[0]
    assert "Spoon" in cloned_assign.name()
    weapon_profiles = cloned_assign.weapon_profiles()
    assert len(weapon_profiles) == 1
    assert weapon_profiles[0].name == "Spoon Spike"
    accessories = cloned_assign.weapon_accessories()
    assert len(accessories) == 1
    assert accessories[0].name == "Spoon Sight"


@pytest.mark.django_db
def test_list_clone_excludes_stash_fighter(
    make_list, make_list_fighter, make_content_fighter
):
    """Test that stash fighters are not cloned when cloning a list."""
    list_ = make_list("Test List")

    # Create a regular fighter
    make_list_fighter(list_, "Regular Fighter")

    # Create a stash content fighter
    stash_cf = make_content_fighter(
        type="Stash",
        category="STASH",
        base_cost=0,
        house=list_.content_house,
    )
    stash_cf.is_stash = True
    stash_cf.save()

    # Create a stash list fighter
    ListFighter.objects.create(
        name="Gang Stash",
        content_fighter=stash_cf,
        list=list_,
        owner=list_.owner,
    )

    # Verify original list has both fighters
    assert list_.fighters().count() == 2

    # Clone the list
    cloned_list = list_.clone()

    # Verify only the regular fighter was cloned
    assert cloned_list.fighters().count() == 1
    cloned_fighter = cloned_list.fighters().first()
    assert cloned_fighter.name == "Regular Fighter"
    assert not cloned_fighter.content_fighter.is_stash


@pytest.mark.django_db
def test_list_clone_for_campaign_preserves_public_state(make_list, make_campaign):
    """Test that public/private state is preserved when cloning for campaigns."""
    # Test with a public list
    public_list = make_list("Public List", public=True)
    campaign = make_campaign("Test Campaign")

    public_clone = public_list.clone(for_campaign=campaign)
    assert public_clone.public is True  # Should preserve public state
    assert public_clone.campaign == campaign
    assert public_clone.status == List.CAMPAIGN_MODE

    # Test with a private list
    private_list = make_list("Private List", public=False)

    private_clone = private_list.clone(for_campaign=campaign)
    assert private_clone.public is False  # Should preserve private state
    assert private_clone.campaign == campaign
    assert private_clone.status == List.CAMPAIGN_MODE


@pytest.mark.django_db
def test_fighter_clone_with_xp_and_advancements(
    make_list, make_list_fighter, make_user
):
    """Test that XP and advancements are cloned with fighters."""
    list_ = make_list("Test List")
    fighter = make_list_fighter(list_, "Test Fighter")

    # Set XP on the fighter
    fighter.xp_current = 15
    fighter.xp_total = 25
    fighter.save()

    # Create an advancement (stat type instead of skill)
    from gyrinx.core.models.list import ListFighterAdvancement

    ListFighterAdvancement.objects.create(
        fighter=fighter,
        owner=fighter.owner,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_STAT,
        stat_increased="strength",
        xp_cost=6,
        cost_increase=5,
    )

    # Clone the fighter
    new_fighter = fighter.clone(
        name="Test Fighter (Clone)",
    )

    # Check XP was cloned
    assert new_fighter.xp_current == 15
    assert new_fighter.xp_total == 25

    # Check advancement was cloned
    assert new_fighter.advancements.count() == 1
    cloned_advancement = new_fighter.advancements.first()
    assert (
        cloned_advancement.advancement_type == ListFighterAdvancement.ADVANCEMENT_STAT
    )
    assert cloned_advancement.stat_increased == "strength"
    assert cloned_advancement.xp_cost == 6
    assert cloned_advancement.cost_increase == 5
    assert (
        cloned_advancement.campaign_action is None
    )  # Should not clone campaign action reference
