"""The fullest gang the stack can currently express, rendered end to end.

A living demo more than a test: two fighters with real statlines, weapons
with their own statlines and traits, subtypes, skills, wargear, XP — the
gang sheet and the ledger printed side by side. Run it to look at it:

    uv run pytest tests/sandbox/test_full_gang_demo.py -s
"""

import pytest
from django.contrib.auth.models import User

from n26.library.models import Profile, ProfileType, StatlineType, StatlineTypeStat
from n26.core.reconcile import assert_reconciled
from n26.core.render_text import gang_to_text, ledger_to_text
from n26.tests.sandbox.actions import (
    adds,
    assign,
    buy_weapon_profile,
    changes_stat,
    create_skill,
    create_stat,
    create_subtype,
    create_trait,
    create_wargear,
    create_weapon,
    found_gang,
    give_weapon,
    hire,
    modifier,
    set_statline,
    targets_model,
    targets_weapons,
)
from n26.tests.sandbox.test_render import FIGHTER_STATS
from n26.tests.sandbox.test_weapon_statlines import WEAPON_STATS

pytestmark = pytest.mark.django_db


@pytest.fixture
def library(default_pack, gang_type):
    stats = {}

    fighter_shape = StatlineType.objects.create(name="Fighter")
    for position, (short, full, flags, first, highlighted) in enumerate(FIGHTER_STATS):
        stats[full] = create_stat(short, full, **flags)
        StatlineTypeStat.objects.create(
            statline_type=fighter_shape,
            stat=stats[full],
            position=position,
            is_first_of_group=first,
            is_highlighted=highlighted,
        )
    # Stat definitions are shared across statline types by design — the
    # weapon shape reuses the fighter's Strength rather than redefining it.
    weapon_shape = StatlineType.objects.create(name="Weapon")
    for position, (short, full, flags) in enumerate(WEAPON_STATS):
        stat = stats.get(full) or create_stat(short, full, **flags)
        StatlineTypeStat.objects.create(
            statline_type=weapon_shape, stat=stat, position=position
        )
    fighter_type = ProfileType.objects.create(
        name="Fighter", statline_type=fighter_shape
    )

    def profile(name, rating, **stats):
        row = Profile.objects.create(
            name=name, profile_type=fighter_type, gang_type=gang_type, price=rating
        )
        set_statline(row, **stats)
        return row

    leader = profile(
        "Escher Gang Queen",
        125,
        movement=5,
        weapon_skill=2,
        ballistic_skill=3,
        strength=3,
        toughness=3,
        wounds=2,
        initiative=3,
        attacks=3,
        save=5,
        leadership=5,
        cool=4,
        willpower=6,
        intelligence=6,
    )
    sister = profile(
        "Escher Gang Sister",
        55,
        movement=5,
        weapon_skill=4,
        ballistic_skill=4,
        strength=3,
        toughness=3,
        wounds=1,
        initiative=4,
        attacks=1,
        save=6,
        leadership=6,
        cool=6,
        willpower=6,
        intelligence=6,
    )

    knockback = create_trait("Knockback", "6+")
    rapid_fire = create_trait("Rapid Fire", "1")
    template = create_trait("Template")
    melee = create_trait("Melee")
    parry = create_trait("Parry")

    shotgun = create_weapon(
        "Combat shotgun",
        profiles=[
            ("Salvo ammo", 0, [knockback]),
            ("Shredder ammo", 30, [rapid_fire, template]),
        ],
    )
    shotgun.statline_type = weapon_shape
    shotgun.save()
    salvo, shredder = shotgun.profiles.order_by("position")
    set_statline(
        salvo,
        short_range=4,
        long_range=12,
        strength=4,
        armour_piercing="-",
        lethality=1,
    )
    set_statline(
        shredder,
        short_range="T",
        long_range="-",
        strength=3,
        armour_piercing="-",
        lethality=1,
    )

    stiletto = create_weapon("Stiletto knife", profiles=[("Blade", 0, [melee, parry])])
    stiletto.statline_type = weapon_shape
    stiletto.save()
    set_statline(
        stiletto.profiles.get(),
        short_range="E",
        long_range="-",
        strength="S",
        armour_piercing="-1",
        lethality=1,
    )

    # Modifiers: a mount granting a subtype that itself grants a skill; an
    # injury worsening a characteristic; a skill arming Melee weapons.
    mounted = create_subtype("Mounted")
    modifier(
        "Mounted grants Hit & Run",
        targets_model(),
        adds(create_skill("Hit & Run")),
        carried_by=mounted,
    )
    cutter = create_wargear("Cutter")
    modifier("Cutter grants Mounted", targets_model(), adds(mounted), carried_by=cutter)

    eye_injury = create_wargear("Eye Injury")
    modifier(
        "Eye Injury worsens BS",
        targets_model(),
        changes_stat(stats["Ballistic Skill"], mode="worsen", amount=1),
        carried_by=eye_injury,
    )

    backstab = create_skill("Backstab")
    modifier(
        "Backstab arms Melee weapons",
        targets_weapons(with_trait=melee),
        adds(create_trait("Backstab")),
        carried_by=backstab,
    )

    return {
        "leader": leader,
        "sister": sister,
        "shotgun": shotgun,
        "stiletto": stiletto,
        "leader_subtype": create_subtype("Leader"),
        "ganger": create_subtype("Ganger"),
        "nerves": create_skill("Nerves of Steel"),
        "mesh": create_wargear("Mesh Armour"),
        "cutter": cutter,
        "eye_injury": eye_injury,
        "backstab": backstab,
    }


def test_the_full_gang_renders(library, gang_type):
    player = User.objects.create_user("tom")
    gang = found_gang("The Bad Girls", gang_type, owner=player, budget=1000)

    adina = hire(gang, library["leader"], "Adina", paid=125)
    assign(library["leader_subtype"], miniature=adina)
    assign(library["nerves"], miniature=adina)
    shotgun = give_weapon(adina, library["shotgun"], paid=35)
    buy_weapon_profile(shotgun, library["shotgun"].profiles.get(price=30))
    assign(library["mesh"], miniature=adina, paid=15)
    assign(library["eye_injury"], miniature=adina)  # worsens BS, computed
    adina.xp, adina.xp_target = 7, 9
    adina.save(update_fields=["xp", "xp_target"])  # not rating — ops own that pin

    yolanda = hire(gang, library["sister"], "Yolanda", paid=55)
    assign(library["ganger"], miniature=yolanda)
    give_weapon(yolanda, library["stiletto"], paid=20)
    assign(library["cutter"], miniature=yolanda, paid=75)  # -> Mounted -> Hit & Run
    assign(library["backstab"], miniature=yolanda)  # -> Backstab on the knife
    yolanda.xp, yolanda.xp_target = 2, 6
    yolanda.save(update_fields=["xp", "xp_target"])

    gang.refresh_from_db()
    sheet = gang_to_text(gang)
    ledger = ledger_to_text(gang)
    print("\n" + sheet)
    print(ledger)

    assert gang.rating == 125 + 35 + 30 + 15 + 55 + 20 + 75
    assert gang.credits == 1000 - 355

    # Computed, not stored: Mounted, Hit & Run and Backstab appear on cards
    # but never as assignments.
    assert "Mounted" in sheet
    assert "Hit & Run" in sheet
    assert "Backstab†" in sheet
    assert_reconciled(gang)
