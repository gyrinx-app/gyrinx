# Generated by Django 5.1.2 on 2024-12-01 09:40

from django.db import migrations

from gyrinx.models import EquipmentCategoryChoices


def do_migration(apps, schema_editor):
    ContentEquipment = apps.get_model("content", "ContentEquipment")
    ContentWeaponProfile = apps.get_model("content", "ContentWeaponProfile")
    ContentWeaponTrait = apps.get_model("content", "ContentWeaponTrait")

    # Autogun

    t_limited, _ = ContentWeaponTrait.objects.get_or_create(name="Limited")
    t_s_b, _ = ContentWeaponTrait.objects.get_or_create(name="Shield Breaker")
    t_s, _ = ContentWeaponTrait.objects.get_or_create(name="Shock")
    t_r_f_1, _ = ContentWeaponTrait.objects.get_or_create(name="Rapid Fire (1)")
    t_cursed, _ = ContentWeaponTrait.objects.get_or_create(name="Cursed")
    t_s_s, _ = ContentWeaponTrait.objects.get_or_create(name="Single Shot")

    autogun = ContentEquipment.objects.create(
        name="Autogun",
        category=EquipmentCategoryChoices.BASIC_WEAPONS,
        cost=15,
        rarity="C",
    )
    autogun_profile, _ = ContentWeaponProfile.objects.get_or_create(
        equipment=autogun,
        name="",
        range_short='8"',
        range_long='24"',
        accuracy_short="+1",
        accuracy_long="",
        strength="3",
        armour_piercing="",
        damage="1",
        ammo="4+",
    )
    autogun_profile.traits.set([t_r_f_1])

    autogun_static_rounds_profile, _ = ContentWeaponProfile.objects.get_or_create(
        equipment=autogun,
        name="static rounds",
        cost=10,
        cost_sign="+",
        rarity="I",
        rarity_roll=9,
        range_short='8"',
        range_long='24"',
        accuracy_short="+1",
        accuracy_long="",
        strength="3",
        armour_piercing="",
        damage="1",
        ammo="4+",
    )
    autogun_static_rounds_profile.traits.set([t_limited, t_s_b, t_s, t_r_f_1])

    autogun_warp_rounds_profile, _ = ContentWeaponProfile.objects.get_or_create(
        equipment=autogun,
        name="warp rounds",
        cost=15,
        cost_sign="+",
        rarity="I",
        rarity_roll=10,
        range_short='8"',
        range_long='24"',
        accuracy_short="+1",
        accuracy_long="",
        strength="3",
        armour_piercing="",
        damage="1",
        ammo="4+",
    )
    autogun_warp_rounds_profile.traits.set([t_cursed, t_limited, t_s_s])

    autogun.save()
    autogun_profile.save()
    autogun_static_rounds_profile.save()
    autogun_warp_rounds_profile.save()

    t_knockback, _ = ContentWeaponTrait.objects.get_or_create(name="Knockback")
    t_rapid_fire_1, _ = ContentWeaponTrait.objects.get_or_create(name="Rapid Fire (1)")
    t_scattershot, _ = ContentWeaponTrait.objects.get_or_create(name="Scattershot")
    t_template, _ = ContentWeaponTrait.objects.get_or_create(name="Template")
    t_blaze, _ = ContentWeaponTrait.objects.get_or_create(name="Blaze")
    t_limited, _ = ContentWeaponTrait.objects.get_or_create(name="Limited")
    t_gas, _ = ContentWeaponTrait.objects.get_or_create(name="Gas")
    t_blast_3, _ = ContentWeaponTrait.objects.get_or_create(name='Blast (3")')
    t_single_shot, _ = ContentWeaponTrait.objects.get_or_create(name="Single Shot")

    # Combat shotgun

    combat_shotgun, _ = ContentEquipment.objects.get_or_create(
        name="Combat shotgun",
        category=EquipmentCategoryChoices.BASIC_WEAPONS,
        cost=70,
        rarity="R",
        rarity_roll=7,
    )

    combat_shotgun_salvo_profile, _ = ContentWeaponProfile.objects.get_or_create(
        equipment=combat_shotgun,
        name="salvo ammo",
        cost=0,
        cost_sign="+",
        rarity="",
        range_short='4"',
        range_long='12"',
        accuracy_short="+1",
        accuracy_long="",
        strength="4",
        armour_piercing="",
        damage="2",
        ammo="4+",
    )
    combat_shotgun_salvo_profile.traits.set([t_knockback, t_rapid_fire_1])

    combat_shotgun_shredder_profile, _ = ContentWeaponProfile.objects.get_or_create(
        equipment=combat_shotgun,
        name="shredder ammo",
        cost=0,
        cost_sign="+",
        rarity="",
        range_short="",
        range_long="T",
        accuracy_short="",
        accuracy_long="",
        strength="2",
        armour_piercing="",
        damage="1",
        ammo="4+",
    )
    combat_shotgun_shredder_profile.traits.set([t_scattershot, t_template])

    combat_shotgun_firestorm_profile, _ = ContentWeaponProfile.objects.get_or_create(
        equipment=combat_shotgun,
        name="firestorm ammo",
        cost=30,
        cost_sign="+",
        rarity="R",
        rarity_roll=8,
        range_short='4"',
        range_long='12"',
        accuracy_short="+2",
        accuracy_long="",
        strength="4",
        armour_piercing="",
        damage="1",
        ammo="4+",
    )
    combat_shotgun_firestorm_profile.traits.set([t_blaze, t_limited, t_template])

    combat_shotgun_gas_shells_profile, _ = ContentWeaponProfile.objects.get_or_create(
        equipment=combat_shotgun,
        name="gas shells",
        cost=25,
        cost_sign="+",
        rarity="R",
        rarity_roll=11,
        range_short='4"',
        range_long='12"',
        accuracy_short="+1",
        accuracy_long="",
        strength="2",
        armour_piercing="",
        damage="1",
        ammo="4+",
    )

    combat_shotgun_gas_shells_profile.traits.set(
        [t_blast_3, t_gas, t_limited, t_single_shot]
    )

    combat_shotgun_shatter_shells_profile, _ = (
        ContentWeaponProfile.objects.get_or_create(
            equipment=combat_shotgun,
            name="shatter shells",
            cost=15,
            cost_sign="+",
            rarity="R",
            rarity_roll=9,
            range_short='4"',
            range_long='12"',
            accuracy_short="+1",
            accuracy_long="",
            strength="4",
            armour_piercing="-1",
            damage="2",
            ammo="4+",
        )
    )
    combat_shotgun_shatter_shells_profile.traits.set([t_blast_3, t_limited])

    combat_shotgun.save()
    combat_shotgun_salvo_profile.save()
    combat_shotgun_shredder_profile.save()
    combat_shotgun_firestorm_profile.save()
    combat_shotgun_gas_shells_profile.save()
    combat_shotgun_shatter_shells_profile.save()

    # Autopistol combi

    autopistol_combi_pistol_hand_flamer, _ = ContentEquipment.objects.get_or_create(
        name="Autopistol Combi-Pistol Hand flamer",
        category=EquipmentCategoryChoices.PISTOLS,
        cost=65,
        rarity="R",
        rarity_roll=10,
    )
    autopistol_combi_pistol_plasma_pistol, _ = ContentEquipment.objects.get_or_create(
        name="Autopistol Combi-Pistol Plasma pistol",
        category=EquipmentCategoryChoices.PISTOLS,
        cost=50,
        rarity="R",
        rarity_roll=10,
    )

    autopistol_combi_pistol_hand_flamer_autopistol, _ = (
        ContentWeaponProfile.objects.get_or_create(
            equipment=autopistol_combi_pistol_hand_flamer,
            name="Autopistol",
            cost=0,
            cost_sign="+",
            rarity="",
            range_short='4"',
            range_long='12"',
            accuracy_short="+1",
            accuracy_long="",
            strength="3",
            armour_piercing="",
            damage="1",
            ammo="4+",
        )
    )
    autopistol_combi_pistol_plasma_pistol_autopistol, _ = (
        ContentWeaponProfile.objects.get_or_create(
            equipment=autopistol_combi_pistol_plasma_pistol,
            name="Autopistol",
            cost=0,
            cost_sign="+",
            rarity="",
            range_short='4"',
            range_long='12"',
            accuracy_short="+1",
            accuracy_long="",
            strength="3",
            armour_piercing="",
            damage="1",
            ammo="4+",
        )
    )

    autopistol_combi_pistol_hand_flamer_profile, _ = (
        ContentWeaponProfile.objects.get_or_create(
            equipment=autopistol_combi_pistol_hand_flamer,
            name="Hand flamer",
            range_short="",
            range_long="T",
            accuracy_short="",
            accuracy_long="",
            strength="3",
            armour_piercing="",
            damage="1",
            ammo="5+",
        )
    )

    autopistol_combi_pistol_plasma_pistol_profile, _ = (
        ContentWeaponProfile.objects.get_or_create(
            equipment=autopistol_combi_pistol_plasma_pistol,
            name="Plasma pistol",
            range_short='6"',
            range_long='12"',
            accuracy_short="+2",
            accuracy_long="",
            strength="5",
            armour_piercing="-1",
            damage="2",
            ammo="5+",
        )
    )

    autopistol_combi_pistol_hand_flamer.save()
    autopistol_combi_pistol_plasma_pistol.save()
    autopistol_combi_pistol_hand_flamer_autopistol.save()
    autopistol_combi_pistol_plasma_pistol_autopistol.save()
    autopistol_combi_pistol_hand_flamer_profile.save()
    autopistol_combi_pistol_plasma_pistol_profile.save()

    # Autogun Combi

    autogun_combi_flamer, _ = ContentEquipment.objects.get_or_create(
        name="Autogun Combi-Flamer",
        category=EquipmentCategoryChoices.SPECIAL_WEAPONS,
        cost=110,
        rarity="R",
        rarity_roll=10,
    )
    autogun_combi_grenade_launcher, _ = ContentEquipment.objects.get_or_create(
        name="Autogun Combi-Grenade Launcher",
        category=EquipmentCategoryChoices.SPECIAL_WEAPONS,
        cost=30,
        rarity="R",
        rarity_roll=7,
    )

    autogun_combi_flamer_autogun, _ = ContentWeaponProfile.objects.get_or_create(
        equipment=autogun_combi_flamer,
        name="Autogun",
        range_short='8"',
        range_long='24"',
        accuracy_short="+1",
        accuracy_long="",
        strength="3",
        armour_piercing="",
        damage="1",
        ammo="4+",
    )

    autogun_combi_grenade_launcher_autogun, _ = (
        ContentWeaponProfile.objects.get_or_create(
            equipment=autogun_combi_grenade_launcher,
            name="Autogun",
            range_short='8"',
            range_long='24"',
            accuracy_short="+1",
            accuracy_long="",
            strength="3",
            armour_piercing="",
            damage="1",
            ammo="4+",
        )
    )

    autogun_combi_flamer_flamer, _ = ContentWeaponProfile.objects.get_or_create(
        equipment=autogun_combi_flamer,
        name="Flamer",
        range_short='6"',
        range_long="T",
        accuracy_short="-1",
        accuracy_long="",
        strength="4",
        armour_piercing="-1",
        damage="1",
        ammo="5+",
    )

    autogun_combi_grenade_launcher_frag, _ = ContentWeaponProfile.objects.get_or_create(
        equipment=autogun_combi_grenade_launcher,
        name="Frag Grenades",
        range_short='6"',
        range_long='24"',
        accuracy_short="-1",
        accuracy_long="",
        strength="3",
        armour_piercing="",
        damage="1",
        ammo="6+",
    )

    autogun_combi_grenade_launcher_krak, _ = ContentWeaponProfile.objects.get_or_create(
        equipment=autogun_combi_grenade_launcher,
        name="Krak Grenades",
        cost=25,
        cost_sign="+",
        rarity="R",
        rarity_roll=8,
        range_short='6"',
        range_long='24"',
        accuracy_short="-1",
        accuracy_long="",
        strength="6",
        armour_piercing="-2",
        damage="2",
        ammo="6+",
    )

    autogun_combi_grenade_launcher_stun, _ = ContentWeaponProfile.objects.get_or_create(
        equipment=autogun_combi_grenade_launcher,
        name="Stun Rounds",
        cost=20,
        cost_sign="+",
        rarity="R",
        rarity_roll=8,
        range_short='6"',
        range_long='24"',
        accuracy_short="",
        accuracy_long="",
        strength="3",
        armour_piercing="-1",
        damage="1",
        ammo="6+",
    )

    autogun_combi_flamer.save()
    autogun_combi_grenade_launcher.save()
    autogun_combi_flamer_autogun.save()
    autogun_combi_grenade_launcher_autogun.save()
    autogun_combi_flamer_flamer.save()
    autogun_combi_grenade_launcher_frag.save()
    autogun_combi_grenade_launcher_krak.save()
    autogun_combi_grenade_launcher_stun.save()

    # Kroot Long Rifle

    t_esoteric, _ = ContentWeaponTrait.objects.get_or_create(name="Esoteric")
    t_knockback, _ = ContentWeaponTrait.objects.get_or_create(name="Knockback")
    t_plentiful, _ = ContentWeaponTrait.objects.get_or_create(name="Plentiful")
    t_disarm, _ = ContentWeaponTrait.objects.get_or_create(name="Disarm")
    t_melee, _ = ContentWeaponTrait.objects.get_or_create(name="Melee")
    t_versatile, _ = ContentWeaponTrait.objects.get_or_create(name="Versatile")

    kroot_long_rifle, _ = ContentEquipment.objects.get_or_create(
        name="Kroot long rifle",
        category=EquipmentCategoryChoices.BASIC_WEAPONS,
        cost=30,
        rarity="R",
        rarity_roll=10,
    )

    kroot_long_rifle_ranged_profile, _ = ContentWeaponProfile.objects.get_or_create(
        equipment=kroot_long_rifle,
        name="ranged",
        range_short='12"',
        range_long='24"',
        accuracy_short="+1",
        accuracy_long="",
        strength="4",
        armour_piercing="",
        damage="1",
        ammo="4+",
    )
    kroot_long_rifle_ranged_profile.traits.set([t_esoteric, t_knockback, t_plentiful])

    kroot_long_rifle_melee_profile, _ = ContentWeaponProfile.objects.get_or_create(
        equipment=kroot_long_rifle,
        name="melee",
        range_short="E",
        range_long='2"',
        accuracy_short="",
        accuracy_long="",
        strength="S+1",
        armour_piercing="",
        damage="1",
        ammo="",
    )
    kroot_long_rifle_melee_profile.traits.set(
        [t_disarm, t_esoteric, t_melee, t_versatile]
    )

    kroot_long_rifle.save()
    kroot_long_rifle_ranged_profile.save()
    kroot_long_rifle_melee_profile.save()

    # Blasting charge

    t_blast_5, _ = ContentWeaponTrait.objects.get_or_create(name='Blast (5")')
    t_grenade, _ = ContentWeaponTrait.objects.get_or_create(name="Grenade")
    t_knockback, _ = ContentWeaponTrait.objects.get_or_create(name="Knockback")

    blasting_charge, _ = ContentEquipment.objects.get_or_create(
        name="Blasting charge",
        category=EquipmentCategoryChoices.GRENADES,
        cost=35,
        rarity="R",
        rarity_roll=8,
    )

    blasting_charge_profile, _ = ContentWeaponProfile.objects.get_or_create(
        equipment=blasting_charge,
        name="",
        range_short="",
        range_long="Sx2",
        accuracy_short="",
        accuracy_long="",
        strength="5",
        armour_piercing="-1",
        damage="2",
        ammo="5+",
    )

    blasting_charge_profile.traits.set([t_blast_5, t_grenade, t_knockback])

    blasting_charge.save()
    blasting_charge_profile.save()


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0022_auto_20241127_2157"),
    ]

    operations = [migrations.RunPython(do_migration)]
