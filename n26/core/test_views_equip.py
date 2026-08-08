"""Equipping a fighter: the till's contract, server side.

``browse`` and ``Operation.buy`` have their own tests — these are about
the wiring: the list draws from a list the fighter can actually browse,
a Buy pays the server's price and never the form's, and refusals refuse
cleanly.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

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
