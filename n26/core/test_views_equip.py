"""Equipping a fighter: the till's contract, server side.

``browse`` and ``Operation.buy`` have their own tests — these are about
the wiring: the list draws from a list the fighter can actually browse,
a Buy pays the server's price and never the form's, and refusals refuse
cleanly.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.browse import UNCATEGORISED
from n26.core.models import Assignment, Gang
from n26.core.operations import operation
from n26.library.authoring import create_collection, create_wargear

pytestmark = pytest.mark.django_db


@pytest.fixture
def tester(db):
    return User.objects.create_user("player", is_staff=True)


@pytest.fixture
def gang(gang_type, tester):
    return Gang.objects.create(
        name="The Ashen Choir",
        owner=tester,
        gang_type=gang_type,
        starting_credits=100,
        credits=100,
    )


@pytest.fixture
def fighter(gang, make_profile, make_statline, tester):
    profile = make_profile("Ganger", price=0)
    make_statline(profile, movement=5, weapon_skill=4, toughness=3)
    with operation(gang, actor=tester) as op:
        return op.hire(profile, "Vex")


@pytest.fixture
def house_list(gang, tester):
    """An equipment list the gang holds: a knife at reference, a sword
    the list prices its own way."""
    knife = create_wargear("Knife", price=10)
    sword = create_wargear("Sword", price=20)
    collection = create_collection(
        "House List", entries=[knife, (sword, {"price_override": 35})]
    )
    with operation(gang, actor=tester) as op:
        op.assign(collection, gang=gang)
    return collection


def equip_url(fighter, collection=None):
    url = reverse("n26-equip", args=[fighter.pk])
    return f"{url}?list={collection.pk}" if collection else url


def key_of(thing):
    return f"{thing._meta.label_lower}:{thing.pk}"


def test_the_list_draws(client, tester, fighter, house_list):
    client.force_login(tester)
    body = client.get(equip_url(fighter)).content.decode()
    assert "Knife" in body
    assert "Sword" in body
    # The entry's own price, not the item's reference price.
    assert "35" in body


def test_a_buy_lands_on_the_fighter_at_the_servers_price(
    client, tester, gang, fighter, house_list
):
    from n26.library.models import Wargear

    sword = Wargear.objects.get(name="Sword")
    client.force_login(tester)
    response = client.post(equip_url(fighter, house_list), {"thing": key_of(sword)})
    assert response.status_code == 302

    bought = Assignment.objects.get(wargear=sword)
    assert bought.miniature == fighter
    gang.refresh_from_db()
    # The list's override, not the wargear's 20 — the pricing seam.
    assert gang.credits == 65


def test_a_buy_stays_on_the_shop(client, tester, fighter, house_list):
    from n26.library.models import Wargear

    knife = Wargear.objects.get(name="Knife")
    client.force_login(tester)
    response = client.post(equip_url(fighter, house_list), {"thing": key_of(knife)})
    assert response.url == equip_url(fighter, house_list)


def test_a_thing_not_on_the_list_is_refused(client, tester, gang, fighter, house_list):
    """The till only accepts lines the browse produced. An off-list
    thing — here a wargear that exists but sits on no list the fighter
    holds — buys nothing, whatever the form says."""
    stray = create_wargear("Contraband", price=5)

    client.force_login(tester)
    response = client.post(equip_url(fighter, house_list), {"thing": key_of(stray)})
    assert response.status_code == 302
    assert not Assignment.objects.filter(wargear=stray).exists()
    gang.refresh_from_db()
    assert gang.credits == 100


def test_an_overspend_refuses_and_writes_nothing(
    client, tester, gang, fighter, house_list
):
    from n26.library.models import Wargear

    dear = create_wargear("Archeotech", price=500)
    house_list.entries.create(wargear=dear)

    client.force_login(tester)
    response = client.post(equip_url(fighter, house_list), {"thing": key_of(dear)})
    assert response.status_code == 302
    assert not Assignment.objects.filter(wargear=dear).exists()
    gang.refresh_from_db()
    assert gang.credits == 100
    assert Wargear.objects.filter(name="Archeotech").exists()  # refused, not deleted


def test_the_standard_trading_post_is_offered(client, tester, fighter):
    """With no lists of their own, a fighter still gets the library's
    Trading Post when it exists — swept, not curated."""
    from n26.library.authoring import create_trading_post

    create_wargear("Lho Sticks", price=5, trade_point_price=1)
    create_trading_post()

    client.force_login(tester)
    body = client.get(equip_url(fighter)).content.decode()
    assert "Lho Sticks" in body


def test_a_homebrew_trading_post_is_not_the_standard_one(
    client, tester, fighter, homebrew
):
    """Collection names are only unique per pack. A pack that names its
    own collection "Trading Post" must not be offered as the standard
    fallback — it reaches a fighter the way any pack list does, by
    being assigned or granted."""
    from n26.library.authoring import create_trading_post

    create_wargear("Bootleg Stimms", price=5, trade_point_price=1, pack=homebrew)
    create_trading_post(pack=homebrew)

    client.force_login(tester)
    body = client.get(equip_url(fighter)).content.decode()
    assert "Bootleg Stimms" not in body


def test_the_chosen_list_is_url_state(client, tester, fighter, house_list):
    """?list= picks which collection is browsed."""
    from n26.library.authoring import create_trading_post

    create_wargear("Lho Sticks", price=5, trade_point_price=1)
    create_trading_post()

    client.force_login(tester)
    on_house = client.get(equip_url(fighter, house_list)).content.decode()
    assert "Knife" in on_house
    assert "Lho Sticks" not in on_house


def test_every_registration_name_is_a_known_category(
    client, tester, fighter, house_list
):
    """Same client-side trap as the hire page: a row in an unnamed
    category registers under its section's name, possibly ""."""
    client.force_login(tester)
    response = client.get(equip_url(fighter))
    registration_names = {
        category["name"] or section["name"]
        for section in response.context["section_rows"]
        for category in section["categories"]
    }
    assert registration_names <= set(response.context["categories"])


def test_a_homeless_line_gets_a_tab_of_its_own(client, tester, fighter, house_list):
    """Same rule as the hire page: one line the content gave no category
    must not cost every other section its tab, so the homeless shelf is
    named and takes a tab like any other. A section missing from the
    strip can never be the active one, and its rows would be served with
    no way to reach them — so every shelf drawn is checked against it."""
    from n26.library.models import Category, Section, Wargear

    section = Section.objects.create(name="Armoury", position=0)
    category = Category.objects.create(section=section, name="Blades", position=0)
    sword = Wargear.objects.get(name="Sword")
    sword.category = category
    sword.save()
    # The knife stays homeless.

    client.force_login(tester)
    response = client.get(equip_url(fighter, house_list))
    assert response.context["sections"] == ["Armoury", UNCATEGORISED]

    drawn = {section["name"] for section in response.context["section_rows"]}
    assert drawn <= set(response.context["sections"])
    registration_names = {
        category["name"] or section["name"]
        for section in response.context["section_rows"]
        for category in section["categories"]
    }
    assert registration_names <= set(response.context["categories"])


@pytest.fixture
def gun_list(gang, tester):
    """A list with a gun that has ammo: one paid round and one free
    firing mode, which comes with the gun and is never for sale."""
    from n26.library.authoring import add_weapon_profile, create_weapon

    autogun = create_weapon("Autogun", profiles=[("", 0)], price=20)
    add_weapon_profile(autogun, name="warp round", price=10)
    add_weapon_profile(autogun, name="fully automatic", price=0)
    collection = create_collection("Armoury", entries=[autogun])
    with operation(gang, actor=tester) as op:
        op.assign(collection, gang=gang)
    return collection


def parts_field(thing):
    """The input name the view's own derivation produces, spelt out
    rather than imported: a test that asks the code under test what it
    named its fields cannot catch the code renaming them."""
    from django.utils.text import slugify

    return f"{slugify(key_of(thing))}:parts"


def test_the_ammo_input_is_named_what_the_server_reads(
    client, tester, fighter, gun_list
):
    """Asserted on the rendered HTML, not on a hand-built POST. The
    scope is slugified, and reading the raw key back would ignore every
    box ticked in a real browser while a test posting the raw key still
    passed."""
    from n26.library.models import Weapon

    autogun = Weapon.objects.get(name="Autogun")
    client.force_login(tester)
    body = client.get(equip_url(fighter, gun_list)).content.decode()

    assert f'name="{parts_field(autogun)}"' in body
    assert 'value="0"' in body
    # The surcharge the live total reads off the input, so the number
    # beside the Buy button cannot drift from the one that is charged.
    assert 'data-price="10"' in body
    # The bare name: the row is drawn under the gun, which has already
    # said which gun it is.
    assert "warp round" in body
    assert "fully automatic" not in body


def test_ticking_ammo_buys_it_onto_the_gun(client, tester, gang, fighter, gun_list):
    from n26.core.reconcile import assert_reconciled
    from n26.library.models import Weapon, WeaponProfile

    autogun = Weapon.objects.get(name="Autogun")
    warp = WeaponProfile.objects.get(name="warp round")
    client.force_login(tester)
    response = client.post(
        equip_url(fighter, gun_list),
        {"thing": key_of(autogun), parts_field(autogun): "0"},
    )
    assert response.status_code == 302

    gun = Assignment.objects.get(weapon=autogun)
    ammo = Assignment.objects.get(weapon_profile=warp)
    # On the gun, not on the fighter: a profile belongs to one weapon.
    assert ammo.parent == gun
    assert ammo.miniature_root == fighter

    gang.refresh_from_db()
    assert gang.credits == 70  # 100 - 20 - 10
    assert_reconciled(gang)


def test_the_gun_alone_costs_what_it_says(client, tester, gang, fighter, gun_list):
    """No box ticked, no surcharge — and the free mode still rides along
    with the gun, unbought."""
    from n26.core.reconcile import assert_reconciled
    from n26.library.models import Weapon, WeaponProfile

    autogun = Weapon.objects.get(name="Autogun")
    client.force_login(tester)
    client.post(equip_url(fighter, gun_list), {"thing": key_of(autogun)})

    gang.refresh_from_db()
    assert gang.credits == 80
    free = WeaponProfile.objects.get(name="fully automatic")
    assert Assignment.objects.filter(weapon_profile=free).count() == 1
    assert_reconciled(gang)


@pytest.mark.parametrize("tampered", ["1", "-1", "nonsense", ""])
def test_an_index_the_row_does_not_offer_is_refused(
    client, tester, gang, fighter, gun_list, tampered
):
    """The row offers one part, at index 0. Anything else is a broken
    link rather than a rule to explain, and it buys nothing at all —
    not even the gun."""
    from n26.library.models import Weapon

    autogun = Weapon.objects.get(name="Autogun")
    client.force_login(tester)
    response = client.post(
        equip_url(fighter, gun_list),
        {"thing": key_of(autogun), parts_field(autogun): tampered},
    )
    assert response.status_code == 404
    assert not Assignment.objects.filter(weapon=autogun).exists()
    gang.refresh_from_db()
    assert gang.credits == 100


def test_the_same_ammo_twice_is_refused(client, tester, gang, fighter, gun_list):
    """A checkbox cannot be ticked twice, so a repeated index is a
    tampered form — and one press was never an order for two rounds."""
    from n26.library.models import Weapon

    autogun = Weapon.objects.get(name="Autogun")
    client.force_login(tester)
    response = client.post(
        equip_url(fighter, gun_list),
        {"thing": key_of(autogun), parts_field(autogun): ["0", "0"]},
    )
    assert response.status_code == 404
    assert not Assignment.objects.filter(weapon=autogun).exists()
    gang.refresh_from_db()
    assert gang.credits == 100


def test_ammo_ticked_on_one_row_does_not_ride_another_press(
    client, tester, gang, fighter, gun_list
):
    """One form holds the whole listing, so the fields are scoped by
    line. Buying something else while the gun's box is ticked buys only
    the something else."""
    from n26.library.models import Weapon, WeaponProfile

    autogun = Weapon.objects.get(name="Autogun")
    knife = create_wargear("Knife", price=10)
    gun_list.entries.create(wargear=knife)

    client.force_login(tester)
    client.post(
        equip_url(fighter, gun_list),
        {"thing": key_of(knife), parts_field(autogun): "0"},
    )

    warp = WeaponProfile.objects.get(name="warp round")
    assert not Assignment.objects.filter(weapon_profile=warp).exists()
    gang.refresh_from_db()
    assert gang.credits == 90


def test_someone_elses_fighter_is_not_found(client, fighter):
    stranger = User.objects.create_user("stranger", is_staff=True)
    client.force_login(stranger)
    assert client.get(equip_url(fighter)).status_code == 404


def test_a_pk_that_is_not_a_ulid_is_not_found(client, tester):
    client.force_login(tester)
    assert client.get("/n26/fighters/nonsense/equip/").status_code == 404


def test_the_sheet_links_each_card_to_equip(client, tester, gang, fighter):
    client.force_login(tester)
    body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
    assert reverse("n26-equip", args=[fighter.pk]) in body
