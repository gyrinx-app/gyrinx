import pytest
from django.core.exceptions import ValidationError

from gyrinx.content.models import (
    ContentEquipment,
    ContentEquipmentCategory,
    ContentEquipmentUpgrade,
    ContentFighter,
    ContentFighterEquipmentListItem,
    ContentFighterEquipmentListWeaponAccessory,
    ContentFighterHouseOverride,
    ContentHouse,
    ContentWeaponAccessory,
    ContentWeaponProfile,
    ContentWeaponTrait,
)
from gyrinx.core.models.list import (
    List,
    ListFighter,
    ListFighterEquipmentAssignment,
    VirtualListFighterEquipmentAssignment,
)
from gyrinx.models import FighterCategoryChoices


@pytest.fixture
def test_content(content_house, content_fighter):
    """Fixture that returns a tuple of category, house, and fighter for backward compatibility."""
    return content_fighter.category, content_house, content_fighter


@pytest.mark.django_db
def test_basic_list(content_house):
    lst = List.objects.create(name="Test List", content_house=content_house)

    assert lst.name == "Test List"


@pytest.mark.django_db
def test_list_name_min_length(content_house):
    # Test that 1 character names are now allowed
    lst = List.objects.create(name="A", content_house=content_house)
    assert lst.name == "A"

    # Test that 2 character names still work
    lst2 = List.objects.create(name="AB", content_house=content_house)
    assert lst2.name == "AB"


@pytest.mark.django_db
def test_basic_list_fighter(content_house, content_fighter):
    lst = List.objects.create(name="Test List", content_house=content_house)
    fighter = ListFighter.objects.create(
        name="Test Fighter", list=lst, content_fighter=content_fighter
    )

    assert lst.name == "Test List"
    assert fighter.name == "Test Fighter"


@pytest.mark.django_db
def test_fighter_name_min_length(user, content_house, content_fighter):
    lst = List.objects.create(name="Test List", content_house=content_house)

    # Test that 1 character names are now allowed
    fighter = ListFighter(
        name="B", list=lst, content_fighter=content_fighter, owner=user
    )
    fighter.full_clean()  # This should not raise any validation error

    # Test that empty names still fail (due to blank=False)
    with pytest.raises(ValidationError, match="This field cannot be blank"):
        fighter = ListFighter(
            name="", list=lst, content_fighter=content_fighter, owner=user
        )
        fighter.full_clean()  # This will trigger the validation


@pytest.mark.django_db
def test_list_fighter_requires_content_fighter(content_house):
    lst = List.objects.create(name="Test List", content_house=content_house)
    with pytest.raises(Exception):
        ListFighter.objects.create(name="Test Fighter", list=lst)


@pytest.mark.django_db
def test_list_fighter_content_fighter(content_house, content_fighter):
    lst = List.objects.create(name="Test List", content_house=content_house)
    fighter = ListFighter.objects.create(
        name="Test Fighter", list=lst, content_fighter=content_fighter
    )

    assert fighter.content_fighter.type == "Prospector Digger"


@pytest.mark.django_db
def test_list_fighter_house_matches_list(user, content_fighter):
    house = ContentHouse.objects.create(
        name="Ash Waste Nomads",
    )

    lst = List.objects.create(name="Test List AWN", content_house=house, owner=user)

    with pytest.raises(
        ValidationError,
        match="Prospector Digger cannot be a member of Ash Waste Nomads list",
    ):
        ListFighter.objects.create(
            name="Test Fighter",
            list=lst,
            content_fighter=content_fighter,
            owner=lst.owner,
        ).full_clean()


@pytest.mark.django_db
def test_list_fighter_generic_house(
    user, make_content_fighter, make_content_house, make_list
):
    generic_house = make_content_house("Generic House", generic=True)
    content_fighter = make_content_fighter(
        type="Generic Fighter",
        category=FighterCategoryChoices.JUVE,
        house=generic_house,
        base_cost=100,
    )

    list_house = make_content_house("List House")
    lst = make_list("Test List", content_house=list_house, owner=user)

    ListFighter.objects.create(
        name="Test Fighter",
        list=lst,
        content_fighter=content_fighter,
        owner=lst.owner,
    ).full_clean()


@pytest.mark.django_db
def test_fighter_cost_override_for_house(
    user, make_content_fighter, make_content_house, make_list, make_list_fighter
):
    generic_house = make_content_house("Generic House", generic=True)
    content_fighter = make_content_fighter(
        type="Generic Fighter",
        category=FighterCategoryChoices.JUVE,
        house=generic_house,
        base_cost=100,
    )

    list_house = make_content_house("List House")

    # Override cost to list_house for generic fighter
    ContentFighterHouseOverride.objects.create(
        fighter=content_fighter, house=list_house, cost=80
    )

    lst = make_list("Test List", content_house=list_house, owner=user)
    make_list_fighter(lst, "Generic Fighter", content_fighter=content_fighter)

    assert lst.cost_int() == 80


@pytest.mark.django_db
def test_fighter_stat_override(content_fighter, make_list, make_list_fighter):
    lst = make_list("Test List", content_house=content_fighter.house)
    fighter = make_list_fighter(lst, "Test Fighter", content_fighter=content_fighter)

    stats = [stat.value for stat in fighter.statline]
    assert stats == ['5"', "5+", "5+", "4", "3", "1", "4+", "1", "8+", "7+", "6+", "7+"]

    fighter.movement_override = '6"'
    fighter.weapon_skill_override = "6+"
    fighter.ballistic_skill_override = "6+"
    fighter.strength_override = "5"
    fighter.toughness_override = "4"
    fighter.wounds_override = "2"
    fighter.initiative_override = "5+"
    fighter.attacks_override = "2"
    fighter.leadership_override = "9+"
    fighter.cool_override = "8+"
    fighter.willpower_override = "7+"
    fighter.intelligence_override = "8+"
    fighter.save()

    # Caching!
    fighter = ListFighter.objects.get(pk=fighter.pk)

    stats = [stat.value for stat in fighter.statline]
    assert stats == ['6"', "6+", "6+", "5", "4", "2", "5+", "2", "9+", "8+", "7+", "8+"]


@pytest.mark.django_db
def test_archive_list(content_house):
    lst = List.objects.create(name="Test List", content_house=content_house)

    lst.archive()

    assert lst.archived
    assert lst.archived_at is not None


@pytest.mark.django_db
def test_history(content_house):
    lst = List.objects.create(name="Test List", content_house=content_house)

    assert lst.history.all().count() == 1

    lst.name = "Test List 2"
    lst.save()

    assert lst.history.all().count() == 2
    assert lst.history.first().name == "Test List 2"

    lst.archive()

    assert lst.history.first().archived
    assert not lst.history.first().prev_record.archived


@pytest.mark.django_db
def test_list_cost(content_house, content_fighter):
    lst = List.objects.create(name="Test List", content_house=content_house)
    fighter = ListFighter.objects.create(
        name="Test Fighter", list=lst, content_fighter=content_fighter
    )

    assert fighter.cost_int() == content_fighter.cost_int()
    assert lst.cost_int() == content_fighter.cost_int()

    fighter2 = ListFighter.objects.create(
        name="Test Fighter 2", list=lst, content_fighter=content_fighter
    )

    assert fighter2.cost_int() == content_fighter.cost_int()
    assert lst.cost_int() == content_fighter.cost_int() * 2


@pytest.mark.django_db
def test_list_cost_variable(content_house, content_fighter):
    content_fighter2 = ContentFighter.objects.create(
        type="Expensive Guy",
        category=content_fighter.category,
        house=content_house,
        base_cost=150,
    )

    lst = List.objects.create(name="Test List", content_house=content_house)
    fighter = ListFighter.objects.create(
        name="Test Fighter", list=lst, content_fighter=content_fighter
    )
    fighter2 = ListFighter.objects.create(
        name="Test Fighter 2", list=lst, content_fighter=content_fighter2
    )

    assert fighter.cost_int() == content_fighter.cost_int()
    assert fighter2.cost_int() == content_fighter2.cost_int()
    assert lst.cost_int() == content_fighter.cost_int() + content_fighter2.cost_int()


@pytest.mark.django_db
def test_list_cost_with_archived_fighter(content_house, content_fighter):
    expensive_guy = ContentFighter.objects.create(
        type="Expensive Guy",
        category=content_fighter.category,
        house=content_house,
        base_cost=150,
    )

    lst = List.objects.create(name="Test List", content_house=content_house)
    fighter = ListFighter.objects.create(
        name="Test Fighter", list=lst, content_fighter=content_fighter
    )
    fighter2 = ListFighter.objects.create(
        name="Test Fighter 2", list=lst, content_fighter=expensive_guy
    )

    assert lst.cost_int() == fighter.cost_int() + fighter2.cost_int()

    fighter2.archive()

    assert lst.cost_int() == fighter.cost_int()


@pytest.mark.django_db
def test_list_cost_with_fighter_cost_override(content_house, content_fighter):
    expensive_guy = ContentFighter.objects.create(
        type="Expensive Guy",
        category=content_fighter.category,
        house=content_house,
        base_cost=150,
    )

    lst = List.objects.create(name="Test List", content_house=content_house)
    fighter = ListFighter.objects.create(
        name="Test Fighter", list=lst, content_fighter=content_fighter
    )
    fighter2 = ListFighter.objects.create(
        name="Test Fighter 2", list=lst, content_fighter=expensive_guy
    )

    assert lst.cost_int() == fighter.cost_int() + fighter2.cost_int()

    fighter2.cost_override = 0
    fighter2.save()

    assert lst.cost_int() == fighter.cost_int()
    pre_clone_list_cost = lst.cost_int()

    # Test fighter clone keeps the cost override
    new_fighter = fighter2.clone(
        name="Test Fighter 2 (Clone)",
        list=lst,
    )

    assert new_fighter.cost_int() == 0

    lst = List.objects.get(pk=lst.pk)
    assert lst.cost_int() == pre_clone_list_cost


@pytest.mark.django_db
def test_list_fighter_with_spoon(
    content_house, content_fighter, content_equipment_categories
):
    spoon, _ = ContentEquipment.objects.get_or_create(
        name="Wooden Spoon",
        category=ContentEquipmentCategory.objects.get(name="Basic Weapons"),
        cost=10,
    )

    lst, _ = List.objects.get_or_create(name="Test List", content_house=content_house)
    fighter, _ = ListFighter.objects.get_or_create(
        name="Test Fighter", list=lst, content_fighter=content_fighter
    )

    assert fighter.cost_int() == 100

    fighter.equipment.add(spoon)

    assert fighter.cost_int() == 110

    assert fighter.cost_int() == content_fighter.cost_int() + spoon.cost_int()
    assert lst.cost_int() == fighter.cost_int()
    assert lst.cost_int() == 110


@pytest.mark.django_db
def test_list_fighter_with_spoon_weapon(
    content_house, content_fighter, content_equipment_categories
):
    spoon, _ = ContentEquipment.objects.get_or_create(
        name="Wooden Spoon",
        category=ContentEquipmentCategory.objects.get(name="Basic Weapons"),
        cost=10,
    )

    t_melee, _ = ContentWeaponTrait.objects.get_or_create(
        name="Melee",
    )
    spoon_profile, _ = ContentWeaponProfile.objects.get_or_create(
        equipment=spoon,
        name="",
        defaults=dict(
            range_short="",
            range_long="E",
            accuracy_short="",
            accuracy_long="",
            strength="S-1",
            armour_piercing="+1",
            damage="1",
            ammo="4+",
        ),
    )
    spoon_profile.traits.add(t_melee)

    lst, _ = List.objects.get_or_create(name="Test List", content_house=content_house)
    fighter, _ = ListFighter.objects.get_or_create(
        name="Test Fighter", list=lst, content_fighter=content_fighter
    )

    assert fighter.cost_int() == 100

    fighter.assign(spoon, weapon_profiles=[spoon_profile])

    assert fighter.cost_int() == 110
    assert list(
        fighter.equipment.through.objects.get(
            list_fighter=fighter, content_equipment=spoon
        ).weapon_profiles()
    ) == [spoon_profile]

    assert fighter.cost_int() == content_fighter.cost_int() + spoon.cost_int()
    assert lst.cost_int() == fighter.cost_int()
    assert lst.cost_int() == 110


@pytest.mark.django_db
def test_fighter_with_spoon_weapon_profile_with_cost(
    content_house, content_fighter, content_equipment_categories
):
    spoon, _ = ContentEquipment.objects.get_or_create(
        name="Wooden Spoon",
        category=ContentEquipmentCategory.objects.get(name="Basic Weapons"),
        cost=10,
    )

    spoon_profile, _ = ContentWeaponProfile.objects.get_or_create(
        equipment=spoon,
        name="",
        defaults=dict(
            range_short="",
            range_long="E",
            accuracy_short="",
            accuracy_long="",
            strength="S-1",
            armour_piercing="+1",
            damage="1",
            ammo="4+",
        ),
    )

    spoon_spike_profile, _ = ContentWeaponProfile.objects.get_or_create(
        equipment=spoon,
        name="with Spike",
        defaults=dict(
            cost=5,
            range_short="",
            range_long="E",
            accuracy_short="",
            accuracy_long="",
            strength="S",
            armour_piercing="+2",
            damage="1",
            ammo="4+",
        ),
    )

    lst, _ = List.objects.get_or_create(name="Test List", content_house=content_house)
    fighter, _ = ListFighter.objects.get_or_create(
        name="Test Fighter", list=lst, content_fighter=content_fighter
    )

    assert fighter.cost_int() == 100

    fighter.assign(spoon, weapon_profiles=[spoon_spike_profile])

    assert fighter.cost_int() == 115

    assert lst.cost_int() == 115


@pytest.mark.django_db
def test_list_fighter_with_spoon_and_not_other_assignments(
    content_house, content_fighter, content_equipment_categories
):
    # This test was introduced to fix a bug where the cost of a fighter was
    # including all equipment assignments, not just the ones for that fighter.
    spoon, _ = ContentEquipment.objects.get_or_create(
        name="Wooden Spoon",
        category=ContentEquipmentCategory.objects.get(name="Basic Weapons"),
        cost=10,
    )

    spoon_profile, _ = ContentWeaponProfile.objects.get_or_create(
        equipment=spoon,
        name="",
        defaults=dict(
            range_short="",
            range_long="E",
            accuracy_short="",
            accuracy_long="",
            strength="S-1",
            armour_piercing="+1",
            damage="1",
            ammo="4+",
        ),
    )

    spoon_spike_profile, _ = ContentWeaponProfile.objects.get_or_create(
        equipment=spoon,
        name="with Spike",
        defaults=dict(
            cost=5,
            range_short="",
            range_long="E",
            accuracy_short="",
            accuracy_long="",
            strength="S",
            armour_piercing="+2",
            damage="1",
            ammo="4+",
        ),
    )

    lst, _ = List.objects.get_or_create(name="Test List", content_house=content_house)
    fighter, _ = ListFighter.objects.get_or_create(
        name="Test Fighter", list=lst, content_fighter=content_fighter
    )
    fighter2, _ = ListFighter.objects.get_or_create(
        name="Test Fighter 2", list=lst, content_fighter=content_fighter
    )

    assert fighter.cost_int() == 100
    assert fighter2.cost_int() == 100

    fighter.assign(spoon, weapon_profiles=[spoon_spike_profile])

    assert fighter.cost_int() == 115
    assert fighter2.cost_int() == 100

    fighter2.assign(spoon, weapon_profiles=[spoon_profile])

    assert fighter.cost_int() == 115
    assert fighter2.cost_int() == 110

    assert lst.cost_int() == 225


@pytest.mark.django_db
def test_profile_validation_standard_profile_non_zero_cost(
    content_equipment_categories,
):
    spoon, _ = ContentEquipment.objects.get_or_create(
        name="Wooden Spoon",
        category=ContentEquipmentCategory.objects.get(name="Basic Weapons"),
        cost=10,
    )

    with pytest.raises(ValidationError):
        profile, _ = ContentWeaponProfile.objects.get_or_create(
            equipment=spoon,
            name="",
            defaults=dict(
                cost=5,
                range_short="",
                range_long="E",
                accuracy_short="",
                accuracy_long="",
                strength="S-1",
                armour_piercing="+1",
                damage="1",
                ammo="4+",
            ),
        )
        profile.clean()


@pytest.mark.django_db
def test_weapon_cost_equipment_list_override(
    content_equipment_categories, content_house, content_fighter
):
    spoon, _ = ContentEquipment.objects.get_or_create(
        name="Wooden Spoon",
        category=ContentEquipmentCategory.objects.get(name="Basic Weapons"),
        cost=10,
    )

    # This guy gets spoons on the cheap
    ContentFighterEquipmentListItem.objects.get_or_create(
        fighter=content_fighter, equipment=spoon, cost=5
    )

    lst, _ = List.objects.get_or_create(name="Test List", content_house=content_house)
    fighter, _ = ListFighter.objects.get_or_create(
        name="Test Fighter", list=lst, content_fighter=content_fighter
    )

    assert fighter.cost_int() == 100

    fighter.assign(spoon)

    assert fighter.cost_int() == 105

    assignment = ListFighterEquipmentAssignment.objects.get(
        list_fighter=fighter, content_equipment=spoon
    )

    assert assignment.cost_int() == 5
    assert assignment.base_cost_int() == 5
    assert assignment.base_cost_display() == "5¢"


@pytest.mark.django_db
def test_weapon_cost_equipment_list_override_with_profile(
    content_equipment_categories, content_house, content_fighter
):
    spoon, _ = ContentEquipment.objects.get_or_create(
        name="Wooden Spoon",
        category=ContentEquipmentCategory.objects.get(name="Basic Weapons"),
        cost=10,
    )

    spoon_spike_profile, _ = ContentWeaponProfile.objects.get_or_create(
        equipment=spoon,
        name="with Spike",
        defaults=dict(
            cost=5,
            range_short="",
            range_long="E",
            accuracy_short="",
            accuracy_long="",
            strength="S",
            armour_piercing="+2",
            damage="1",
            ammo="4+",
        ),
    )

    # This guy gets spikes on his spoons for cheap, but spoons at full cost.
    ContentFighterEquipmentListItem.objects.get_or_create(
        fighter=content_fighter,
        equipment=spoon,
        cost=10,
    )

    ContentFighterEquipmentListItem.objects.get_or_create(
        fighter=content_fighter,
        equipment=spoon,
        weapon_profile=spoon_spike_profile,
        cost=2,
    )

    lst, _ = List.objects.get_or_create(name="Test List", content_house=content_house)
    fighter, _ = ListFighter.objects.get_or_create(
        name="Test Fighter", list=lst, content_fighter=content_fighter
    )

    assert fighter.cost_int() == 100

    # Duel-wield spoons
    fighter.assign(spoon)
    fighter.assign(spoon, weapon_profiles=[spoon_spike_profile])

    assert fighter.cost_int() == 122

    assignment = ListFighterEquipmentAssignment.objects.get(
        list_fighter=fighter,
        content_equipment=spoon,
        weapon_profiles_field=None,
    )

    assert assignment.cost_int() == 10
    assert assignment.base_cost_int() == 10
    assert assignment.base_cost_display() == "10¢"
    assert assignment.weapon_profiles_cost_int() == 0
    assert assignment.weapon_profiles_cost_display() == "+0¢"

    spike_assignment = ListFighterEquipmentAssignment.objects.get(
        list_fighter=fighter,
        content_equipment=spoon,
        weapon_profiles_field__in=[spoon_spike_profile],
    )

    assert spike_assignment.cost_int() == 12
    assert spike_assignment.cost_display() == "12¢"
    assert spike_assignment.base_cost_int() == 10
    assert spike_assignment.base_cost_display() == "10¢"
    assert spike_assignment.weapon_profiles_cost_int() == 2
    assert spike_assignment.weapon_profiles_cost_display() == "+2¢"


@pytest.mark.django_db
def test_fighter_with_equipment_list_accessory(
    content_fighter,
    content_equipment_categories,
    make_list,
    make_list_fighter,
    make_equipment,
    make_weapon_profile,
):
    spoon = make_equipment(
        "Wooden Spoon",
        category=ContentEquipmentCategory.objects.get(name="Basic Weapons"),
        cost=10,
    )

    spoon_profile = make_weapon_profile(spoon)
    spoon_scope, _ = ContentWeaponAccessory.objects.get_or_create(
        name="Spoon Scope", cost=10
    )

    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Test Fighter")

    ContentFighterEquipmentListWeaponAccessory.objects.create(
        fighter=fighter.content_fighter, weapon_accessory=spoon_scope, cost=5
    )

    # With the scope, the spoon is 10 + 0 + 10 = 20
    # With an equipment list entry for the scope, the price is 10 + 0 + 5 = 15
    lf_assign = fighter.assign(
        spoon, weapon_profiles=[spoon_profile], weapon_accessories=[spoon_scope]
    )

    assert lf_assign.cost_int() == 15

    # Reminder: assignments() returns List[VirtuaListFighterEquipmentAssignment]
    assert len(fighter.assignments()) == 1
    assignment = fighter.assignments()[0]
    assert assignment.content_equipment == spoon
    assert assignment.weapon_profiles()[0] == spoon_profile
    assert assignment.weapon_accessories()[0] == spoon_scope
    assert assignment.cost_int() == 15
    assert fighter.cost_int() == 115

    assignment._assignment.total_cost_override = 25
    assignment._assignment.save()

    assert assignment.cost_int() == 25
    assert fighter.cost_int() == 125


@pytest.mark.django_db
def test_list_fighter_with_same_equipment_different_profiles(
    content_house, content_fighter, content_equipment_categories
):
    spoon, _ = ContentEquipment.objects.get_or_create(
        name="Wooden Spoon",
        category=ContentEquipmentCategory.objects.get(name="Basic Weapons"),
        cost=10,
    )

    spoon_profile, _ = ContentWeaponProfile.objects.get_or_create(
        equipment=spoon,
        name="",
        defaults=dict(
            range_short="",
            range_long="E",
            accuracy_short="",
            accuracy_long="",
            strength="S-1",
            armour_piercing="+1",
            damage="1",
            ammo="4+",
        ),
    )

    spoon_spike_profile, _ = ContentWeaponProfile.objects.get_or_create(
        equipment=spoon,
        name="with Spike",
        defaults=dict(
            cost=5,
            range_short="",
            range_long="E",
            accuracy_short="",
            accuracy_long="",
            strength="S",
            armour_piercing="+2",
            damage="1",
            ammo="4+",
        ),
    )

    lst, _ = List.objects.get_or_create(name="Test List", content_house=content_house)
    fighter, _ = ListFighter.objects.get_or_create(
        name="Test Fighter", list=lst, content_fighter=content_fighter
    )

    assert fighter.cost_int() == 100

    # Assign the same equipment with different profiles
    fighter.assign(spoon, weapon_profiles=[spoon_profile])
    fighter.assign(spoon, weapon_profiles=[spoon_spike_profile])

    assert fighter.cost_int() == 125  # 100 base + 10 spoon + 15 spoon with spike

    assignment1 = ListFighterEquipmentAssignment.objects.get(
        list_fighter=fighter,
        content_equipment=spoon,
        weapon_profiles_field__in=[spoon_profile],
    )
    assignment2 = ListFighterEquipmentAssignment.objects.get(
        list_fighter=fighter,
        content_equipment=spoon,
        weapon_profiles_field__in=[spoon_spike_profile],
    )

    assert assignment1.cost_int() == 10
    assert assignment2.cost_int() == 15

    assert lst.cost_int() == 125

    weapon_assigns = fighter.weapons()
    assert len(weapon_assigns) == 2

    a1_profiles = assignment1.all_profiles()
    assert len(a1_profiles) == 1

    a2_profiles = assignment2.all_profiles()
    assert len(a2_profiles) == 2


@pytest.mark.django_db
def test_weapon_with_multiple_profiles(
    content_equipment_categories,
    content_house,
    content_fighter,
):
    spoon, _ = ContentEquipment.objects.get_or_create(
        name="Wooden Spoon",
        category=ContentEquipmentCategory.objects.get(name="Basic Weapons"),
        cost=10,
    )

    # Create multiple profiles for the same equipment
    spoon_profile1, _ = ContentWeaponProfile.objects.get_or_create(
        equipment=spoon,
        name="Profile 1",
        defaults=dict(
            range_short="",
            range_long="E",
            accuracy_short="",
            accuracy_long="",
            strength="S-1",
            armour_piercing="+1",
            damage="1",
            ammo="4+",
        ),
    )

    spoon_profile2, _ = ContentWeaponProfile.objects.get_or_create(
        equipment=spoon,
        name="Profile 2",
        defaults=dict(
            range_short="",
            range_long="E",
            accuracy_short="",
            accuracy_long="",
            strength="S-1",
            armour_piercing="+1",
            damage="1",
            ammo="4+",
        ),
    )

    spoon_profile_costed, _ = ContentWeaponProfile.objects.get_or_create(
        equipment=spoon,
        name="Profile with Cost",
        defaults=dict(
            cost=5,
            range_short="",
            range_long="E",
            accuracy_short="",
            accuracy_long="",
            strength="S",
            armour_piercing="+2",
            damage="1",
            ammo="4+",
        ),
    )

    lst, _ = List.objects.get_or_create(name="Test List", content_house=content_house)
    fighter, _ = ListFighter.objects.get_or_create(
        name="Test Fighter", list=lst, content_fighter=content_fighter
    )

    assert fighter.cost_int() == 100

    # Assign the costed profile to the fighter
    fighter.assign(spoon, weapon_profiles=[spoon_profile_costed])

    assert fighter.cost_int() == 115  # 100 base + 10 spoon + 5 profile cost

    assignment = ListFighterEquipmentAssignment.objects.get(
        list_fighter=fighter,
        content_equipment=spoon,
        weapon_profiles_field__in=[spoon_profile_costed],
    )

    assert assignment.cost_int() == 15
    assert assignment.base_cost_int() == 10
    assert assignment.weapon_profiles_cost_int() == 5

    assert lst.cost_int() == 115

    weapon_assigns = fighter.weapons()
    assert len(weapon_assigns) == 1

    first_assign = weapon_assigns[0]
    assert first_assign.cost_int() == 15


@pytest.mark.django_db
def test_weapon_with_multiple_costed_profiles(
    content_equipment_categories, content_house, content_fighter
):
    spoon, _ = ContentEquipment.objects.get_or_create(
        name="Wooden Spoon",
        category=ContentEquipmentCategory.objects.get(name="Basic Weapons"),
        cost=10,
    )

    # Create multiple profiles for the same equipment
    spoon_profile1, _ = ContentWeaponProfile.objects.get_or_create(
        equipment=spoon,
        name="Profile 1",
        defaults=dict(
            range_short="",
            range_long="E",
            accuracy_short="",
            accuracy_long="",
            strength="S-1",
            armour_piercing="+1",
            damage="1",
            ammo="4+",
        ),
    )

    spoon_profile_costed1, _ = ContentWeaponProfile.objects.get_or_create(
        equipment=spoon,
        name="Profile with Cost 1",
        defaults=dict(
            cost=5,
            range_short="",
            range_long="E",
            accuracy_short="",
            accuracy_long="",
            strength="S",
            armour_piercing="+2",
            damage="1",
            ammo="4+",
        ),
    )

    spoon_profile_costed2, _ = ContentWeaponProfile.objects.get_or_create(
        equipment=spoon,
        name="Profile with Cost 2",
        defaults=dict(
            cost=7,
            range_short="",
            range_long="E",
            accuracy_short="",
            accuracy_long="",
            strength="S+1",
            armour_piercing="+3",
            damage="2",
            ammo="3+",
        ),
    )

    lst, _ = List.objects.get_or_create(name="Test List", content_house=content_house)
    fighter, _ = ListFighter.objects.get_or_create(
        name="Test Fighter", list=lst, content_fighter=content_fighter
    )

    assert fighter.cost_int() == 100

    # Assign both costed profile to the fighter
    assignment = fighter.assign(
        spoon, weapon_profiles=[spoon_profile_costed1, spoon_profile_costed2]
    )

    assert (
        fighter.cost_int() == 122
    )  # 100 base + 10 spoon + 5 profile cost + 7 profile cost

    assert assignment.cost_int() == 22

    assert lst.cost_int() == 122

    weapon_assigns = fighter.weapons()
    assert len(weapon_assigns) == 1

    first_assign = weapon_assigns[0]
    assert first_assign.cost_int() == 22

    assert assignment.weapon_profiles_display() == [
        dict(
            profile=spoon_profile_costed1,
            cost_int=5,
            cost_display="+5¢",
        ),
        dict(
            profile=spoon_profile_costed2,
            cost_int=7,
            cost_display="+7¢",
        ),
    ]


@pytest.mark.django_db
def test_list_fighter_legacy(make_list, make_content_house, make_content_fighter):
    """
    This is testing that fighters can have a "legacy" association with a different
    content fighter than their base type, giving them costs from that fighter.

    The use-case is Venators House Legacy, BoP p16.
    """
    fighter_house = make_content_house("Fighter House")
    content_fighter_no_legacy = make_content_fighter(
        type="Test Fighter",
        category=FighterCategoryChoices.LEADER,
        house=fighter_house,
        base_cost=100,
        can_take_legacy=False,
    )
    content_fighter_legacy = make_content_fighter(
        type="Test Fighter",
        category=FighterCategoryChoices.LEADER,
        house=fighter_house,
        base_cost=100,
        can_take_legacy=True,
    )

    legacy_house = make_content_house("Legacy House")
    legacy_content_fighter = make_content_fighter(
        type="Legacy Fighter",
        category=FighterCategoryChoices.LEADER,
        house=legacy_house,
        base_cost=100,
        can_be_legacy=True,
    )
    legacy_content_fighter_nl = make_content_fighter(
        type="Legacy Fighter 2",
        category=FighterCategoryChoices.LEADER,
        house=legacy_house,
        base_cost=100,
        can_be_legacy=False,
    )

    lst = make_list(name="Test List", content_house=fighter_house)
    fighter_nl, _ = ListFighter.objects.get_or_create(
        name="Test Fighter (No Legacy)",
        list=lst,
        content_fighter=content_fighter_no_legacy,
        owner=lst.owner,
    )
    fighter_l, _ = ListFighter.objects.get_or_create(
        name="Test Fighter (No Legacy)",
        list=lst,
        content_fighter=content_fighter_legacy,
        owner=lst.owner,
    )
    fighter_l_cf_nl, _ = ListFighter.objects.get_or_create(
        name="Test Fighter (No Legacy)",
        list=lst,
        content_fighter=content_fighter_legacy,
        owner=lst.owner,
    )

    with pytest.raises(ValidationError):
        fighter_nl.legacy_content_fighter = legacy_content_fighter
        fighter_nl.full_clean()

    # The list fighter is allowed to have a legacy content fighter, but
    # the content fighter is not allowed to be a legacy fighter.
    with pytest.raises(ValidationError):
        fighter_l.legacy_content_fighter = legacy_content_fighter_nl
        fighter_l.full_clean()

    fighter_l.legacy_content_fighter = legacy_content_fighter
    fighter_l.full_clean()


@pytest.mark.django_db
def test_weapon_cost_legacy_equipment_list_override(
    content_equipment_categories, make_content_house, make_content_fighter
):
    """
    This is testing that fighters can have a "legacy" association with a different
    content fighter than their base type, giving them costs from that fighter.

    The use-case is Venators House Legacy, BoP p16.
    """
    fighter_house = make_content_house("Fighter House")
    content_fighter = make_content_fighter(
        type="Test Fighter",
        category=FighterCategoryChoices.JUVE,
        house=fighter_house,
        base_cost=100,
        can_take_legacy=True,
    )

    legacy_house = make_content_house("Legacy House")
    legacy_content_fighter = make_content_fighter(
        type="Legacy Fighter",
        category=FighterCategoryChoices.JUVE,
        house=legacy_house,
        base_cost=100,
        can_be_legacy=True,
    )

    spoon, _ = ContentEquipment.objects.get_or_create(
        name="Wooden Spoon",
        category=ContentEquipmentCategory.objects.get(name="Basic Weapons"),
        cost=10,
    )

    # Our legacy guy gets spoons on the cheap
    ContentFighterEquipmentListItem.objects.get_or_create(
        fighter=legacy_content_fighter, equipment=spoon, cost=5
    )

    lst, _ = List.objects.get_or_create(name="Test List", content_house=fighter_house)
    fighter, _ = ListFighter.objects.get_or_create(
        name="Test Fighter", list=lst, content_fighter=content_fighter
    )

    fighter.legacy_content_fighter = legacy_content_fighter
    # TODO: Test that this throws if CF cannot take legacy
    # fighter.full_clean()  # This will trigger the validation
    fighter.save()

    fighter = ListFighter.objects.get(pk=fighter.pk)

    assert fighter.cost_int() == 100

    fighter.assign(spoon)

    assert fighter.cost_int() == 105

    assignment = ListFighterEquipmentAssignment.objects.get(
        list_fighter=fighter, content_equipment=spoon
    )

    assert assignment.cost_int() == 5
    assert assignment.base_cost_int() == 5
    assert assignment.base_cost_display() == "5¢"


@pytest.mark.django_db
def test_weapon_cost_legacy_equipment_list_override_with_profile(
    content_equipment_categories, make_content_house, make_content_fighter
):
    """
    This is testing that fighters can have a "legacy" association with a different
    content fighter than their base type, giving them costs from that fighter.

    The use-case is Venators House Legacy, BoP p16.
    """
    fighter_house = make_content_house("Fighter House")
    content_fighter = make_content_fighter(
        type="Test Fighter",
        category=FighterCategoryChoices.JUVE,
        house=fighter_house,
        base_cost=100,
        can_take_legacy=True,
    )

    legacy_house = make_content_house("Legacy House")
    legacy_content_fighter = make_content_fighter(
        type="Legacy Fighter",
        category=FighterCategoryChoices.JUVE,
        house=legacy_house,
        base_cost=100,
    )

    spoon, _ = ContentEquipment.objects.get_or_create(
        name="Wooden Spoon",
        category=ContentEquipmentCategory.objects.get(name="Basic Weapons"),
        cost=10,
    )

    spoon_spike_profile, _ = ContentWeaponProfile.objects.get_or_create(
        equipment=spoon,
        name="with Spike",
        defaults=dict(
            cost=5,
            range_short="",
            range_long="E",
            accuracy_short="",
            accuracy_long="",
            strength="S",
            armour_piercing="+2",
            damage="1",
            ammo="4+",
        ),
    )

    # The legacy guy gets spikes on his spoons for cheap, but spoons at full cost.
    ContentFighterEquipmentListItem.objects.get_or_create(
        fighter=legacy_content_fighter,
        equipment=spoon,
        cost=10,
    )

    ContentFighterEquipmentListItem.objects.get_or_create(
        fighter=legacy_content_fighter,
        equipment=spoon,
        weapon_profile=spoon_spike_profile,
        cost=2,
    )

    lst, _ = List.objects.get_or_create(name="Test List", content_house=fighter_house)
    fighter, _ = ListFighter.objects.get_or_create(
        name="Test Fighter",
        list=lst,
        content_fighter=content_fighter,
        legacy_content_fighter=legacy_content_fighter,
    )

    assert fighter.cost_int() == 100

    # Duel-wield spoons
    fighter.assign(spoon)
    fighter.assign(spoon, weapon_profiles=[spoon_spike_profile])

    # The cost is 100 base + 10 spoon + 10 spoon + 2 profile cost
    # If the profile cost was not overridden, it would be 100 + 10 + 10 + 5 -> 125
    assert fighter.cost_int() == 122

    assignment = ListFighterEquipmentAssignment.objects.get(
        list_fighter=fighter,
        content_equipment=spoon,
        weapon_profiles_field=None,
    )

    assert assignment.cost_int() == 10
    assert assignment.base_cost_int() == 10
    assert assignment.base_cost_display() == "10¢"
    assert assignment.weapon_profiles_cost_int() == 0
    assert assignment.weapon_profiles_cost_display() == "+0¢"

    spike_assignment = ListFighterEquipmentAssignment.objects.get(
        list_fighter=fighter,
        content_equipment=spoon,
        weapon_profiles_field__in=[spoon_spike_profile],
    )

    assert spike_assignment.cost_int() == 12
    assert spike_assignment.cost_display() == "12¢"
    assert spike_assignment.base_cost_int() == 10
    assert spike_assignment.base_cost_display() == "10¢"
    assert spike_assignment.weapon_profiles_cost_int() == 2
    assert spike_assignment.weapon_profiles_cost_display() == "+2¢"


@pytest.mark.django_db
def test_weapon_cost_legacy_equipment_list_override_with_accessory(
    content_equipment_categories,
    make_content_house,
    make_content_fighter,
    make_equipment,
    make_weapon_profile,
):
    """
    This is testing that fighters can have a "legacy" association with a different
    content fighter than their base type, giving them costs from that fighter.

    The use-case is Venators House Legacy, BoP p16.
    """
    fighter_house = make_content_house("Fighter House")
    content_fighter = make_content_fighter(
        type="Test Fighter",
        category=FighterCategoryChoices.JUVE,
        house=fighter_house,
        base_cost=100,
        can_take_legacy=True,
    )

    legacy_house = make_content_house("Legacy House")
    legacy_content_fighter = make_content_fighter(
        type="Legacy Fighter",
        category=FighterCategoryChoices.JUVE,
        house=legacy_house,
        base_cost=100,
    )

    spoon = make_equipment(
        "Wooden Spoon",
        category=ContentEquipmentCategory.objects.get(name="Basic Weapons"),
        cost=10,
    )

    make_weapon_profile(spoon, cost=5)

    spoon_scope, _ = ContentWeaponAccessory.objects.get_or_create(
        name="Spoon Scope", cost=10
    )

    # The legacy guy gets spoons scope on the cheap
    ContentFighterEquipmentListWeaponAccessory.objects.create(
        fighter=legacy_content_fighter, weapon_accessory=spoon_scope, cost=5
    )

    lst, _ = List.objects.get_or_create(name="Test List", content_house=fighter_house)
    fighter, _ = ListFighter.objects.get_or_create(
        name="Test Fighter",
        list=lst,
        content_fighter=content_fighter,
        legacy_content_fighter=legacy_content_fighter,
    )

    assert fighter.cost_int() == 100

    fighter.assign(spoon, weapon_accessories=[spoon_scope])

    # The cost is 100 base + 10 spoon + 5 scope -> 115
    # If the profile cost was not overridden, it would be 100 + 10 + 10 -> 120
    assert fighter.cost_int() == 115


@pytest.mark.django_db
def test_virtual_assignments(
    content_house, content_fighter, content_equipment_categories
):
    spoon, _ = ContentEquipment.objects.get_or_create(
        name="Wooden Spoon",
        category=ContentEquipmentCategory.objects.get(name="Basic Weapons"),
        cost=10,
    )

    # Create multiple profiles for the same equipment
    spoon_profile1, _ = ContentWeaponProfile.objects.get_or_create(
        equipment=spoon,
        name="Profile 1",
    )

    spoon_profile_costed1, _ = ContentWeaponProfile.objects.get_or_create(
        equipment=spoon,
        name="Profile with Cost 1",
        cost=5,
    )

    spoon_profile_costed2, _ = ContentWeaponProfile.objects.get_or_create(
        equipment=spoon,
        name="Profile with Cost 2",
        cost=7,
    )

    lst, _ = List.objects.get_or_create(name="Test List", content_house=content_house)
    fighter, _ = ListFighter.objects.get_or_create(
        name="Test Fighter", list=lst, content_fighter=content_fighter
    )

    assert fighter.cost_int() == 100

    # Assign both costed profile to the fighter
    assignment = fighter.assign(
        spoon, weapon_profiles=[spoon_profile_costed1, spoon_profile_costed2]
    )

    v_assignment = VirtualListFighterEquipmentAssignment.from_assignment(assignment)

    assert (
        fighter.cost_int() == 122
    )  # 100 base + 10 spoon + 5 profile cost + 7 profile cost

    assert v_assignment.cost_int() == 22

    weapon_assigns = fighter.weapons()
    assert len(weapon_assigns) == 1

    first_assign = weapon_assigns[0]
    assert first_assign.cost_int() == 22

    assert v_assignment.weapon_profiles_display() == [
        dict(
            profile=spoon_profile_costed1,
            cost_int=5,
            cost_display="+5¢",
        ),
        dict(
            profile=spoon_profile_costed2,
            cost_int=7,
            cost_display="+7¢",
        ),
    ]

    assert v_assignment.name() == assignment.name()
    assert v_assignment.content_equipment == assignment.content_equipment
    assert v_assignment._profiles_cost_int() == 12
    assert v_assignment.name() == assignment.name()
    assert list(v_assignment.all_profiles()) == list(assignment.all_profiles())
    assert list(v_assignment.standard_profiles()) == list(
        assignment.standard_profiles()
    )


@pytest.mark.django_db
def test_weapon_equipment_match(
    content_fighter,
    content_equipment_categories,
    make_list,
    make_equipment,
    make_list_fighter,
):
    spoon, _ = ContentEquipment.objects.get_or_create(
        name="Wooden Spoon",
        category=ContentEquipmentCategory.objects.get(name="Basic Weapons"),
        cost=5,
    )
    fork, _ = ContentEquipment.objects.get_or_create(
        name="Fork",
        category=ContentEquipmentCategory.objects.get(name="Basic Weapons"),
        cost=10,
    )
    spoon_profile, _ = ContentWeaponProfile.objects.get_or_create(
        equipment=spoon,
        name="",
    )

    lst = make_list("Test List")
    fighter = make_list_fighter(lst, content_fighter)

    with pytest.raises(Exception):
        fighter.assign(fork, weapon_profiles=[spoon_profile])


@pytest.mark.django_db
def test_equipment_upgrades(
    content_fighter, make_list, make_equipment, make_list_fighter
):
    spoon = make_equipment(
        "Wooden Spoonetika",
        category=ContentEquipmentCategory.objects.get(name="Cyberteknika"),
        cost=50,
    )

    u1 = ContentEquipmentUpgrade.objects.create(
        equipment=spoon, name="Alpha", cost=20, position=0
    )
    u2 = ContentEquipmentUpgrade.objects.create(
        equipment=spoon, name="Beta", cost=30, position=1
    )

    lst = make_list("Test List")
    fighter = make_list_fighter(lst, content_fighter)

    assign = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter, content_equipment=spoon
    )

    assert assign.cost_int() == 50
    assert u1.cost_int() == 20
    assert u2.cost_int() == 50

    assign.upgrades_field.add(u2)
    assign.save()

    # Refresh the object because there is caching
    assign = ListFighterEquipmentAssignment.objects.get(id=assign.id)

    assert assign.cost_int() == 100
    assert fighter.cost_int() == 200

    vassign = VirtualListFighterEquipmentAssignment.from_assignment(assign)
    assert vassign.active_upgrades_display == [
        {"name": "Beta", "cost_display": "+50¢", "cost_int": 50, "upgrade": u2},
    ]


@pytest.mark.django_db
def test_invalid_equipment_upgrade(
    content_fighter, make_list, make_equipment, make_list_fighter
):
    spoon = make_equipment(
        "Wooden Spoonteknika",
        category=ContentEquipmentCategory.objects.get(name="Cyberteknika"),
        cost=50,
    )
    fork = make_equipment(
        "Forkteknika",
        category=ContentEquipmentCategory.objects.get(name="Cyberteknika"),
        cost=50,
    )

    ContentEquipmentUpgrade.objects.create(
        equipment=spoon, name="Alpha", cost=20, position=0
    )
    u2 = ContentEquipmentUpgrade.objects.create(
        equipment=spoon, name="Beta", cost=30, position=1
    )

    lst = make_list("Test List")
    fighter = make_list_fighter(lst, content_fighter)

    assign = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter, content_equipment=fork
    )

    assert assign.cost_int() == 50

    assign.upgrades_field.add(u2)

    with pytest.raises(Exception):
        assign.full_clean()


@pytest.mark.django_db
def test_multi_equipment_upgrades(
    content_fighter,
    content_equipment_categories,
    make_list,
    make_equipment,
    make_list_fighter,
):
    spoon = make_equipment(
        "Catborn",
        category=ContentEquipmentCategory.objects.get(name="Basic Weapons"),
        cost=50,
        upgrade_mode=ContentEquipment.UpgradeMode.MULTI,
    )

    u1 = ContentEquipmentUpgrade.objects.create(equipment=spoon, name="Alpha", cost=20)
    u2 = ContentEquipmentUpgrade.objects.create(equipment=spoon, name="Beta", cost=30)

    lst = make_list("Test List")
    fighter = make_list_fighter(lst, content_fighter)

    assign = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter, content_equipment=spoon
    )

    assert assign.cost_int() == 50
    assert u1.cost_int() == 20
    # Multi upgrades are summed by position in the stack
    assert u2.cost_int() == 30

    assign.upgrades_field.add(u2)
    assign.save()

    # Refresh the object because there is caching
    assign = ListFighterEquipmentAssignment.objects.get(id=assign.id)

    assert assign.cost_int() == 80
    assert fighter.cost_int() == 180

    assign.upgrades_field.add(u1)
    assign.save()

    # Refresh the object because there is caching
    assign = ListFighterEquipmentAssignment.objects.get(id=assign.id)

    assert assign.cost_int() == 100
    assert fighter.cost_int() == 200

    vassign = VirtualListFighterEquipmentAssignment.from_assignment(assign)
    assert vassign.active_upgrades_display == [
        {"name": "Alpha", "cost_display": "+20¢", "cost_int": 20, "upgrade": u1},
        {"name": "Beta", "cost_display": "+30¢", "cost_int": 30, "upgrade": u2},
    ]


@pytest.mark.django_db
def test_m2m_triggers_cost_recalculation(
    content_fighter,
    content_equipment_categories,
    make_list,
    make_equipment,
    make_list_fighter,
):
    """Test that M2M field changes result in correct cost calculations."""
    # Create test data
    weapon = make_equipment(
        "Test Weapon",
        category=ContentEquipmentCategory.objects.get(name="Basic Weapons"),
        cost=50,
    )

    # Create weapon profile with cost
    profile = ContentWeaponProfile.objects.create(
        equipment=weapon,
        name="Profile 1",
        cost=25,
    )

    # Create weapon accessory with cost
    accessory = ContentWeaponAccessory.objects.create(
        name="Test Accessory",
        cost=15,
    )

    # Create upgrade with cost
    upgrade = ContentEquipmentUpgrade.objects.create(
        equipment=weapon,
        name="Test Upgrade",
        cost=20,
    )

    lst = make_list("Test List")
    fighter = make_list_fighter(lst, content_fighter)

    # Create equipment assignment
    assign = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter, content_equipment=weapon
    )

    # Initial costs
    initial_assign_cost = assign.cost_int()
    initial_fighter_cost = fighter.cost_int()
    initial_list_cost = lst.cost_int()

    # Test weapon_profiles_field M2M trigger
    assign.weapon_profiles_field.add(profile)

    # Refresh the object because there is caching
    assign = ListFighterEquipmentAssignment.objects.get(id=assign.id)
    fighter = ListFighter.objects.get(id=fighter.id)
    lst = List.objects.get(id=lst.id)

    assert assign.cost_int() == initial_assign_cost + profile.cost_int()
    assert fighter.cost_int() == initial_fighter_cost + profile.cost_int()
    assert lst.cost_int() == initial_list_cost + profile.cost_int()

    # Test weapon_accessories_field M2M trigger
    assign.weapon_accessories_field.add(accessory)

    # Refresh the object because there is caching
    assign = ListFighterEquipmentAssignment.objects.get(id=assign.id)
    fighter = ListFighter.objects.get(id=fighter.id)
    lst = List.objects.get(id=lst.id)

    assert (
        assign.cost_int()
        == initial_assign_cost + profile.cost_int() + accessory.cost_int()
    )
    assert (
        fighter.cost_int()
        == initial_fighter_cost + profile.cost_int() + accessory.cost_int()
    )
    assert (
        lst.cost_int() == initial_list_cost + profile.cost_int() + accessory.cost_int()
    )

    # Test upgrades_field M2M trigger
    assign.upgrades_field.add(upgrade)

    # Refresh the object because there is caching
    assign = ListFighterEquipmentAssignment.objects.get(id=assign.id)
    fighter = ListFighter.objects.get(id=fighter.id)
    lst = List.objects.get(id=lst.id)

    final_expected_cost = (
        initial_assign_cost
        + profile.cost_int()
        + accessory.cost_int()
        + upgrade.cost_int()
    )
    assert assign.cost_int() == final_expected_cost
    assert (
        fighter.cost_int()
        == initial_fighter_cost
        + profile.cost_int()
        + accessory.cost_int()
        + upgrade.cost_int()
    )
    assert (
        lst.cost_int()
        == initial_list_cost
        + profile.cost_int()
        + accessory.cost_int()
        + upgrade.cost_int()
    )

    # Test removing M2M relationships also triggers cache updates
    assign.weapon_profiles_field.remove(profile)

    # Refresh the object because there is caching
    assign = ListFighterEquipmentAssignment.objects.get(id=assign.id)
    fighter = ListFighter.objects.get(id=fighter.id)
    lst = List.objects.get(id=lst.id)

    expected_cost_after_remove = final_expected_cost - profile.cost_int()
    assert assign.cost_int() == expected_cost_after_remove
    assert (
        fighter.cost_int()
        == initial_fighter_cost + accessory.cost_int() + upgrade.cost_int()
    )
    assert (
        lst.cost_int() == initial_list_cost + accessory.cost_int() + upgrade.cost_int()
    )


@pytest.mark.django_db
def test_fighter_category_override(content_fighter, make_list, make_list_fighter):
    """Test that category_override overrides the fighter's content category."""
    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Test Fighter")

    # Initially, should use content_fighter's category
    assert fighter.get_category() == content_fighter.category

    # Set a category override
    fighter.category_override = FighterCategoryChoices.LEADER
    fighter.save()

    # Now should return the override
    assert fighter.get_category() == FighterCategoryChoices.LEADER

    # Clear the override
    fighter.category_override = None
    fighter.save()

    # Should fall back to content_fighter's category
    assert fighter.get_category() == content_fighter.category


@pytest.mark.django_db
def test_fighter_category_override_fully_qualified_name(
    content_fighter, make_list, make_list_fighter
):
    """Test that fully_qualified_name uses the category override."""
    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Bob")

    # Get the original fully qualified name
    original_name = fighter.fully_qualified_name

    # Set a category override to LEADER
    fighter.category_override = FighterCategoryChoices.LEADER
    fighter.save()

    # Clear the cached property
    del fighter.fully_qualified_name

    # The fully qualified name should now use the overridden category
    expected_name = f"Bob - {content_fighter.type} (Leader)"
    assert fighter.fully_qualified_name == expected_name

    # Clear the override
    fighter.category_override = None
    fighter.save()

    # Clear the cached property
    del fighter.fully_qualified_name

    # Should be back to original
    assert fighter.fully_qualified_name == original_name


@pytest.mark.django_db
def test_fighter_category_override_sorting(content_house):
    """Test that fighters are sorted by their overridden category."""
    lst = List.objects.create(name="Test List", content_house=content_house)

    # Create fighters with different categories
    juve_fighter = ContentFighter.objects.create(
        type="Test Juve",
        category=FighterCategoryChoices.JUVE,
        house=content_house,
        base_cost=50,
    )
    ganger_fighter = ContentFighter.objects.create(
        type="Test Ganger",
        category=FighterCategoryChoices.GANGER,
        house=content_house,
        base_cost=60,
    )

    # Create list fighters
    fighter1 = ListFighter.objects.create(
        name="Fighter 1", content_fighter=juve_fighter, list=lst
    )
    fighter2 = ListFighter.objects.create(
        name="Fighter 2", content_fighter=ganger_fighter, list=lst
    )

    # Initially, fighter2 (ganger) should come before fighter1 (juve) in sorting
    fighters = ListFighter.objects.filter(list=lst).order_by("_category_order", "name")
    assert list(fighters) == [fighter2, fighter1]

    # Override fighter1's category to LEADER
    fighter1.category_override = FighterCategoryChoices.LEADER
    fighter1.save()

    # Now fighter1 (overridden to leader) should come first
    fighters = ListFighter.objects.filter(list=lst).order_by("_category_order", "name")
    assert list(fighters) == [fighter1, fighter2]


@pytest.mark.django_db
def test_fighter_category_override_restricted_categories(content_house):
    """Test that category override only allows specific categories."""
    from gyrinx.core.models.list import (
        ALLOWED_CATEGORY_OVERRIDES,
        validate_category_override,
    )

    lst = List.objects.create(name="Test List", content_house=content_house)

    # Create a regular fighter
    regular_fighter = ContentFighter.objects.create(
        type="Test Fighter",
        category=FighterCategoryChoices.GANGER,
        house=content_house,
        base_cost=50,
    )

    fighter = ListFighter.objects.create(
        name="Fighter", content_fighter=regular_fighter, list=lst
    )

    # Test that allowed overrides work
    for category in ALLOWED_CATEGORY_OVERRIDES:
        fighter.category_override = category
        # Validate the category_override field directly
        validate_category_override(category)  # Should not raise
        fighter.save()
        assert fighter.get_category() == category

    # Test that disallowed categories raise validation error
    disallowed_categories = [
        FighterCategoryChoices.VEHICLE,
        FighterCategoryChoices.STASH,
        FighterCategoryChoices.EXOTIC_BEAST,
        FighterCategoryChoices.BRUTE,
        FighterCategoryChoices.HIRED_GUN,
    ]

    for category in disallowed_categories:
        with pytest.raises(ValidationError):
            validate_category_override(category)


@pytest.mark.django_db
def test_fighter_category_override_equipment_restrictions(content_house):
    """Test that equipment category restrictions respect category overrides."""
    from gyrinx.content.models import (
        ContentEquipment,
        ContentEquipmentCategory,
        ContentEquipmentCategoryFighterRestriction,
        ContentFighterEquipmentListItem,
    )

    lst = List.objects.create(name="Test List", content_house=content_house)

    # Create a JUVE fighter
    juve_fighter = ContentFighter.objects.create(
        type="Test Juve",
        category=FighterCategoryChoices.JUVE,
        house=content_house,
        base_cost=50,
    )

    # Create equipment categories with restrictions
    leader_only_category = ContentEquipmentCategory.objects.create(
        name="Leader Equipment", group="Equipment"
    )
    ContentEquipmentCategoryFighterRestriction.objects.create(
        equipment_category=leader_only_category,
        fighter_category=FighterCategoryChoices.LEADER,
    )

    all_fighters_category = ContentEquipmentCategory.objects.create(
        name="Common Equipment", group="Equipment"
    )
    # No restrictions - available to all

    juve_ganger_category = ContentEquipmentCategory.objects.create(
        name="Juve/Ganger Equipment", group="Equipment"
    )
    ContentEquipmentCategoryFighterRestriction.objects.create(
        equipment_category=juve_ganger_category,
        fighter_category=FighterCategoryChoices.JUVE,
    )
    ContentEquipmentCategoryFighterRestriction.objects.create(
        equipment_category=juve_ganger_category,
        fighter_category=FighterCategoryChoices.GANGER,
    )

    # Create equipment in each category
    leader_equipment = ContentEquipment.objects.create(
        name="Leader Sword",
        category=leader_only_category,
        rarity="C",
        cost="50",
    )
    common_equipment = ContentEquipment.objects.create(
        name="Common Knife",
        category=all_fighters_category,
        rarity="C",
        cost="10",
    )
    juve_equipment = ContentEquipment.objects.create(
        name="Juve/Ganger Pistol",
        category=juve_ganger_category,
        rarity="C",
        cost="20",
    )

    # Create the list fighter
    fighter = ListFighter.objects.create(
        name="Test Fighter", content_fighter=juve_fighter, list=lst
    )

    # Add all equipment to the fighter's equipment list
    ContentFighterEquipmentListItem.objects.create(
        fighter=juve_fighter, equipment=leader_equipment
    )
    ContentFighterEquipmentListItem.objects.create(
        fighter=juve_fighter, equipment=common_equipment
    )
    ContentFighterEquipmentListItem.objects.create(
        fighter=juve_fighter, equipment=juve_equipment
    )

    # Test 1: As a JUVE, should not have access to leader-only equipment
    assert fighter.get_category() == FighterCategoryChoices.JUVE
    assert not leader_only_category.is_available_to_fighter_category(
        fighter.get_category()
    )
    assert all_fighters_category.is_available_to_fighter_category(
        fighter.get_category()
    )
    assert juve_ganger_category.is_available_to_fighter_category(fighter.get_category())

    # Test 2: Override to LEADER, should now have access to leader equipment
    fighter.category_override = FighterCategoryChoices.LEADER
    fighter.save()

    assert fighter.get_category() == FighterCategoryChoices.LEADER
    assert leader_only_category.is_available_to_fighter_category(fighter.get_category())
    assert all_fighters_category.is_available_to_fighter_category(
        fighter.get_category()
    )
    assert not juve_ganger_category.is_available_to_fighter_category(
        fighter.get_category()
    )

    # Test 3: Override to GANGER, should have access to juve/ganger equipment but not leader
    fighter.category_override = FighterCategoryChoices.GANGER
    fighter.save()

    assert fighter.get_category() == FighterCategoryChoices.GANGER
    assert not leader_only_category.is_available_to_fighter_category(
        fighter.get_category()
    )
    assert all_fighters_category.is_available_to_fighter_category(
        fighter.get_category()
    )
    assert juve_ganger_category.is_available_to_fighter_category(fighter.get_category())

    # Test 4: Clear override, should revert to original JUVE restrictions
    fighter.category_override = None
    fighter.save()

    assert fighter.get_category() == FighterCategoryChoices.JUVE
    assert not leader_only_category.is_available_to_fighter_category(
        fighter.get_category()
    )
    assert all_fighters_category.is_available_to_fighter_category(
        fighter.get_category()
    )
    assert juve_ganger_category.is_available_to_fighter_category(fighter.get_category())


@pytest.mark.django_db
def test_list_rating_calculation(
    content_house, make_list, make_list_fighter, make_content_fighter, user
):
    """Test that rating only includes active fighters."""
    # Create a list with multiple fighters
    lst = make_list("Test Gang")

    # Create regular fighters with different costs
    fighter1_template = make_content_fighter(
        type="Fighter 1",
        category=FighterCategoryChoices.GANGER,
        house=content_house,
        base_cost=50,
    )
    fighter2_template = make_content_fighter(
        type="Fighter 2",
        category=FighterCategoryChoices.LEADER,
        house=content_house,
        base_cost=100,
    )
    fighter3_template = make_content_fighter(
        type="Fighter 3",
        category=FighterCategoryChoices.JUVE,
        house=content_house,
        base_cost=30,
    )

    # Create list fighters
    ListFighter.objects.create(
        list=lst,
        name="Fighter 1",
        content_fighter=fighter1_template,
        owner=user,
    )
    fighter2 = ListFighter.objects.create(
        list=lst,
        name="Fighter 2",
        content_fighter=fighter2_template,
        owner=user,
    )
    ListFighter.objects.create(
        list=lst,
        name="Fighter 3",
        content_fighter=fighter3_template,
        owner=user,
    )

    lst = List.objects.get(id=lst.id)  # Refresh to clear any cached properties

    # Rating should be the sum of active fighters only (50 + 100 + 30)
    assert lst.rating == 180
    assert lst.rating_display == "180¢"

    # Add a stash fighter - it should NOT count towards rating
    stash_fighter_template, _ = ContentFighter.objects.get_or_create(
        house=content_house,
        is_stash=True,
        defaults={
            "type": "Stash",
            "category": FighterCategoryChoices.STASH,
            "base_cost": 0,
        },
    )
    ListFighter.objects.create(
        list=lst,
        name="Stash",
        content_fighter=stash_fighter_template,
        owner=user,
    )

    lst = List.objects.get(id=lst.id)  # Refresh to clear any cached properties

    # Rating should still be 180 (stash not included)
    assert lst.rating == 180

    # Archive one fighter - it should no longer count towards rating
    fighter2.archived = True
    fighter2.save()

    lst = List.objects.get(id=lst.id)  # Refresh to clear any cached properties

    # Rating should now be 50 + 30 = 80
    assert lst.rating == 80
    assert lst.rating_display == "80¢"


@pytest.mark.django_db
def test_stash_fighter_cost_calculation(
    content_house, make_list, user, content_equipment_categories
):
    """Test stash fighter cost is calculated correctly."""
    lst = make_list("Test Gang")

    # Initially no stash, cost should be 0
    assert lst.stash_fighter_cost_int == 0
    assert lst.stash_fighter_cost_display == "0¢"

    # Create a stash fighter
    stash_fighter_template, _ = ContentFighter.objects.get_or_create(
        house=content_house,
        is_stash=True,
        defaults={
            "type": "Stash",
            "category": FighterCategoryChoices.STASH,
            "base_cost": 0,
        },
    )
    stash_fighter = ListFighter.objects.create(
        list=lst,
        name="Stash",
        content_fighter=stash_fighter_template,
        owner=user,
    )

    lst = List.objects.get(id=lst.id)  # Refresh to clear any cached properties

    # Stash fighter base cost should still be 0
    assert lst.stash_fighter_cost_int == 0

    # Add equipment to the stash
    weapon = ContentEquipment.objects.create(
        name="Test Weapon",
        category=ContentEquipmentCategory.objects.get(name="Basic Weapons"),
        cost=25,
    )
    armor = ContentEquipment.objects.create(
        name="Test Armor",
        category=ContentEquipmentCategory.objects.get(name="Armor"),
        cost=50,
    )

    ListFighterEquipmentAssignment.objects.create(
        list_fighter=stash_fighter,
        content_equipment=weapon,
    )
    ListFighterEquipmentAssignment.objects.create(
        list_fighter=stash_fighter,
        content_equipment=armor,
    )

    lst = List.objects.get(id=lst.id)  # Refresh to clear any cached properties

    # Stash fighter cost should now be 25 + 50 = 75
    assert lst.stash_fighter_cost_int == 75
    assert lst.stash_fighter_cost_display == "75¢"


@pytest.mark.django_db
def test_wealth_breakdown_display(
    content_house, make_list, make_list_fighter, make_content_fighter, user
):
    """Test the display formatting methods."""
    lst = make_list("Test Gang", credits_current=250)

    # Create a fighter
    fighter_template = make_content_fighter(
        type="Fighter",
        category=FighterCategoryChoices.GANGER,
        house=content_house,
        base_cost=100,
    )
    ListFighter.objects.create(
        list=lst,
        name="Test Fighter",
        content_fighter=fighter_template,
        owner=user,
    )

    # Create a stash fighter
    stash_fighter_template, _ = ContentFighter.objects.get_or_create(
        house=content_house,
        is_stash=True,
        defaults={
            "type": "Stash",
            "category": FighterCategoryChoices.STASH,
            "base_cost": 0,
        },
    )
    ListFighter.objects.create(
        list=lst,
        name="Stash",
        content_fighter=stash_fighter_template,
        owner=user,
    )

    # Sync facts after adding fighters
    lst.facts_from_db(update=True)

    # Fetch fresh list with proper prefetching so can_use_facts is True
    lst = List.objects.with_latest_actions().get(id=lst.id)

    # Test display methods
    assert lst.credits_current_display == "250¢"

    # Rating should be 100 (from fighter)
    assert lst.rating == 100
    assert lst.rating_display == "100¢"

    # Stash fighter cost should be 0 (no equipment)
    assert lst.stash_fighter_cost_int == 0
    assert lst.stash_fighter_cost_display == "0¢"

    # Total wealth (cost_int) should be rating + stash + credits = 100 + 0 + 250 = 350
    assert lst.cost_int() == 350
    assert lst.cost_display() == "350¢"

    # Test with larger numbers
    lst.credits_current = 1500
    lst.save()

    # Sync facts after changing credits
    lst.facts_from_db(update=True)

    # Fetch fresh list with proper prefetching
    lst = List.objects.with_latest_actions().get(id=lst.id)

    assert lst.credits_current_display == "1500¢"
    assert lst.cost_int() == 1600
    assert lst.cost_display() == "1600¢"


@pytest.mark.django_db
def test_fighter_type_summary_no_additional_queries(user, content_house):
    """Test that fighter_type_summary doesn't issue additional queries when using with_related_data."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    # Create a list
    lst = List.objects.create(
        name="Test List",
        content_house=content_house,
        owner=user,
    )

    # Create multiple fighters of different categories
    leader_template = ContentFighter.objects.create(
        type="Example Leader",
        category=FighterCategoryChoices.LEADER,
        house=content_house,
        base_cost=100,
    )
    ListFighter.objects.create(
        list=lst,
        name="Gang Leader",
        content_fighter=leader_template,
        owner=user,
    )

    ganger_template = ContentFighter.objects.create(
        type="Example Ganger",
        category=FighterCategoryChoices.GANGER,
        house=content_house,
        base_cost=50,
    )
    ListFighter.objects.create(
        list=lst,
        name="Ganger 1",
        content_fighter=ganger_template,
        owner=user,
    )
    ListFighter.objects.create(
        list=lst,
        name="Ganger 2",
        content_fighter=ganger_template,
        owner=user,
    )

    juve_template = ContentFighter.objects.create(
        type="Example Juve",
        category=FighterCategoryChoices.JUVE,
        house=content_house,
        base_cost=25,
    )
    juve_fighter = ListFighter.objects.create(
        list=lst,
        name="Juve 1",
        content_fighter=juve_template,
        owner=user,
    )

    # Create a stash fighter (should be excluded from summary)
    stash_template = ContentFighter.objects.create(
        type="Stash",
        category=FighterCategoryChoices.STASH,
        house=content_house,
        is_stash=True,
        base_cost=0,
    )
    ListFighter.objects.create(
        list=lst,
        name="Stash",
        content_fighter=stash_template,
        owner=user,
    )

    # Archive a fighter (should be excluded from summary)
    juve_fighter.archived = True
    juve_fighter.save()

    # Fetch the list with related data (as the view does)
    with CaptureQueriesContext(connection) as context:
        lst = List.objects.with_related_data(with_fighters=True).get(id=lst.id)
        query_count_after_fetch = len(context.captured_queries)

        # Access fighter_type_summary - should not issue additional queries
        summary = lst.fighter_type_summary
        query_count_after_summary = len(context.captured_queries)

    # Verify no additional queries were issued when accessing fighter_type_summary
    additional_queries = query_count_after_summary - query_count_after_fetch
    assert additional_queries == 0, (
        f"Expected 0 additional queries after fetching list, but got {additional_queries}. "
        f"Total queries: {query_count_after_summary}, queries after fetch: {query_count_after_fetch}"
    )

    # Verify the summary is correct
    assert len(summary) == 2  # Only leader and ganger (juve archived, stash excluded)

    # Convert to dict for easier testing
    summary_dict = {(item["type"], item["category"]): item["count"] for item in summary}

    assert (
        summary_dict[(leader_template.type, FighterCategoryChoices.LEADER.label)] == 1
    )
    assert (
        summary_dict[(ganger_template.type, FighterCategoryChoices.GANGER.label)] == 2
    )
    assert (
        juve_template.type,
        FighterCategoryChoices.JUVE.label,
    ) not in summary_dict  # Archived
    assert ("Stash", FighterCategoryChoices.STASH.label) not in summary_dict  # Excluded


@pytest.mark.django_db
def test_fighter_type_summary_with_category_override(user, content_house):
    """Test that fighter_type_summary respects category overrides."""
    # Create a list
    lst = List.objects.create(
        name="Test List",
        content_house=content_house,
        owner=user,
    )

    # Create a ganger fighter
    ganger_template = ContentFighter.objects.create(
        type="Example Ganger",
        category=FighterCategoryChoices.GANGER,
        house=content_house,
        base_cost=50,
    )

    # Create two fighters from the same template
    ListFighter.objects.create(
        list=lst,
        name="Regular Ganger",
        content_fighter=ganger_template,
        owner=user,
    )

    # Create a ganger with category override to champion
    ListFighter.objects.create(
        list=lst,
        name="Promoted Champion",
        content_fighter=ganger_template,
        category_override=FighterCategoryChoices.CHAMPION,
        owner=user,
    )

    # Fetch the list with related data
    lst = List.objects.with_related_data(with_fighters=True).get(id=lst.id)

    summary = lst.fighter_type_summary

    # Should have both ganger and champion
    assert len(summary) == 2

    summary_dict = {(item["type"], item["category"]): item["count"] for item in summary}
    assert (
        summary_dict[(ganger_template.type, FighterCategoryChoices.GANGER.label)] == 1
    )
    assert (
        summary_dict[(ganger_template.type, FighterCategoryChoices.CHAMPION.label)] == 1
    )


@pytest.mark.django_db
def test_fighter_type_summary_excludes_vehicles(user, content_house):
    """Test that fighter_type_summary excludes vehicles (vehicles are not fighters)."""
    # Create a list
    lst = List.objects.create(
        name="Test List",
        content_house=content_house,
        owner=user,
    )

    # Create a leader fighter
    leader_template = ContentFighter.objects.create(
        type="Example Leader",
        category=FighterCategoryChoices.LEADER,
        house=content_house,
        base_cost=100,
    )
    ListFighter.objects.create(
        list=lst,
        name="Gang Leader",
        content_fighter=leader_template,
        owner=user,
    )

    # Create a vehicle (should be excluded from summary)
    vehicle_template = ContentFighter.objects.create(
        type="Goliath Mauler",
        category=FighterCategoryChoices.VEHICLE,
        house=content_house,
        base_cost=200,
    )
    ListFighter.objects.create(
        list=lst,
        name="My Vehicle",
        content_fighter=vehicle_template,
        owner=user,
    )

    # Fetch the list with related data
    lst = List.objects.with_related_data(with_fighters=True).get(id=lst.id)

    summary = lst.fighter_type_summary

    # Should only have leader (vehicle excluded)
    assert len(summary) == 1

    summary_dict = {(item["type"], item["category"]): item["count"] for item in summary}
    assert (
        summary_dict[(leader_template.type, FighterCategoryChoices.LEADER.label)] == 1
    )
    # Vehicle should not be in summary
    assert (
        vehicle_template.type,
        FighterCategoryChoices.VEHICLE.label,
    ) not in summary_dict


@pytest.mark.django_db
def test_list_type_summary_exludes_dead_fighters(user, content_house):
    """Test that fighter_type_summary excludes dead fighters."""
    # Create a list
    lst = List.objects.create(
        name="Test List",
        content_house=content_house,
        owner=user,
    )

    # Create a leader fighter
    leader_template = ContentFighter.objects.create(
        type="Example Leader",
        category=FighterCategoryChoices.LEADER,
        house=content_house,
        base_cost=100,
    )
    ListFighter.objects.create(
        list=lst,
        name="Gang Leader",
        content_fighter=leader_template,
        owner=user,
    )

    # Create a dead fighter
    dead_fighter_template = ContentFighter.objects.create(
        type="Fallen Fighter",
        category=FighterCategoryChoices.GANGER,
        house=content_house,
        base_cost=50,
    )
    ListFighter.objects.create(
        list=lst,
        name="Dead Ganger",
        content_fighter=dead_fighter_template,
        owner=user,
        injury_state=ListFighter.DEAD,
    )

    # Fetch the list with related data
    lst = List.objects.with_related_data(with_fighters=True).get(id=lst.id)

    summary = lst.fighter_type_summary

    # Should only have leader (dead fighter excluded)
    assert len(summary) == 1

    summary_dict = {(item["type"], item["category"]): item["count"] for item in summary}
    assert (
        summary_dict[(leader_template.type, FighterCategoryChoices.LEADER.label)] == 1
    )
    # Dead fighter should not be in summary
    assert (
        dead_fighter_template.type,
        FighterCategoryChoices.GANGER.label,
    ) not in summary_dict
