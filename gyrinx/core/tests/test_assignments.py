import pytest

from gyrinx.content.models import (
    ContentEquipmentCategory,
    ContentEquipmentUpgrade,
    ContentFighter,
    ContentFighterDefaultAssignment,
    ContentFighterEquipmentListWeaponAccessory,
    ContentModFighterRule,
    ContentModFighterStat,
    ContentModStat,
    ContentModTrait,
    ContentRule,
    ContentWeaponAccessory,
    ContentWeaponTrait,
    RulelineDisplay,
    StatlineDisplay,
)
from gyrinx.core.models import ListFighter, ListFighterEquipmentAssignment


@pytest.mark.django_db
def test_fighter_with_default_spoon_weapon_assignment(
    content_fighter, make_list, make_list_fighter, make_equipment, make_weapon_profile
):
    spoon = make_equipment(
        "Wooden Spoon",
        category=ContentEquipmentCategory.objects.get(name="Basic Weapons"),
        cost=10,
    )

    spoon_profile = make_weapon_profile(spoon)

    content_fighter_equip = content_fighter.default_assignments.create(equipment=spoon)
    content_fighter_equip.weapon_profiles_field.add(spoon_profile)

    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Test Fighter")

    assert len(fighter.assignments()) == 1
    assert fighter.assignments()[0].content_equipment == spoon
    # Spoon is default and therefore free
    assert fighter.cost_int() == content_fighter.cost_int()


@pytest.mark.django_db
def test_fighter_disable_default_assignment(
    content_fighter, make_list, make_list_fighter, make_equipment, make_weapon_profile
):
    spoon = make_equipment(
        "Wooden Spoon",
        category=ContentEquipmentCategory.objects.get(name="Basic Weapons"),
        cost=10,
    )

    spoon_profile = make_weapon_profile(spoon)

    content_fighter_equip = content_fighter.default_assignments.create(equipment=spoon)
    content_fighter_equip.weapon_profiles_field.add(spoon_profile)

    lst = make_list("Test List")
    fighter: ListFighter = make_list_fighter(lst, "Test Fighter")

    assert len(fighter.assignments()) == 1
    assert fighter.cost_int() == content_fighter.cost_int()

    fighter.toggle_default_assignment(content_fighter_equip)
    # Refresh because caching
    fighter = ListFighter.objects.get(pk=fighter.pk)

    assert len(fighter.assignments()) == 0

    fighter.toggle_default_assignment(content_fighter_equip, enable=True)
    # Refresh because caching
    fighter = ListFighter.objects.get(pk=fighter.pk)

    assert len(fighter.assignments()) == 1


@pytest.mark.django_db
def test_fighter_multiple_default_assigns_of_same_equipment(
    content_fighter, make_list, make_list_fighter, make_equipment, make_weapon_profile
):
    spoon = make_equipment(
        "Wooden Spoon",
        category=ContentEquipmentCategory.objects.get(name="Basic Weapons"),
        cost=10,
    )

    spoon_profile = make_weapon_profile(spoon)

    content_fighter_equip = content_fighter.default_assignments.create(equipment=spoon)
    content_fighter_equip.weapon_profiles_field.add(spoon_profile)
    content_fighter_equip_2 = content_fighter.default_assignments.create(
        equipment=spoon
    )
    content_fighter_equip_2.weapon_profiles_field.add(spoon_profile)

    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Test Fighter")

    assert len(fighter.assignments()) == 2
    assert fighter.assignments()[0].content_equipment == spoon
    assert fighter.assignments()[1].content_equipment == spoon
    # Spoon is default and therefore free
    assert fighter.cost_int() == content_fighter.cost_int()


@pytest.mark.django_db
def test_assign_accessory(
    make_list, make_list_fighter, make_equipment, make_weapon_profile
):
    spoon = make_equipment("Spoon")
    spoon_profile = make_weapon_profile(spoon)
    spoon_scope, _ = ContentWeaponAccessory.objects.get_or_create(
        name="Spoon Scope", cost=10
    )

    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Test Fighter")
    lf_assignment = fighter.assign(
        spoon, weapon_profiles=[spoon_profile], weapon_accessories=[spoon_scope]
    )

    assert lf_assignment.content_equipment == spoon
    assert lf_assignment.weapon_profiles()[0] == spoon_profile
    assert lf_assignment.weapon_accessories()[0] == spoon_scope
    assert lf_assignment.cost_int() == 10

    # Reminder: assignments() returns List[VirtuaListFighterEquipmentAssignment]
    assert len(fighter.assignments()) == 1
    assignment = fighter.assignments()[0]
    assert assignment.content_equipment == spoon
    assert assignment.weapon_profiles()[0] == spoon_profile
    assert assignment.weapon_accessories()[0] == spoon_scope
    assert assignment.cost_int() == 10

    assert fighter.cost_int() == 110

    assignment._assignment.total_cost_override = 20
    assignment._assignment.save()

    assert assignment.cost_int() == 20
    assert fighter.cost_int() == 120


@pytest.mark.django_db
def test_assign_accessory_stat_mod(
    make_list, make_list_fighter, make_equipment, make_weapon_profile
):
    t_r_f_1, _ = ContentWeaponTrait.objects.get_or_create(name="Rapid Fire (1)")
    t_rm, _ = ContentWeaponTrait.objects.get_or_create(name="Remove Me")
    t_add, _ = ContentWeaponTrait.objects.get_or_create(name="Add Me")
    spoon = make_equipment("Spoon")
    spoon_profile = make_weapon_profile(
        spoon,
        range_short='1"',
        range_long='2"',
        accuracy_short="",
        accuracy_long="-1",
        strength="2",
        armour_piercing="",
        damage="2",
        ammo="",
    )
    spoon_profile.traits.set([t_r_f_1, t_rm])

    spoon_spike_profile = make_weapon_profile(
        spoon,
        name="Spoon Spike",
        cost=10,
        range_short='1"',
        range_long='2"',
        accuracy_short="",
        accuracy_long="-1",
        strength="2",
        armour_piercing="-1",
        damage="2",
        ammo="",
    )
    spoon_spike_profile.traits.set([t_r_f_1, t_rm])

    spoon_scope, _ = ContentWeaponAccessory.objects.get_or_create(
        name="Spoon Scope", cost=10
    )

    # You can associate a mod with a weapon accessory...

    # ...to improve stats
    mod_rng_s = ContentModStat.objects.create(
        stat="range_short",
        mode="improve",
        value="1",
    )

    mod_acc_l = ContentModStat.objects.create(
        stat="accuracy_long",
        mode="improve",
        value="1",
    )

    # ...to worsen stats
    mod_str = ContentModStat.objects.create(
        stat="strength",
        mode="worsen",
        value="1",
    )

    # ...to improve stats in the reverse direction
    mod_ap = ContentModStat.objects.create(
        stat="armour_piercing",
        mode="improve",
        value="1",
    )

    # ...to replace stats
    mod_dmg = ContentModStat.objects.create(
        stat="damage",
        mode="set",
        value="3",
    )

    # ...to remove traits
    mod_rm_trait = ContentModTrait.objects.create(
        mode="remove",
        trait=t_rm,
    )

    # ...to add traits
    mod_add_trait = ContentModTrait.objects.create(
        mode="add",
        trait=t_add,
    )

    spoon_scope.modifiers.set(
        [
            mod_rng_s,
            mod_acc_l,
            mod_str,
            mod_ap,
            mod_dmg,
            mod_rm_trait,
            mod_add_trait,
        ]
    )

    lst = make_list("Test List")
    fighter: ListFighter = make_list_fighter(lst, "Test Fighter")
    lf_assignment = fighter.assign(
        spoon,
        weapon_profiles=[spoon_profile, spoon_spike_profile],
        weapon_accessories=[spoon_scope],
    )

    assert lf_assignment.content_equipment == spoon
    assert lf_assignment.weapon_profiles()[0] == spoon_profile
    assert lf_assignment.weapon_accessories()[0] == spoon_scope

    profiles = lf_assignment.all_profiles()
    assert len(profiles) == 2
    modded_profile = profiles[0]
    assert modded_profile.range_short == '2"'
    assert modded_profile.accuracy_long == ""
    assert modded_profile.strength == "1"
    assert modded_profile.armour_piercing == "-1"
    assert modded_profile.damage == "3"
    assert t_rm not in modded_profile.traits
    assert t_add in modded_profile.traits

    # The statline should reflect the changes
    # List of JSON dict of name, classes, value
    # S	L	S	L	Str	Ap	D	Am
    assert modded_profile.statline() == [
        StatlineDisplay(**d)
        for d in [
            {
                "field_name": "range_short",
                "name": "Rng S",
                "classes": "",
                "value": '2"',
                "modded": True,
            },
            {"field_name": "range_long", "name": "Rng L", "classes": "", "value": '2"'},
            {
                "field_name": "accuracy_short",
                "name": "Acc S",
                "classes": "border-start",
                "value": "-",
            },
            {
                "field_name": "accuracy_long",
                "name": "Acc L",
                "classes": "",
                "value": "-",
                "modded": True,
            },
            {
                "field_name": "strength",
                "name": "Str",
                "classes": "border-start",
                "value": "1",
                "modded": True,
            },
            {
                "field_name": "armour_piercing",
                "name": "Ap",
                "classes": "",
                "value": "-1",
                "modded": True,
            },
            {
                "field_name": "damage",
                "name": "D",
                "classes": "",
                "value": "3",
                "modded": True,
            },
            {"field_name": "ammo", "name": "Am", "classes": "", "value": "-"},
        ]
    ]
    assert modded_profile.traitline() == [
        "Add Me",
        "Rapid Fire (1)",
    ]

    modded_spike_profile = profiles[1]
    assert modded_spike_profile.range_short == '2"'
    assert modded_spike_profile.accuracy_long == ""
    assert modded_spike_profile.strength == "1"
    assert modded_spike_profile.armour_piercing == "-2"
    assert modded_spike_profile.damage == "3"
    assert t_rm not in modded_spike_profile.traits
    assert t_add in modded_spike_profile.traits

    # The statline should reflect the changes
    # List of JSON dict of name, classes, value
    # S	L	S	L	Str	Ap	D	Am
    assert modded_spike_profile.statline() == [
        StatlineDisplay(**d)
        for d in [
            {
                "field_name": "range_short",
                "name": "Rng S",
                "classes": "",
                "value": '2"',
                "modded": True,
            },
            {"field_name": "range_long", "name": "Rng L", "classes": "", "value": '2"'},
            {
                "field_name": "accuracy_short",
                "name": "Acc S",
                "classes": "border-start",
                "value": "-",
            },
            {
                "field_name": "accuracy_long",
                "name": "Acc L",
                "classes": "",
                "value": "-",
                "modded": True,
            },
            {
                "field_name": "strength",
                "name": "Str",
                "classes": "border-start",
                "value": "1",
                "modded": True,
            },
            {
                "field_name": "armour_piercing",
                "name": "Ap",
                "classes": "",
                "value": "-2",
                "modded": True,
            },
            {
                "field_name": "damage",
                "name": "D",
                "classes": "",
                "value": "3",
                "modded": True,
            },
            {"field_name": "ammo", "name": "Am", "classes": "", "value": "-"},
        ]
    ]
    assert modded_spike_profile.traitline() == [
        "Add Me",
        "Rapid Fire (1)",
    ]


@pytest.mark.django_db
def test_default_assignment_accessory_stat_mod(
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

    spoon_profile = make_weapon_profile(spoon, strength="1")
    spoon_with_spiky_bit = make_weapon_profile(
        spoon, name="with spiky bit", strength="S+1"
    )
    spoon_scope, _ = ContentWeaponAccessory.objects.get_or_create(
        name="Spoon Scope", cost=10
    )

    mod_str = ContentModStat.objects.create(
        stat="strength",
        mode="improve",
        value="1",
    )

    spoon_scope.modifiers.set([mod_str])

    content_fighter_equip = content_fighter.default_assignments.create(equipment=spoon)
    content_fighter_equip.weapon_profiles_field.add(spoon_profile)
    content_fighter_equip.weapon_profiles_field.add(spoon_with_spiky_bit)
    content_fighter_equip.weapon_accessories_field.add(spoon_scope)

    assert content_fighter_equip.cost_int() == 0

    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Test Fighter")

    # Reminder: assignments() returns List[VirtuaListFighterEquipmentAssignment]
    assert len(fighter.assignments()) == 1
    assignment: ContentFighterDefaultAssignment = fighter.assignments()[0]
    assert assignment.content_equipment == spoon

    assert assignment.standard_profiles()[0].strength == "2"

    assert assignment.weapon_profiles()[0].strength == "2"
    assert assignment.weapon_profiles()[1].strength == "S+2"


@pytest.mark.django_db
def test_upgrade_stat_mod(
    content_fighter, make_list, make_list_fighter, make_equipment, make_weapon_profile
):
    t_r_f_1, _ = ContentWeaponTrait.objects.get_or_create(name="Rapid Fire (1)")
    t_rm, _ = ContentWeaponTrait.objects.get_or_create(name="Remove Me")
    t_add, _ = ContentWeaponTrait.objects.get_or_create(name="Add Me")
    spoon = make_equipment("Spoon")
    spoon_profile = make_weapon_profile(
        spoon,
        range_short='1"',
        range_long='2"',
        accuracy_short="",
        accuracy_long="-1",
        strength="2",
        armour_piercing="",
        damage="2",
        ammo="",
    )
    spoon_profile.traits.set([t_r_f_1, t_rm])

    spoon_spike_profile = make_weapon_profile(
        spoon,
        name="Spoon Spike",
        cost=10,
        range_short='1"',
        range_long='2"',
        accuracy_short="",
        accuracy_long="-1",
        strength="2",
        armour_piercing="-1",
        damage="2",
        ammo="",
    )
    spoon_spike_profile.traits.set([t_r_f_1, t_rm])

    # You can associate a mod with an upgrade...

    # ...to improve stats
    mod_rng_s = ContentModStat.objects.create(
        stat="range_short",
        mode="improve",
        value="1",
    )

    mod_dmg = ContentModStat.objects.create(
        stat="damage",
        mode="set",
        value="3",
    )

    # ...to remove traits
    mod_rm_trait = ContentModTrait.objects.create(
        mode="remove",
        trait=t_rm,
    )

    # ...to add traits
    mod_add_trait = ContentModTrait.objects.create(
        mode="add",
        trait=t_add,
    )

    u1 = ContentEquipmentUpgrade.objects.create(
        equipment=spoon, name="Alpha", cost=20, position=0
    )
    u2 = ContentEquipmentUpgrade.objects.create(
        equipment=spoon, name="Beta", cost=30, position=1
    )

    u1.modifiers.set([mod_rng_s])
    u2.modifiers.set([mod_dmg, mod_rm_trait, mod_add_trait])

    lst = make_list("Test List")
    fighter: ListFighter = make_list_fighter(lst, "Test Fighter")
    assign = fighter.assign(
        spoon,
        weapon_profiles=[spoon_profile, spoon_spike_profile],
    )

    profiles = assign.all_profiles()
    assert len(profiles) == 2

    assign.upgrades_field.add(u1)
    assign.save()

    assign = ListFighterEquipmentAssignment.objects.get(pk=assign.pk)

    profiles = assign.all_profiles()
    assert len(profiles) == 2
    modded_profile = profiles[0]
    assert modded_profile.range_short == '2"'

    assign.upgrades_field.remove(u1)
    assign.upgrades_field.add(u2)
    assign.save()

    assign = ListFighterEquipmentAssignment.objects.get(pk=assign.pk)

    profiles = assign.all_profiles()
    assert len(profiles) == 2
    modded_profile = profiles[0]
    assert modded_profile.damage == "3"
    assert t_rm not in modded_profile.traits
    assert t_add in modded_profile.traits


@pytest.mark.django_db
def test_upgrade_fighter_stat_mod(
    content_fighter, make_list, make_list_fighter, make_equipment, make_weapon_profile
):
    r_rm, _ = ContentRule.objects.get_or_create(name="Remove Me")
    r_add, _ = ContentRule.objects.get_or_create(name="Add Me")
    spoon = make_equipment("Spoon")
    content_fighter.rules.add(r_rm)
    content_fighter.save()

    # You can associate a mod with an upgrade...

    # ...to improve stats
    mod_mv = ContentModFighterStat.objects.create(
        stat="movement",
        mode="improve",
        value="1",
    )

    mod_ws = ContentModFighterStat.objects.create(
        stat="weapon_skill",
        mode="set",
        value="3+",
    )

    # ...to remove rules
    mod_rm_rule = ContentModFighterRule.objects.create(
        mode="remove",
        rule=r_rm,
    )

    # ...to add rules
    mod_add_rule = ContentModFighterRule.objects.create(
        mode="add",
        rule=r_add,
    )

    u1 = ContentEquipmentUpgrade.objects.create(
        equipment=spoon, name="Alpha", cost=20, position=0
    )
    u2 = ContentEquipmentUpgrade.objects.create(
        equipment=spoon, name="Beta", cost=30, position=1
    )

    u1.modifiers.set([mod_mv])
    u2.modifiers.set([mod_ws, mod_rm_rule, mod_add_rule])

    lst = make_list("Test List")
    fighter: ListFighter = make_list_fighter(lst, "Test Fighter")
    assign = fighter.assign(spoon)

    assert fighter.ruleline == [
        RulelineDisplay(
            value="Remove Me",
            modded=False,
        )
    ]

    assign.upgrades_field.add(u1)
    assign.save()

    fighter = ListFighter.objects.get(pk=fighter.pk)

    # He moves quick for a big lad
    assert fighter.statline[0].value == '6"'

    assign.upgrades_field.remove(u1)
    assign.upgrades_field.add(u2)
    assign.save()

    fighter = ListFighter.objects.get(pk=fighter.pk)

    assert fighter.statline[1].value == "3+"
    assert fighter.ruleline == [
        RulelineDisplay(
            value="Add Me",
            modded=True,
        )
    ]


@pytest.mark.django_db
def test_equipment_fighter_stat_mod(
    content_fighter, make_list, make_list_fighter, make_equipment, make_weapon_profile
):
    r_rm, _ = ContentRule.objects.get_or_create(name="Remove Me")
    r_add, _ = ContentRule.objects.get_or_create(name="Add Me")
    spoon = make_equipment("Spoon")
    content_fighter.rules.add(r_rm)
    content_fighter.save()

    # You can associate a mod with equipment...

    # ...to improve stats
    mod_mv = ContentModFighterStat.objects.create(
        stat="movement",
        mode="improve",
        value="1",
    )

    # ...to remove rules
    mod_rm_rule = ContentModFighterRule.objects.create(
        mode="remove",
        rule=r_rm,
    )

    # ...to add rules
    mod_add_rule = ContentModFighterRule.objects.create(
        mode="add",
        rule=r_add,
    )

    spoon.modifiers.set([mod_mv, mod_rm_rule, mod_add_rule])

    lst = make_list("Test List")
    fighter: ListFighter = make_list_fighter(lst, "Test Fighter")

    fighter.assign(spoon)

    # Caching!!
    fighter = ListFighter.objects.get(pk=fighter.pk)

    assert fighter.statline[0].value == '6"'
    assert fighter.ruleline == [
        RulelineDisplay(
            value="Add Me",
            modded=True,
        )
    ]

    # Check that mods are applied after the list fighter stat override

    fighter.movement_override = '12"'
    fighter.save()

    fighter = ListFighter.objects.get(pk=fighter.pk)

    assert fighter.statline[0].value == '13"'


@pytest.mark.django_db
def test_fighter_with_default_spoon_scope_assignment(
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

    content_fighter_equip = content_fighter.default_assignments.create(equipment=spoon)
    content_fighter_equip.weapon_profiles_field.add(spoon_profile)
    content_fighter_equip.weapon_accessories_field.add(spoon_scope)

    assert content_fighter_equip.cost_int() == 0

    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Test Fighter")

    # Reminder: assignments() returns List[VirtuaListFighterEquipmentAssignment]
    assert len(fighter.assignments()) == 1
    assignment = fighter.assignments()[0]
    assert assignment.content_equipment == spoon
    assert assignment.weapon_profiles()[0] == spoon_profile
    assert assignment.weapon_accessories()[0] == spoon_scope
    assert assignment.cost_int() == 0
    # Spoon and scope are default and therefore free
    assert fighter.cost_int() == content_fighter.cost_int()


@pytest.mark.django_db
def test_fighter_default_assignment_conversion_to_full(
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
    spoon_spike_profile = make_weapon_profile(
        spoon, name="with spiky bit", strength="S+1", cost=11
    )
    spoon_scope, _ = ContentWeaponAccessory.objects.get_or_create(
        name="Spoon Scope", cost=12
    )

    content_fighter_equip = content_fighter.default_assignments.create(equipment=spoon)
    content_fighter_equip.weapon_profiles_field.add(spoon_profile)
    content_fighter_equip.weapon_profiles_field.add(spoon_spike_profile)
    content_fighter_equip.weapon_accessories_field.add(spoon_scope)

    assert content_fighter_equip.cost_int() == 0

    lst = make_list("Test List")
    fighter: ListFighter = make_list_fighter(lst, "Test Fighter")

    # Reminder: assignments() returns List[VirtuaListFighterEquipmentAssignment]
    assert len(fighter.assignments()) == 1
    assignment = fighter.assignments()[0]
    assert assignment.content_equipment == spoon

    fighter.convert_default_assignment(assignment)

    # Refresh because caching
    fighter = ListFighter.objects.get(pk=fighter.pk)

    assert len(fighter.assignments()) == 1
    assignment = fighter.assignments()[0]
    assert assignment.content_equipment == spoon
    assert assignment.weapon_profiles()[0] == spoon_profile
    assert assignment.weapon_profiles()[1] == spoon_spike_profile
    assert assignment.weapon_accessories()[0] == spoon_scope
    assert assignment.cost_int() == 0
    assert assignment.is_from_default_assignment()


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
def test_negative_cost_item(
    content_fighter: ContentFighter,
    make_list,
    make_list_fighter,
    make_equipment,
    make_weapon_profile,
):
    spoon = make_equipment(
        "Wooden Spoon",
        category=ContentEquipmentCategory.objects.get(name="Basic Weapons"),
        cost="-10",
    )

    spoon_profile = make_weapon_profile(spoon)

    lst = make_list("Test List")
    fighter: ListFighter = make_list_fighter(lst, "Test Fighter")

    fighter.assign(spoon, weapon_profiles=[spoon_profile], weapon_accessories=[])
    # Refresh because cache
    fighter = ListFighter.objects.get(pk=fighter.pk)

    assert len(fighter.assignments()) == 1
    assign = fighter.assignments()[0]
    assert assign.content_equipment == spoon
    assert assign.cost_int() == -10
    assert fighter.cost_int() == content_fighter.cost_int() - 10
