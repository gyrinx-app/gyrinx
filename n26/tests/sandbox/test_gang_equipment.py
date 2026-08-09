"""Gang Equipment: the Trazior Pattern Sentry Gun spawns a vehicle.

The wargear is bought into the Stash, and its weapon options don't sit
on the wargear — they decide **which vehicle-shaped card is generated**
(design/gang-equipment.md). The grenade launcher and the heavy stubber
are option groups on the wargear purchase, and different picks result
in different vehicle cards.

Nothing here is new machinery — it composes three shipped pieces:

* an **option group** on the wargear (the Escher Cutter shape), whose
  priced option sets each hold a Hidden;
* that Hidden's ``OpAddsMiniature`` names a
  different **vehicle profile** (the pets pattern — stored effects run
  when the option's set materialises);
* each profile's own built-ins bring **its** weapon, and its statline
  is an ordinary profile statline — Toughness 4, 2 Wounds, 5+ Save
  need no special home.

Removing the wargear from the Stash takes the platform with it, the
same cascade that sells a pet with its collar. Battle rules (heat,
deployment) are names on the card, text never stored.
"""

import pytest
from django.contrib.auth.models import User

from n26.core.models import Miniature
from n26.core.render import build_model_card, render_gang
from n26.core.render_text import render_model_card
from n26.tests.sandbox.actions import (
    buy as buy_line,
)
from n26.tests.sandbox.actions import (
    create_collection,
    create_default_set,
    create_hidden,
    create_profile,
    create_profile_type,
    create_rule,
    create_statline_type,
    create_trait,
    create_wargear,
    create_weapon,
    found_gang,
    modifier,
    offer_option,
    op_adds_model,
    remove,
    set_statline,
    targets_model,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def vehicle_type(make_stat, default_pack):
    stats = [
        make_stat("T", "Toughness"),
        make_stat("W", "Wounds"),
        make_stat("Sv", "Save", is_target=True, is_inverted=True),
    ]
    return create_profile_type(
        "Vehicle", create_statline_type("Platform statline", stats)
    )


@pytest.fixture
def trazior(vehicle_type, gang_type):
    """The whole page: two vehicle profiles, one wargear with a one-of
    weapon choice whose options spawn them."""
    traits = {
        pair: create_trait(*pair)
        for pair in [
            ("Arc", "Front"),
            ("Blast", '3"'),
            ("Knockback", "5+"),
            ("Rapid Fire", "3"),
        ]
    }
    rules = [
        create_rule(name)
        for name in [
            "Deployable Platform",
            "Target Spotted",
            "Overheat!",
            "Mechanical Platform",
            "Easy Repair",
        ]
    ]
    armaments = {
        "grenade launcher": [("Arc", "Front"), ("Blast", '3"'), ("Knockback", "5+")],
        "heavy stubber": [("Arc", "Front"), ("Rapid Fire", "3")],
    }
    platforms = {}
    for key, key_traits in armaments.items():
        weapon = create_weapon(f"Trazior {key}", profiles=[("Standard", 0)])
        for pair in key_traits:
            weapon.profiles.first().traits.add(traits[pair])

        profile = create_profile(
            f"Trazior Pattern Sentry Gun ({key})",
            vehicle_type,
            gang_type,
            price=0,
        )
        set_statline(profile, toughness=4, wounds=2, save="5+")
        profile.built_ins = create_default_set(
            f"{profile.name} built-ins", members=[weapon, *rules]
        )
        profile.save()
        platforms[key] = profile

    sentry_gun = create_wargear(
        "Trazior Pattern Sentry Gun", price=30, trade_point_price=2
    )
    options = {}
    for position, (key, option_price) in enumerate(
        [("grenade launcher", 45), ("heavy stubber", 80)]
    ):
        deployer = create_hidden(f"Deploys the Trazior ({key})")
        modifier(
            f"Trazior: deploys the {key} platform",
            targets_model(),
            op_adds_model(platforms[key]),
            carried_by=deployer,
        )
        options[key] = create_default_set(
            f"Trazior {key} option", members=[deployer], price=option_price
        )
        offer_option(sentry_gun, key, default_set=options[key], position=position)
    return sentry_gun, platforms, options


@pytest.fixture
def gang_equipment_list(trazior):
    sentry_gun, _, _ = trazior
    return create_collection("Gang Equipment", entries=[(sentry_gun, {})])


@pytest.fixture
def gang(gang_type):
    return found_gang("The Watch", gang_type, owner=User.objects.create_user("tom"))


def sentry_line(gang_equipment_list):
    from n26.core.browse import browse

    return next(browse(gang_equipment_list).all_lines())


def buy_sentry(gang, gang_equipment_list, trazior, key):
    _, _, options = trazior
    return buy_line(gang.stash, sentry_line(gang_equipment_list), option=[options[key]])


def the_platform(gang):
    return Miniature.objects.get(
        membership__gang=gang, name__startswith="Trazior Pattern Sentry Gun ("
    )


class TestBuyingIntoTheStash:
    def test_the_stash_holds_the_wargear_and_a_vehicle_joins_the_gang(
        self, gang, gang_equipment_list, trazior
    ):
        bought = buy_line(
            gang.stash,
            sentry_line(gang_equipment_list),
            option=[trazior[2]["heavy stubber"]],
        )

        assert bought.stash == gang.stash
        assert bought.ledger_entry.paid == 30 + 80
        platform = the_platform(gang)
        assert platform.name == "Trazior Pattern Sentry Gun (heavy stubber)"
        # The platform is worth nothing on its own line — the wargear
        # purchase carried the whole price (the pets pattern).
        assert platform.membership.rating == 0

    def test_the_option_decides_which_card_is_generated(
        self, gang, gang_equipment_list, trazior
    ):
        buy_line(
            gang.stash,
            sentry_line(gang_equipment_list),
            option=[trazior[2]["grenade launcher"]],
        )

        card = build_model_card(the_platform(gang))
        assert card.profile_type == "Vehicle"
        assert [w.name for w in card.weapons] == ["Trazior grenade launcher"]
        assert card.statline.get("T").value == "4"
        assert card.statline.get("W").value == "2"
        assert card.statline.get("Sv").value == "5+"
        assert [r.name for r in card.rules] == [
            "Deployable Platform",
            "Easy Repair",
            "Mechanical Platform",
            "Overheat!",
            "Target Spotted",
        ]

    def test_the_weapon_keeps_its_traits(self, gang, gang_equipment_list, trazior):
        buy_line(
            gang.stash,
            sentry_line(gang_equipment_list),
            option=[trazior[2]["heavy stubber"]],
        )

        card = build_model_card(the_platform(gang))
        (weapon,) = card.weapons
        assert [t.name for t in weapon.profiles[0].traits] == [
            "Arc (Front)",
            "Rapid Fire (3)",
        ]

    def test_removing_the_wargear_takes_the_platform(
        self, gang, gang_equipment_list, trazior
    ):
        bought = buy_line(
            gang.stash,
            sentry_line(gang_equipment_list),
            option=[trazior[2]["heavy stubber"]],
        )
        platform = the_platform(gang)

        remove(bought)
        platform.membership.refresh_from_db()
        assert platform.membership.archived

    def test_the_sheet_shows_both_sides(self, gang, gang_equipment_list, trazior):
        buy_line(
            gang.stash,
            sentry_line(gang_equipment_list),
            option=[trazior[2]["grenade launcher"]],
        )

        sheet = render_gang(gang)
        assert [(line.name, line.rating) for line in sheet.stash] == [
            ("Trazior Pattern Sentry Gun", 75)
        ]
        (platform_card,) = sheet.models
        print("\n" + "\n".join(render_model_card(platform_card)))
        assert platform_card.name == "Trazior Pattern Sentry Gun (grenade launcher)"
