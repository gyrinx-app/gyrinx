import pytest
from django.core.exceptions import ValidationError

from gyrinx.content.models import (
    ContentEquipment,
    ContentFighter,
    ContentFighterEquipmentListItem,
    ContentHouse,
    ContentWeaponProfile,
    ContentWeaponTrait,
)
from gyrinx.core.models import (
    List,
    ListFighter,
    ListFighterEquipmentAssignment,
    VirtualListFighterEquipmentAssignment,
)
from gyrinx.models import EquipmentCategoryChoices, FighterCategoryChoices


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
def test_list_fighter_with_spoon():
    category, house, content_fighter = make_content()
    spoon, _ = ContentEquipment.objects.get_or_create(
        name="Wooden Spoon",
        category=EquipmentCategoryChoices.BASIC_WEAPONS,
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
        category=EquipmentCategoryChoices.BASIC_WEAPONS,
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
        category=EquipmentCategoryChoices.BASIC_WEAPONS,
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
            cost_sign="+",
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
        category=EquipmentCategoryChoices.BASIC_WEAPONS,
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
            cost_sign="+",
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
def test_profile_validation_negative_cost():
    spoon, _ = ContentEquipment.objects.get_or_create(
        name="Wooden Spoon",
        category=EquipmentCategoryChoices.BASIC_WEAPONS,
        cost=10,
    )

    with pytest.raises(ValidationError, match="Cost cannot be negative."):
        profile, _ = ContentWeaponProfile.objects.get_or_create(
            equipment=spoon,
            name="Negative Cost",
            defaults=dict(
                cost=-5,
                cost_sign="",
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
def test_profile_validation_zero_cost_with_sign():
    spoon, _ = ContentEquipment.objects.get_or_create(
        name="Wooden Spoon",
        category=EquipmentCategoryChoices.BASIC_WEAPONS,
        cost=10,
    )

    with pytest.raises(
        ValidationError, match="Cost sign should be empty for zero cost profiles."
    ):
        profile, _ = ContentWeaponProfile.objects.get_or_create(
            equipment=spoon,
            name="Zero Cost with Sign",
            defaults=dict(
                cost=0,
                cost_sign="+",
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
def test_profile_validation_standard_profile_non_zero_cost():
    spoon, _ = ContentEquipment.objects.get_or_create(
        name="Wooden Spoon",
        category=EquipmentCategoryChoices.BASIC_WEAPONS,
        cost=10,
    )

    with pytest.raises(
        ValidationError, match="Standard profiles should have zero cost."
    ):
        profile, _ = ContentWeaponProfile.objects.get_or_create(
            equipment=spoon,
            name="",
            defaults=dict(
                cost=5,
                cost_sign="+",
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
def test_profile_validation_non_standard_profile_no_cost_sign():
    spoon, _ = ContentEquipment.objects.get_or_create(
        name="Wooden Spoon",
        category=EquipmentCategoryChoices.BASIC_WEAPONS,
        cost=10,
    )

    with pytest.raises(
        ValidationError, match="Non-standard profiles should have a cost sign."
    ):
        profile, _ = ContentWeaponProfile.objects.get_or_create(
            equipment=spoon,
            name="Non-standard No Cost Sign",
            defaults=dict(
                cost=5,
                cost_sign="",
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
def test_profile_validation_non_standard_profile_negative_cost_sign():
    spoon, _ = ContentEquipment.objects.get_or_create(
        name="Wooden Spoon",
        category=EquipmentCategoryChoices.BASIC_WEAPONS,
        cost=10,
    )

    with pytest.raises(
        ValidationError, match="Non-standard profiles should have a positive cost sign."
    ):
        profile, _ = ContentWeaponProfile.objects.get_or_create(
            equipment=spoon,
            name="Non-standard Negative Cost Sign",
            defaults=dict(
                cost=5,
                cost_sign="-",
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
        category=EquipmentCategoryChoices.BASIC_WEAPONS,
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
        category=EquipmentCategoryChoices.BASIC_WEAPONS,
        cost=10,
    )

    spoon_spike_profile, _ = ContentWeaponProfile.objects.get_or_create(
        equipment=spoon,
        name="with Spike",
        defaults=dict(
            cost=5,
            cost_sign="+",
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
def test_list_fighter_with_same_equipment_different_profiles():
    category, house, content_fighter = make_content()
    spoon, _ = ContentEquipment.objects.get_or_create(
        name="Wooden Spoon",
        category=EquipmentCategoryChoices.BASIC_WEAPONS,
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
            cost_sign="+",
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
        category=EquipmentCategoryChoices.BASIC_WEAPONS,
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
            cost_sign="+",
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
        category=EquipmentCategoryChoices.BASIC_WEAPONS,
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
            cost_sign="+",
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
            cost_sign="+",
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
def test_virtual_assignments():
    category, house, content_fighter = make_content()
    spoon, _ = ContentEquipment.objects.get_or_create(
        name="Wooden Spoon",
        category=EquipmentCategoryChoices.BASIC_WEAPONS,
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
        category=EquipmentCategoryChoices.BASIC_WEAPONS,
        cost=5,
    )
    fork, _ = ContentEquipment.objects.get_or_create(
        name="Fork",
        category=EquipmentCategoryChoices.BASIC_WEAPONS,
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
