import pytest
from django.core.cache import caches
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


def make_content():
    category = FighterCategoryChoices.JUVE
    house = ContentHouse.objects.create(
        name="Squat Prospectors",
    )
    fighter = ContentFighter.objects.create(
        type="Prospector Digger",
        category=category,
        house=house,
        base_cost=100,
    )
    return category, house, fighter


@pytest.mark.django_db
def test_basic_list():
    category, house, content_fighter = make_content()

    lst = List.objects.create(name="Test List", content_house=house)

    assert lst.name == "Test List"


@pytest.mark.django_db
def test_list_name_min_length():
    category, house, content_fighter = make_content()

    with pytest.raises(
        ValidationError, match="Ensure this value has at least 3 characters"
    ):
        lst = List(name="Te", content_house=house)
        lst.full_clean()  # This will trigger the validation


@pytest.mark.django_db
def test_basic_list_fighter():
    category, house, content_fighter = make_content()

    lst = List.objects.create(name="Test List", content_house=house)
    fighter = ListFighter.objects.create(
        name="Test Fighter", list=lst, content_fighter=content_fighter
    )

    assert lst.name == "Test List"
    assert fighter.name == "Test Fighter"


@pytest.mark.django_db
def test_fighter_name_min_length(user):
    category, house, content_fighter = make_content()
    lst = List.objects.create(name="Test List", content_house=house)

    with pytest.raises(
        ValidationError, match="Ensure this value has at least 3 characters"
    ):
        fighter = ListFighter(
            name="Te", list=lst, content_fighter=content_fighter, owner=user
        )
        fighter.full_clean()  # This will trigger the validation


@pytest.mark.django_db
def test_list_fighter_requires_content_fighter():
    category, house, content_fighter = make_content()
    lst = List.objects.create(name="Test List", content_house=house)
    with pytest.raises(Exception):
        ListFighter.objects.create(name="Test Fighter", list=lst)


@pytest.mark.django_db
def test_list_fighter_content_fighter():
    category, house, content_fighter = make_content()

    lst = List.objects.create(name="Test List", content_house=house)
    fighter = ListFighter.objects.create(
        name="Test Fighter", list=lst, content_fighter=content_fighter
    )

    assert fighter.content_fighter.type == "Prospector Digger"


@pytest.mark.django_db
def test_list_fighter_house_matches_list(user):
    category, house, content_fighter = make_content()

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
def test_archive_list():
    category, house, content_fighter = make_content()

    lst = List.objects.create(name="Test List", content_house=house)

    lst.archive()

    assert lst.archived
    assert lst.archived_at is not None


@pytest.mark.django_db
def test_history():
    category, house, content_fighter = make_content()

    lst = List.objects.create(name="Test List", content_house=house)

    assert lst.history.all().count() == 1

    lst.name = "Test List 2"
    lst.save()

    assert lst.history.all().count() == 2
    assert lst.history.first().name == "Test List 2"

    lst.archive()

    assert lst.history.first().archived
    assert not lst.history.first().prev_record.archived


@pytest.mark.django_db
def test_list_cost():
    category, house, content_fighter = make_content()

    lst = List.objects.create(name="Test List", content_house=house)
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
def test_list_cost_variable():
    category, house, content_fighter = make_content()
    content_fighter2 = ContentFighter.objects.create(
        type="Expensive Guy",
        category=category,
        house=house,
        base_cost=150,
    )

    lst = List.objects.create(name="Test List", content_house=house)
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
def test_list_cost_cache():
    category, house, content_fighter = make_content()

    spoon, _ = ContentEquipment.objects.get_or_create(
        name="Wooden Spoon",
        category=ContentEquipmentCategory.objects.get(name="Basic Weapons"),
        cost=10,
    )

    lst = List.objects.create(name="Test List", content_house=house)
    fighter = ListFighter.objects.create(
        name="Test Fighter", list=lst, content_fighter=content_fighter
    )

    assert fighter.cost_int() == content_fighter.cost_int()
    assert lst.cost_int() == fighter.cost_int()

    assert lst.cost_int_cached == fighter.cost_int()

    cache = caches["core_list_cache"]
    assert cache.has_key(lst.cost_cache_key())
    assert cache.get(lst.cost_cache_key()) == fighter.cost_int()

    fighter.cost_override = 50
    fighter.save()

    # Refresh the objects from the database... because caching!
    fighter = ListFighter.objects.get(pk=fighter.pk)
    lst = List.objects.get(pk=lst.pk)

    assert cache.get(lst.cost_cache_key()) == fighter.cost_int()
    assert lst.cost_int() == 50
    assert lst.cost_int_cached == 50

    pre_spoon_cost = fighter.cost_int()
    fighter.assign(spoon)

    lst = List.objects.get(pk=lst.pk)
    fighter = ListFighter.objects.get(pk=fighter.pk)
    post_spoon_cost = fighter.cost_int()

    assert post_spoon_cost == pre_spoon_cost + spoon.cost_int()
    assert cache.get(lst.cost_cache_key()) == post_spoon_cost
    assert lst.cost_int() == post_spoon_cost
    assert lst.cost_int_cached == post_spoon_cost


@pytest.mark.django_db
def test_list_cost_with_archived_fighter():
    category, house, content_fighter = make_content()
    expensive_guy = ContentFighter.objects.create(
        type="Expensive Guy",
        category=category,
        house=house,
        base_cost=150,
    )

    lst = List.objects.create(name="Test List", content_house=house)
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
def test_list_cost_with_fighter_cost_override():
    category, house, content_fighter = make_content()
    expensive_guy = ContentFighter.objects.create(
        type="Expensive Guy",
        category=category,
        house=house,
        base_cost=150,
    )

    lst = List.objects.create(name="Test List", content_house=house)
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
def test_list_fighter_with_spoon():
    category, house, content_fighter = make_content()
    spoon, _ = ContentEquipment.objects.get_or_create(
        name="Wooden Spoon",
        category=ContentEquipmentCategory.objects.get(name="Basic Weapons"),
        cost=10,
    )

    lst, _ = List.objects.get_or_create(name="Test List", content_house=house)
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
def test_list_fighter_with_spoon_weapon():
    category, house, content_fighter = make_content()
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

    lst, _ = List.objects.get_or_create(name="Test List", content_house=house)
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
def test_fighter_with_spoon_weapon_profile_with_cost():
    category, house, content_fighter = make_content()
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

    lst, _ = List.objects.get_or_create(name="Test List", content_house=house)
    fighter, _ = ListFighter.objects.get_or_create(
        name="Test Fighter", list=lst, content_fighter=content_fighter
    )

    assert fighter.cost_int() == 100

    fighter.assign(spoon, weapon_profiles=[spoon_spike_profile])

    assert fighter.cost_int() == 115

    assert lst.cost_int() == 115


@pytest.mark.django_db
def test_list_fighter_with_spoon_and_not_other_assignments():
    # This test was introduced to fix a bug where the cost of a fighter was
    # including all equipment assignments, not just the ones for that fighter.

    category, house, content_fighter = make_content()
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

    lst, _ = List.objects.get_or_create(name="Test List", content_house=house)
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
def test_profile_validation_standard_profile_non_zero_cost():
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
def test_weapon_cost_equipment_list_override():
    category, house, content_fighter = make_content()
    spoon, _ = ContentEquipment.objects.get_or_create(
        name="Wooden Spoon",
        category=ContentEquipmentCategory.objects.get(name="Basic Weapons"),
        cost=10,
    )

    # This guy gets spoons on the cheap
    ContentFighterEquipmentListItem.objects.get_or_create(
        fighter=content_fighter, equipment=spoon, cost=5
    )

    lst, _ = List.objects.get_or_create(name="Test List", content_house=house)
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
def test_weapon_cost_equipment_list_override_with_profile():
    category, house, content_fighter = make_content()
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

    lst, _ = List.objects.get_or_create(name="Test List", content_house=house)
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
def test_list_fighter_with_same_equipment_different_profiles():
    category, house, content_fighter = make_content()
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

    lst, _ = List.objects.get_or_create(name="Test List", content_house=house)
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
def test_weapon_with_multiple_profiles():
    category, house, content_fighter = make_content()
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

    lst, _ = List.objects.get_or_create(name="Test List", content_house=house)
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
def test_weapon_with_multiple_costed_profiles():
    category, house, content_fighter = make_content()
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

    lst, _ = List.objects.get_or_create(name="Test List", content_house=house)
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
    make_content_house, make_content_fighter
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
    make_content_house, make_content_fighter
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
    make_content_house, make_content_fighter, make_equipment, make_weapon_profile
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
def test_virtual_assignments():
    category, house, content_fighter = make_content()
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

    lst, _ = List.objects.get_or_create(name="Test List", content_house=house)
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
    content_fighter, make_list, make_equipment, make_list_fighter
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
    content_fighter, make_list, make_equipment, make_list_fighter
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
def test_m2m_triggers_update_cost_cache(
    content_fighter, make_list, make_equipment, make_list_fighter
):
    """Test that M2M field changes trigger cost cache updates."""
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
