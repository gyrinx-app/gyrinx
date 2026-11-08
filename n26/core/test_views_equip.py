"""Equipping a fighter: the equip page's contract, server side.

``browse`` and ``Operation.buy`` have their own tests — these are about
the wiring: the list draws from a list the fighter can actually browse,
a Buy pays the server's price and never the form's, and refusals refuse
cleanly.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils.text import slugify

from n26.core.confirm import CONFIRM_FIELD
from n26.core.models import Assignment, Gang
from n26.core.operations import operation
from n26.core.taxonomy import UNCATEGORISED
from n26.library.authoring import create_category, create_collection, create_wargear
from n26.library.models import Collection


@pytest.fixture
def tester(db):
    """The signed-in person these tests look at the app as."""
    return User.objects.create_user("player")


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


def page_of(response):
    """Read the actual props delivered to the complete React owner."""
    import json

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(response.content, "html.parser")
    host = soup.select_one('[data-react-name="equip"]')
    assert host is not None
    assert not host.select("[data-react-name], [x-data], [hx-post], [hx-get]")
    page = json.loads(soup.find(id=host["data-react-props"]).string)
    assert page == response.context["equip_props"]
    return page


def test_the_page_wires_the_catalogue_controls_and_update_hosts(
    client, tester, fighter, house_list
):
    from n26.library.authoring import create_trading_post

    create_trading_post()
    client.force_login(tester)
    response = client.get(equip_url(fighter, house_list))
    assert response.status_code == 200
    page = page_of(response)
    assert page["dialog"] is None
    assert set(rows_of(response)) == {"Knife", "Sword"}
    assert rows_of(response)["Sword"]["purchase"]["price"] == 35
    assert page["displayHref"] == reverse(
        "n26-equip-fighter-display", args=[fighter.pk]
    )
    assert page["commandHref"] == reverse(
        "n26-equip-fighter-command", args=[fighter.pk]
    )
    assert page["model"]["name"] == fighter.name
    assert [tab["current"] for tab in page["model"]["tabs"]][:2] == [False, True]
    assert page["csrfToken"] and page["requestKey"]
    assert '<meta name="n26-carry"' not in response.content.decode()


def test_a_buy_pays_the_servers_price_and_returns_to_its_list_and_section(
    client, tester, gang, fighter, house_list
):
    from n26.core.reconcile import assert_reconciled
    from n26.library.models import Wargear

    sword = Wargear.objects.get(name="Sword")
    client.force_login(tester)
    response = client.post(
        equip_url(fighter, house_list),
        {"thing": key_of(sword), "section": "Close combat weapons"},
    )
    assert response.status_code == 302
    assert f"list={house_list.pk}" in response.url
    assert "section=Close+combat+weapons" in response.url
    bought = Assignment.objects.get(wargear=sword)
    assert bought.miniature == fighter
    gang.refresh_from_db()
    assert gang.credits == 65
    assert_reconciled(gang)


def test_a_thing_not_on_the_list_is_refused(client, tester, gang, fighter, house_list):
    """A purchase only accepts lines the browse produced. An off-list
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


def test_each_list_is_a_tab_of_its_own(client, tester, fighter, house_list):
    """The lists a fighter's built-ins carry, then the Trading Post — one
    tab each, every one a link, and exactly one of them current."""
    from n26.library.authoring import create_trading_post

    create_wargear("Lho Sticks", price=5, trade_point_price=1)
    create_trading_post()

    client.force_login(tester)
    tabs = page_of(client.get(equip_url(fighter, house_list)))["scopeTabs"]
    assert [tab["label"] for tab in tabs] == [
        "House List",
        "Trading Post",
        "Unrestricted",
    ]
    assert [tab["href"] for tab in tabs] == [
        f"?list={house_list.pk}",
        f"?list={Collection.objects.get(name='Trading Post').pk}",
        "?list=all",
    ]
    assert [tab["current"] for tab in tabs] == [True, False, False]


def test_the_strip_holds_this_fighters_list_and_no_other_houses(
    client, tester, gang, make_profile, make_statline
):
    """A pack holds every house's equipment list at once. Which of them a
    fighter can buy from is a fact about the fighter — the collection
    their built-ins carry — and never a fact about the pack: a Squats
    fighter offered the Van Saar list is being shown the library rather
    than their own kit.

    "Skills & Powers" is here for a second reason: it holds skills, so
    there is nothing in it to buy, and no route by which a fighter might
    come to hold it puts it in this strip.
    """
    from n26.library.authoring import add_built_in, create_skill, create_trading_post

    for house in ["Van Saar", "Orlock", "Escher", "Goliath", "Delaque"]:
        create_collection(
            f"{house} Equipment List", entries=[create_wargear(f"{house} Kit", price=5)]
        )
    create_collection("Skills & Powers", entries=[create_skill("Catfall")])
    ours = create_collection(
        "Ironhead Squats Equipment List",
        entries=[create_wargear("Las-cutter", price=10)],
    )
    create_wargear("Lho Sticks", price=5, trade_point_price=1)
    create_trading_post()

    # The built-in has to be on the profile before the hire: hiring is
    # what turns a profile's built-ins into the fighter's own assignments, and a
    # fighter hired before the list was attached never receives it.
    profile = make_profile("Charter Master", price=0)
    make_statline(profile, movement=4, weapon_skill=3, toughness=4)
    add_built_in(profile, ours)
    with operation(gang, actor=tester) as op:
        fighter = op.hire(profile, "Grum")

    assert Collection.objects.count() == 8

    client.force_login(tester)
    tabs = page_of(client.get(equip_url(fighter)))["scopeTabs"]
    assert [tab["label"] for tab in tabs] == [
        "Ironhead Squats",
        "Trading Post",
        "Unrestricted",
    ]


def test_a_collection_of_skills_is_no_tab_however_the_fighter_holds_it(
    client, tester, gang, make_profile, make_statline
):
    """Holding a collection and buying from it are different things.

    A fighter's skill sets reach their card by exactly the route their
    equipment list does — a built-in on their profile — so nothing about
    how it is held can tell the two apart. What is in it can: there is
    nothing in a set of skills to buy, so a collection of them is offered
    to nobody as somewhere to buy from.
    """
    from n26.core.access import collections_for
    from n26.library.authoring import add_built_in, create_skill

    skills = create_collection("Skills & Powers", entries=[create_skill("Catfall")])
    kit = create_collection(
        "Ironhead Squats Equipment List",
        entries=[create_wargear("Las-cutter", price=10)],
    )
    profile = make_profile("Charter Master", price=0)
    make_statline(profile, movement=4, weapon_skill=3, toughness=4)
    add_built_in(profile, skills)
    add_built_in(profile, kit)
    with operation(gang, actor=tester) as op:
        fighter = op.hire(profile, "Grum")

    # They really do hold both — the strip drops one of them on content.
    assert {access.name for access in collections_for(fighter)} == {
        "Skills & Powers",
        "Ironhead Squats Equipment List",
    }

    client.force_login(tester)
    response = client.get(equip_url(fighter))
    assert [tab["label"] for tab in page_of(response)["scopeTabs"]] == [
        "Ironhead Squats",
        "Unrestricted",
    ]
    assert "Catfall" not in response.content.decode()


def test_a_lone_list_is_still_a_choice_beside_the_library(
    client, tester, fighter, house_list
):
    """One list would be no choice on its own, and the strip would be a
    control that does nothing. But the library tab stands beside every
    list, so a fighter with one list has two places to be — and the
    search box still names the one they are on."""
    client.force_login(tester)
    response = client.get(equip_url(fighter))
    page = page_of(response)
    assert [tab["label"] for tab in page["scopeTabs"]] == ["House List", "Unrestricted"]
    assert page["scopeLabel"] == "House List"


def test_a_tab_drops_the_words_every_tab_shares(client, tester, gang, fighter):
    """Every row of the rail is a list to buy from, so a name that ends by
    saying so spends the rail's width on the one word they all have. The
    full name stays on the link for anyone who wants it."""

    from n26.library.authoring import create_trading_post

    nomads = create_collection(
        "Ash Waste Nomads Equipment List", entries=[create_wargear("Rope", price=5)]
    )
    with operation(gang, actor=tester) as op:
        op.assign(nomads, gang=gang)
    create_trading_post()

    client.force_login(tester)
    response = client.get(equip_url(fighter, nomads))
    tab = next(tab for tab in page_of(response)["scopeTabs"] if tab["current"])
    assert tab["label"] == "Ash Waste Nomads"
    assert tab["title"] == "Ash Waste Nomads Equipment List"
    assert tab["href"] == f"?list={nomads.pk}"


def test_two_names_that_shorten_alike_keep_their_full_names():
    """Two tabs reading the same word is worse than two long ones, and a
    strip is read as a set — so the whole strip falls back together."""
    from n26.core.views.equip import collection_tabs

    class FakeCollection:
        def __init__(self, name, pk):
            self.name, self.pk = name, pk

        def __str__(self):
            return self.name

    collections = [
        FakeCollection("Orlock Equipment List", 1),
        FakeCollection("Orlock", 2),
    ]
    assert [tab["label"] for tab in collection_tabs(collections, collections[0])] == [
        "Orlock Equipment List",
        "Orlock",
    ]


def test_the_strip_names_each_section_once(client, tester, gang, fighter):
    """The strip keys its tabs by name, so a repeat draws neither — and
    the page would serve rows no tab could reach. The catalogue gives each
    section one group, and this is the strip agreeing with it."""
    from n26.library.models import Wargear

    ranged = create_category("Ranged", "Pistols", position=0)
    melee = create_category("Close combat", "Blades", position=1)
    basic = create_category("Ranged", "Basic", position=2)
    things = []
    for category, name in ((ranged, "Stub gun"), (melee, "Knife"), (basic, "Autogun")):
        thing = Wargear.objects.create(name=name, price=10, category=category)
        things.append(thing)
    collection = create_collection("Interleaved", entries=things)
    with operation(gang, actor=tester) as op:
        op.assign(collection, gang=gang)

    client.force_login(tester)
    response = client.get(equip_url(fighter, collection))

    sections = page_of(response)["sections"]
    assert [section["name"] for section in sections] == ["Close combat", "Ranged"]
    assert {
        entry["name"]
        for section in sections
        for category in section["categories"]
        for entry in category["entries"]
    } == {"Stub gun", "Knife", "Autogun"}


def test_a_house_list_draws_no_trade_point_slider(
    client, tester, gang, fighter, house_list
):
    """A slider over a figure no row on the page draws is a control with
    nothing to steer — and it would invite narrowing a list by a number
    that list does not charge."""
    from n26.library.models import Wargear

    knife = Wargear.objects.get(name="Knife")
    knife.trade_point_price = 3
    knife.save(update_fields=["trade_point_price"])

    client.force_login(tester)
    response = client.get(equip_url(fighter, house_list))

    assert page_of(response)["hasTradePoints"] is False
    assert all(entry["tradePoints"] is None for entry in rows_of(response).values())


def test_the_trading_post_draws_one(client, tester, gang, fighter):
    """It is the surface the figure means something on."""
    from n26.library.authoring import create_trading_post

    create_wargear("Lho Sticks", price=5, trade_point_price=3)
    post = create_trading_post()

    client.force_login(tester)
    response = client.get(equip_url(fighter, post))

    assert page_of(response)["hasTradePoints"] is True
    assert page_of(response)["tradePointsCeiling"] == 3


def test_only_the_chosen_lists_rows_are_on_the_page(
    client, tester, gang, fighter, house_list
):
    """One list's rows at a time. A tab that is not current has
    contributed nothing to this render — a page carrying two lists' rows
    is one that concatenated the strip instead of choosing from it."""
    rope = create_wargear("Rope", price=5)
    with operation(gang, actor=tester) as op:
        op.assign(create_collection("Ash Waste", entries=[rope]), gang=gang)

    client.force_login(tester)
    body = client.get(equip_url(fighter, house_list)).content.decode()
    assert "Knife" in body
    # The other list is a tab, so its name is on the page; its stock is not.
    assert "Ash Waste" in body
    assert "Rope" not in body


def test_a_category_named_with_an_ampersand_still_matches_the_filter(
    client, tester, fighter, house_list
):
    """The picker keys its filter and its counts on the names the view
    listed, and a name written into an HTML attribute comes back escaped.
    Escaped, "Armour & field armour" matches nothing in that list: the
    category counts zero, hides itself, and takes its rows off the page
    with it. So the name the picker reads must be the name the view sent,
    character for character."""

    from n26.library.models import Category, Section, Wargear

    section = Section.objects.create(name="Kit & gear", position=0)
    category = Category.objects.create(
        section=section, name="Armour & shields", position=0
    )
    knife = Wargear.objects.get(name="Knife")
    knife.category = category
    knife.save()

    client.force_login(tester)
    response = client.get(equip_url(fighter, house_list))
    page = page_of(response)
    assert "Armour & shields" in page["categories"]
    assert "Armour & shields" in page["categoryOptions"]
    assert any(
        category["name"] == "Armour & shields"
        for section in page["sections"]
        for category in section["categories"]
    )


def test_every_registration_name_is_a_known_category(
    client, tester, fighter, house_list
):
    """Same client-side trap as the hire page: a row in an unnamed
    category registers under its section's name, possibly ""."""
    client.force_login(tester)
    response = client.get(equip_url(fighter))
    page = page_of(response)
    registration_names = {
        category["name"] or section["name"]
        for section in page["sections"]
        for category in section["categories"]
    }
    assert registration_names <= set(page["categories"])


def test_a_homeless_line_gets_a_tab_of_its_own(client, tester, fighter, house_list):
    """Same rule as the hire page: one line the content gave no category
    must not cost every other section its tab, so the homeless section is
    named and takes a tab like any other. A section missing from the
    strip can never be the active one, and its rows would be served with
    no way to reach them — so every section drawn is checked against it."""
    from n26.library.models import Category, Section, Wargear

    section = Section.objects.create(name="Armoury", position=0)
    category = Category.objects.create(section=section, name="Blades", position=0)
    sword = Wargear.objects.get(name="Sword")
    sword.category = category
    sword.save()
    # The knife stays homeless.

    client.force_login(tester)
    response = client.get(equip_url(fighter, house_list))
    page = page_of(response)
    assert [section["name"] for section in page["sections"]] == [
        "Armoury",
        UNCATEGORISED,
    ]
    registration_names = {
        category["name"] or section["name"]
        for section in page["sections"]
        for category in section["categories"]
    }
    assert registration_names <= set(page["categories"])


@pytest.fixture
def gun_list(gang, tester):
    """A list with a gun and the one round the list sells for it.

    The gun also has a free firing mode, which comes with it and is
    never for sale, and the list does not name that. A list carries the
    ammo it names — see ``TestAmmoRidesUnderTheGun``.
    """
    from n26.library.authoring import add_weapon_profile, create_weapon

    autogun = create_weapon("Autogun", profiles=[("", 0)], price=20)
    warp = add_weapon_profile(autogun, name="warp round", price=10)
    add_weapon_profile(autogun, name="fully automatic", price=0)
    collection = create_collection("Armoury", entries=[autogun, warp])
    with operation(gang, actor=tester) as op:
        op.assign(collection, gang=gang)
    return collection


def parts_field(thing):
    """The input name the view's own derivation produces, spelt out
    rather than imported: a test that asks the code under test what it
    named its fields cannot catch the code renaming them."""
    from django.utils.text import slugify

    return f"{slugify(key_of(thing))}:parts"


def price_field(thing, index=None):
    """The box a line's price is typed into, spelt out for the same
    reason the tick boxes' name is."""
    from django.utils.text import slugify

    scope = slugify(key_of(thing))
    return f"{scope}:price" if index is None else f"{scope}:parts:{index}:price"


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
    response = client.get(equip_url(fighter, gun_list))
    purchase = rows_of(response)["Autogun"]["purchase"]
    assert purchase["key"] == key_of(autogun)
    (part,) = purchase["parts"]
    assert part["name"] == "warp round"
    assert part["price"] == 10
    assert part["key"].startswith("library.weaponprofile:")
    assert "fully automatic" not in str(purchase["parts"])


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
    """No optional selection adds a surcharge; included profiles remain attached."""
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


def test_an_index_the_row_does_not_offer_buys_nothing(
    client, tester, gang, fighter, gun_list
):
    from n26.library.models import Weapon

    autogun = Weapon.objects.get(name="Autogun")
    client.force_login(tester)
    response = client.post(
        equip_url(fighter, gun_list),
        {"thing": key_of(autogun), parts_field(autogun): "-1"},
    )
    assert response.status_code == 404
    assert not Assignment.objects.filter(weapon=autogun).exists()
    gang.refresh_from_db()
    assert gang.credits == 100


def test_part_selection_refuses_invalid_and_repeated_indices():
    from types import SimpleNamespace

    from django.http import Http404, QueryDict

    from n26.core.views.equip import _parts_picked

    part = object()
    line = SimpleNamespace(parts=[part])
    for values in (["1"], ["-1"], ["nonsense"], [""], ["0", "0"]):
        data = QueryDict(mutable=True)
        data.setlist("gun:parts", values)
        with pytest.raises(Http404, match="No such option"):
            _parts_picked(data, "gun", line)
    valid = QueryDict("gun:parts=0")
    assert _parts_picked(valid, "gun", line) == [(0, part)]


def test_ammo_ticked_on_one_row_does_not_ride_another_click(
    client, tester, gang, fighter, gun_list
):
    """One form holds the whole catalogue, so the fields are scoped by
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


# --- the price is the reader's to set --------------------------------------


def test_the_listing_quotes_its_price_in_a_box(client, tester, fighter, house_list):
    """The editable quoted price is the field the purchase reads."""
    from n26.library.models import Wargear

    sword = Wargear.objects.get(name="Sword")
    client.force_login(tester)
    response = client.get(equip_url(fighter, house_list))
    purchase = rows_of(response)["Sword"]["purchase"]
    assert purchase["key"] == key_of(sword)
    assert purchase["name"] == "Sword"
    assert purchase["price"] == 35


def test_a_typed_discount_charges_the_deal_and_pins_the_listing_rating(
    client, tester, gang, fighter, house_list
):
    from n26.core.models import LedgerEntry
    from n26.core.reconcile import assert_reconciled
    from n26.library.models import Wargear

    sword = Wargear.objects.get(name="Sword")
    client.force_login(tester)
    response = client.post(
        equip_url(fighter, house_list),
        {"thing": key_of(sword), price_field(sword): "8", CONFIRM_FIELD: "1"},
    )
    assert response.status_code == 302
    assert response.url == equip_url(fighter, house_list)
    entry = LedgerEntry.objects.get(assignment__wargear=sword)
    assert (entry.paid, entry.list_price, entry.discount) == (8, 35, 27)
    assert entry.rating_contribution == 35
    assert entry.assignment.miniature == fighter
    fighter.refresh_from_db()
    gang.refresh_from_db()
    assert gang.credits == 92
    assert fighter.rating == gang.rating == 35
    assert_reconciled(gang)


def test_a_price_over_the_odds_costs_more_and_is_worth_no_more(
    client, tester, gang, fighter, house_list
):
    """The box moves what leaves the bank, in both directions. Paying
    over the odds is money gone, not a better sword — so the rating is
    the listing's price either way, and the discount reads negative."""
    from n26.core.models import LedgerEntry
    from n26.core.reconcile import assert_reconciled
    from n26.library.models import Wargear

    sword = Wargear.objects.get(name="Sword")
    client.force_login(tester)
    client.post(
        equip_url(fighter, house_list),
        {"thing": key_of(sword), price_field(sword): "50"},
    )

    entry = LedgerEntry.objects.get(assignment__wargear=sword)
    assert (entry.paid, entry.list_price, entry.discount) == (50, 35, -15)
    assert entry.rating_contribution == 35
    gang.refresh_from_db()
    assert gang.credits == 50
    assert gang.rating == 35
    assert_reconciled(gang)


def test_a_price_of_nothing_is_a_gift_and_still_counts(
    client, tester, gang, fighter, house_list
):
    """Zero is a price a table may agree. Nothing leaves the bank and
    the gang still owns a 35-credit sword."""
    from n26.core.reconcile import assert_reconciled
    from n26.library.models import Wargear

    sword = Wargear.objects.get(name="Sword")
    client.force_login(tester)
    client.post(
        equip_url(fighter, house_list),
        {"thing": key_of(sword), price_field(sword): "0", CONFIRM_FIELD: "1"},
    )

    gang.refresh_from_db()
    assert gang.credits == 100
    assert gang.rating == 35
    assert_reconciled(gang)


def test_an_empty_box_leaves_the_listing_to_price_it(
    client, tester, gang, fighter, house_list
):
    """A box cleared and clicked is not an offer of nothing. With no
    number in it there is no override, so the row's own price stands."""
    from n26.core.reconcile import assert_reconciled
    from n26.library.models import Wargear

    sword = Wargear.objects.get(name="Sword")
    client.force_login(tester)
    client.post(
        equip_url(fighter, house_list),
        {"thing": key_of(sword), price_field(sword): ""},
    )

    gang.refresh_from_db()
    assert gang.credits == 65
    assert_reconciled(gang)


def test_an_invalid_price_buys_nothing(client, tester, gang, fighter, house_list):
    from n26.library.models import Wargear

    sword = Wargear.objects.get(name="Sword")
    client.force_login(tester)
    response = client.post(
        equip_url(fighter, house_list),
        {"thing": key_of(sword), price_field(sword): "-5"},
    )
    assert response.status_code == 302
    assert not Assignment.objects.filter(wargear=sword).exists()
    gang.refresh_from_db()
    assert gang.credits == 100


def test_price_validation_rejects_malformed_or_out_of_range_credit_amounts():
    from n26.core.prices import BadPrice, price_typed

    for hostile in ("-5", "+5", "abc", "12.5", "1_0", "1e3", "100001", "999999999999"):
        with pytest.raises(BadPrice, match="whole number of credits"):
            price_typed({"price": hostile}, "price", 35, "Sword")


@pytest.fixture
def weakening_list(gang, tester):
    """A list holding gear priced below nothing: taking it makes the
    model worth less, and the gang is paid the difference."""
    brittle = create_wargear("Reduced bone density", price=-10)
    collection = create_collection("Gene-smithing", entries=[brittle])
    with operation(gang, actor=tester) as op:
        op.assign(collection, gang=gang)
    return collection


def test_the_box_for_gear_priced_below_nothing_opens_at_its_own_price(
    client, tester, fighter, weakening_list
):
    """A negative quote must submit unchanged without browser minimum validation."""
    from n26.library.models import Wargear

    brittle = Wargear.objects.get(name="Reduced bone density")
    client.force_login(tester)
    response = client.get(equip_url(fighter, weakening_list))
    purchase = rows_of(response)["Reduced bone density"]["purchase"]
    assert purchase["key"] == key_of(brittle)
    assert purchase["price"] == -10


def test_gear_priced_below_nothing_is_bought_at_its_quote(
    client, tester, gang, fighter, weakening_list
):
    from n26.core.reconcile import assert_reconciled
    from n26.library.models import Wargear

    brittle = Wargear.objects.get(name="Reduced bone density")
    client.force_login(tester)
    client.post(
        equip_url(fighter, weakening_list),
        {"thing": key_of(brittle), price_field(brittle): "-10"},
    )

    gang.refresh_from_db()
    assert gang.credits == 110
    assert_reconciled(gang)


def test_the_quote_stands_when_the_box_is_left_alone(
    client, tester, gang, fighter, weakening_list
):
    from n26.library.models import Wargear

    brittle = Wargear.objects.get(name="Reduced bone density")
    client.force_login(tester)
    client.post(
        equip_url(fighter, weakening_list),
        {"thing": key_of(brittle), price_field(brittle): ""},
    )
    gang.refresh_from_db()
    assert gang.credits == 110


def test_a_buyer_may_accept_less_of_the_discount_but_never_more(
    client, tester, gang, fighter, weakening_list
):
    """Allow a higher payment than a negative quote, but reject a lower one."""
    from n26.core.models import Assignment
    from n26.core.reconcile import assert_reconciled
    from n26.library.models import Wargear

    brittle = Wargear.objects.get(name="Reduced bone density")
    client.force_login(tester)

    client.post(
        equip_url(fighter, weakening_list),
        {"thing": key_of(brittle), price_field(brittle): "-15"},
    )
    assert not Assignment.objects.filter(wargear=brittle).exists()
    gang.refresh_from_db()
    assert gang.credits == 100

    client.post(
        equip_url(fighter, weakening_list),
        {"thing": key_of(brittle), price_field(brittle): "-5"},
    )
    gang.refresh_from_db()
    assert gang.credits == 105
    assert_reconciled(gang)


def test_gear_priced_below_nothing_may_sit_alone_in_the_stash(
    client, tester, gang, gang_type, make_profile, make_statline, weakening_list
):
    """A stash holding only such a thing is worth less than nothing, and
    its pinned rating has to be able to say so rather than the move
    failing on a column that cannot hold the sum. Founded first, because
    founding is what writes the stash."""
    from n26.core.reconcile import assert_reconciled
    from n26.library.models import Wargear

    profile = make_profile("Bruiser", price=100)
    make_statline(profile, movement=5, weapon_skill=4, toughness=3)
    with operation(gang, actor=tester) as op:
        op.found(gang_type)
        fighter = op.hire(profile, "Krath", paid=100)

    brittle = Wargear.objects.get(name="Reduced bone density")
    client.force_login(tester)
    client.post(
        equip_url(fighter, weakening_list),
        {"thing": key_of(brittle), price_field(brittle): "-10"},
    )
    held = Assignment.objects.get(wargear=brittle)
    with operation(gang, actor=tester) as op:
        op.move(held, gang.stash)

    gang.stash.refresh_from_db()
    assert gang.stash.rating == -10
    assert_reconciled(gang)


def test_an_overridden_price_the_gang_cannot_afford_is_still_refused(
    client, tester, gang, fighter, house_list
):
    """The budget is the one hard no, and it is checked against what is
    actually being spent — not against what the listing asked."""
    from n26.core.models import Assignment
    from n26.library.models import Wargear

    sword = Wargear.objects.get(name="Sword")
    client.force_login(tester)
    response = client.post(
        equip_url(fighter, house_list),
        {"thing": key_of(sword), price_field(sword): "500"},
    )

    assert response.status_code == 302
    assert not Assignment.objects.filter(wargear=sword).exists()
    gang.refresh_from_db()
    assert gang.credits == 100


def test_the_prices_of_other_rows_ride_along_and_are_ignored(
    client, tester, gang, fighter, house_list
):
    """With no script running, a click submits every box on the page.
    Only the boxes scoped to the clicked line may charge anything —
    otherwise the knife's price would decide what the sword costs."""
    from n26.core.reconcile import assert_reconciled
    from n26.library.models import Wargear

    knife = Wargear.objects.get(name="Knife")
    sword = Wargear.objects.get(name="Sword")
    client.force_login(tester)
    client.post(
        equip_url(fighter, house_list),
        {
            "thing": key_of(knife),
            price_field(knife): "4",
            price_field(sword): "1",
            CONFIRM_FIELD: "1",
        },
    )

    gang.refresh_from_db()
    assert gang.credits == 96
    assert_reconciled(gang)


def test_a_round_is_charged_at_the_price_typed_on_its_own_row(
    client, tester, gang, fighter, gun_list
):
    """One click, two charges: a discount on the gun is not a discount
    on the ammo, so each carries its own box and its own entry."""
    from n26.core.models import LedgerEntry
    from n26.core.reconcile import assert_reconciled
    from n26.library.models import Weapon, WeaponProfile

    autogun = Weapon.objects.get(name="Autogun")
    warp = WeaponProfile.objects.get(name="warp round")
    client.force_login(tester)
    client.post(
        equip_url(fighter, gun_list),
        {
            "thing": key_of(autogun),
            parts_field(autogun): "0",
            price_field(autogun): "12",
            price_field(autogun, 0): "4",
            CONFIRM_FIELD: "1",
        },
    )

    gun = LedgerEntry.objects.get(assignment__weapon=autogun)
    ammo = LedgerEntry.objects.get(assignment__weapon_profile=warp)
    assert (gun.paid, gun.list_price, gun.rating_contribution) == (12, 20, 20)
    assert (ammo.paid, ammo.list_price, ammo.rating_contribution) == (4, 10, 10)

    gang.refresh_from_db()
    assert gang.credits == 84  # 100 - 12 - 4
    assert gang.rating == 30  # what the pair is worth on the list
    assert_reconciled(gang)


def test_a_bad_price_on_the_ammo_buys_neither_it_nor_the_gun(
    client, tester, gang, fighter, gun_list
):
    """Every price on the click is read before anything is written, so a
    refused round does not leave a gun bought behind it."""
    from n26.core.models import Assignment
    from n26.library.models import Weapon

    autogun = Weapon.objects.get(name="Autogun")
    client.force_login(tester)
    response = client.post(
        equip_url(fighter, gun_list),
        {
            "thing": key_of(autogun),
            parts_field(autogun): "0",
            price_field(autogun): "12",
            price_field(autogun, 0): "-4",
        },
    )

    assert response.status_code == 302
    assert not Assignment.objects.filter(weapon=autogun).exists()
    gang.refresh_from_db()
    assert gang.credits == 100


def test_a_price_typed_on_an_unticked_round_charges_nothing(
    client, tester, gang, fighter, gun_list
):
    """The box always posts, ticked or not. What decides whether a round
    is bought is its checkbox; its price only says what it would cost."""
    from n26.core.reconcile import assert_reconciled
    from n26.library.models import Weapon, WeaponProfile

    autogun = Weapon.objects.get(name="Autogun")
    warp = WeaponProfile.objects.get(name="warp round")
    client.force_login(tester)
    client.post(
        equip_url(fighter, gun_list),
        {
            "thing": key_of(autogun),
            price_field(autogun): "12",
            price_field(autogun, 0): "4",
            CONFIRM_FIELD: "1",
        },
    )

    from n26.core.models import Assignment

    assert not Assignment.objects.filter(weapon_profile=warp).exists()
    gang.refresh_from_db()
    assert gang.credits == 88
    assert_reconciled(gang)


def test_a_section_the_strip_has_no_room_for_is_still_reachable(
    client, tester, fighter, house_list
):
    """Narrow, the strip is the section you are on and a chevron holding the
    rest. The strip and that menu are drawn from one list of sections at
    every width, so a section too wide to be a tab is never a section with
    no way to it."""
    from n26.library.models import Category, Section, Wargear

    for index, (section_name, category_name, item) in enumerate(
        [("Armoury", "Blades", "Sword"), ("Kit", "Field gear", "Knife")]
    ):
        section = Section.objects.create(name=section_name, position=index)
        category = Category.objects.create(
            section=section, name=category_name, position=index
        )
        thing = Wargear.objects.get(name=item)
        thing.category = category
        thing.save()

    client.force_login(tester)
    response = client.get(equip_url(fighter, house_list))
    sections = page_of(response)["sections"]
    assert [section["name"] for section in sections] == ["Armoury", "Kit"]
    assert all(section["categories"] for section in sections)


def test_two_sections_sharing_a_category_name_count_apart(
    client, tester, gang, fighter
):
    """A category name is only unique inside its section — the rulebook
    files Primitive Weapons under both Ranged and Close Combat. Counted by
    name alone, the knife's match lands on both, and the ranged tab draws a
    Primitive Weapons header with a 1 beside it and nothing underneath. So
    each header asks for its own section's tally, while the filter keeps
    the one entry for the name it is still filtering on."""
    ranged = create_category("Ranged weapons", "Primitive weapons", position=0)
    melee = create_category("Close combat weapons", "Primitive weapons", position=1)
    collection = create_collection(
        "Primitives",
        entries=[
            create_wargear("Blunderbuss", price=30, category=ranged),
            create_wargear("Fighting knife", price=5, category=melee),
        ],
    )
    with operation(gang, actor=tester) as op:
        op.assign(collection, gang=gang)

    client.force_login(tester)
    response = client.get(equip_url(fighter, collection))
    page = page_of(response)
    assert page["categories"].count("Primitive weapons") == 1
    assert {
        section["name"]: [
            entry["name"]
            for category in section["categories"]
            for entry in category["entries"]
        ]
        for section in page["sections"]
    } == {"Close combat weapons": ["Fighting knife"], "Ranged weapons": ["Blunderbuss"]}


def buy_one(gang, fighter, tester, thing, **kwargs):
    """One of these on the fighter, through the ledger like anything else."""
    with operation(gang, actor=tester) as op:
        return op.buy(fighter, thing=thing, **kwargs)


def rows_of(response):
    return {
        entry["name"]: entry
        for section in page_of(response)["sections"]
        for category in section["categories"]
        for entry in category["entries"]
    }


def test_an_owned_row_counts_each_copy_keeps_buy_and_addresses_its_actions(
    client, tester, gang, fighter, house_list
):
    from n26.core.reconcile import assert_reconciled
    from n26.library.models import Wargear

    knife = Wargear.objects.get(name="Knife")
    client.force_login(tester)
    row = rows_of(client.get(equip_url(fighter, house_list)))["Knife"]
    assert row["count"] == 0 and row["exclusive"] is False
    first = buy_one(gang, fighter, tester, knife, paid=10)
    response = client.get(equip_url(fighter, house_list))
    row = rows_of(response)["Knife"]
    assert row["count"] == 1
    assert row["purchase"]["key"] == key_of(knife)
    for action in ("sell", "reassign", "refund", "remove"):
        assert any(
            f"?list={house_list.pk}&{action}={first.pk}" in link["target"]
            for link in row["copies"][0]["actions"]
        )
    assert (
        client.post(
            equip_url(fighter, house_list), {"thing": key_of(knife)}
        ).status_code
        == 302
    )
    rows = rows_of(client.get(equip_url(fighter, house_list)))
    assert rows["Knife"]["count"] == 2
    assert rows["Sword"]["count"] == 0
    assert len(rows["Knife"]["copies"]) == 2
    gang.refresh_from_db()
    assert_reconciled(gang)


def test_the_owned_line_renders_a_separate_sale_link_per_copy_and_part():
    from django.template.loader import render_to_string
    from django.test import RequestFactory

    from n26.core.listing import Action, OwnedCopyRow, OwnedPartRow, OwnedRow

    def sale(pk):
        return Action("Sell", "link", f"/equip/?sell={pk}", "danger")

    ammo = OwnedPartRow("round", "round", "warp round", 10, sale("round"), ())
    copies = (
        OwnedCopyRow("first", "gun", "Autogun", 20, (ammo,), sale("first"), ()),
        OwnedCopyRow("second", "gun", "Autogun", 20, (), sale("second"), ()),
    )
    body = render_to_string(
        "n26/includes/equip_owned_line.html",
        {"row": OwnedRow("gun", "Autogun", 2, copies)},
        request=RequestFactory().get("/equip/?list=1"),
    )
    for pk in ("first", "second", "round"):
        assert f'href="/equip/?sell={pk}"' in body


def test_what_a_fighter_is_gets_no_controls(client, tester, gang, fighter, house_list):
    """The card holds the profile that *is* the fighter, the XP they have
    earned and the skills they know. None of it is kit, and none of it may
    grow a Sell button — see n26.core.owned.is_possession."""
    from n26.library.authoring import create_skill

    with operation(gang, actor=tester) as op:
        op.select(fighter, create_skill("Marksman"))

    client.force_login(tester)
    body = client.get(equip_url(fighter, house_list)).content.decode()

    assert f"sell={fighter.membership.pk}" not in body


def test_a_thing_taken_off_the_card_stops_being_counted(
    client, tester, gang, fighter, house_list
):
    from n26.library.models import Wargear

    knife = Wargear.objects.get(name="Knife")
    assignment = buy_one(gang, fighter, tester, knife, paid=10)
    with operation(gang, actor=tester) as op:
        op.remove(assignment)

    client.force_login(tester)
    rows = rows_of(client.get(equip_url(fighter, house_list)))
    assert rows["Knife"]["count"] == 0


def test_a_sale_confirmation_states_its_arithmetic(
    client, tester, gang, fighter, house_list
):
    """Show the sale rating and rounded-up half-value proceeds."""
    from n26.library.models import Wargear

    sword = buy_one(gang, fighter, tester, Wargear.objects.get(name="Sword"), paid=35)
    client.force_login(tester)
    response = client.get(f"{equip_url(fighter, house_list)}&sell={sword.pk}")
    dialog = page_of(response)["dialog"]
    assert dialog["proceeds"] == 18
    assert "Half of its 35¢ rating, rounded up — 18¢." in dialog["lead"]
    assert (
        "The equipment and any accessories sold with it are removed from the gang."
        in dialog["lead"]
    )
    assert dialog["assignment"] == str(sword.pk)
    assert dialog["kind"] == "sell"


def test_a_sale_of_something_worth_almost_nothing_names_the_floor(
    client, tester, gang, fighter, house_list
):
    from n26.library.authoring import create_wargear

    trinket = buy_one(gang, fighter, tester, create_wargear("Charm", price=4), paid=4)
    client.force_login(tester)
    response = client.get(f"{equip_url(fighter, house_list)}&sell={trinket.pk}")
    assert (
        "5¢: half of its 4¢ rating is below the 5¢ minimum sale price."
        in page_of(response)["dialog"]["lead"]
    )


def test_a_move_offers_the_stash_and_the_roster(
    client, tester, gang, fighter, house_list
):
    from n26.library.models import Wargear

    knife = buy_one(gang, fighter, tester, Wargear.objects.get(name="Knife"), paid=10)
    with operation(gang, actor=tester) as op:
        op.hire(fighter.membership.assignable, "Nell")

    client.force_login(tester)
    response = client.get(f"{equip_url(fighter, house_list)}&reassign={knife.pk}")
    dialog = page_of(response)["dialog"]
    assert [model["name"] for model in dialog["models"]] == ["Nell"]
    assert dialog["kind"] == "reassign"
    assert dialog["lead"] == "Moving this equipment does not change its rating."
    assert dialog["submit_label"] == "Move"
    assert dialog["stash_host"] is False


def test_a_move_with_nobody_else_on_the_roster_is_a_move_to_the_stash(
    client, tester, gang, fighter, house_list
):
    """One fighter and a stash is not a choice between two places, so the
    only act on the form is the one place it can go."""
    from n26.library.models import Wargear

    knife = buy_one(gang, fighter, tester, Wargear.objects.get(name="Knife"), paid=10)
    client.force_login(tester)
    response = client.get(f"{equip_url(fighter, house_list)}&reassign={knife.pk}")
    dialog = page_of(response)["dialog"]
    assert dialog["submit_label"] == "To the stash"
    assert dialog["models"] == []
    assert dialog["kind"] == "reassign"


def test_a_removal_says_it_is_permanent(client, tester, gang, fighter, house_list):
    from n26.library.models import Wargear

    knife = buy_one(gang, fighter, tester, Wargear.objects.get(name="Knife"), paid=10)
    client.force_login(tester)
    body = client.get(
        f"{equip_url(fighter, house_list)}&remove={knife.pk}"
    ).content.decode()
    copy = " ".join(body.split())

    assert (
        "The equipment and anything attached to it are permanently removed from the gang. "
        "No credits are returned. Use Refund instead to recover the amount paid."
        in copy
    )
    assert reverse("n26-remove", args=[knife.pk]) in body


def test_a_refund_names_what_was_paid_and_not_its_rating(
    client, tester, gang, fighter, house_list
):
    """Three acts take a thing away and the money is the whole difference
    between them, so the confirmation names its own number. This knife was
    haggled to nothing like it: a sale would fetch 18¢, a removal returns
    nothing, and a refund hands back the 5¢ that was paid."""
    from n26.library.models import Wargear

    knife = buy_one(
        gang,
        fighter,
        tester,
        Wargear.objects.get(name="Knife"),
        paid=5,
        list_price=35,
        discount=30,
    )
    client.force_login(tester)
    response = client.get(f"{equip_url(fighter, house_list)}&refund={knife.pk}")
    dialog = page_of(response)["dialog"]
    assert "You get 5¢ back — the amount paid, not its rating." in dialog["lead"]
    assert (
        "The equipment and anything attached to it are removed from the gang. This undoes the purchase."
        in dialog["lead"]
    )
    assert dialog["kind"] == "refund"
    assert dialog["assignment"] == str(knife.pk)


def test_a_dialog_naming_a_row_off_this_card_draws_nothing(
    client, tester, gang, fighter, house_list, make_profile
):
    """The card is the permission check. A row belonging to somebody else's
    fighter is not on it, so the URL names nothing and the page is just the
    page."""
    stranger = User.objects.create_user("stranger")
    theirs = Gang.objects.create(
        name="Theirs",
        owner=stranger,
        gang_type=gang.gang_type,
        starting_credits=100,
        credits=100,
    )
    with operation(theirs, actor=stranger) as op:
        outsider = op.hire(make_profile("Bruiser", price=0), "Grud")

    client.force_login(tester)
    response = client.get(
        f"{equip_url(fighter, house_list)}&sell={outsider.membership.pk}"
    )
    assert response.status_code == 200
    assert page_of(response)["dialog"] is None


def test_someone_elses_fighter_is_not_found(client, fighter):
    stranger = User.objects.create_user("stranger")
    client.force_login(stranger)
    assert client.get(equip_url(fighter)).status_code == 404


def test_a_pk_that_is_not_a_ulid_is_not_found(client, tester):
    client.force_login(tester)
    assert client.get("/n26/fighters/nonsense/equip/").status_code == 404


def test_the_sheet_links_each_card_to_equip(client, tester, gang, fighter):
    client.force_login(tester)
    body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
    assert reverse("n26-equip", args=[fighter.pk]) in body


def test_the_figures_and_the_roster_line_stand_above_the_catalogue(
    client, tester, gang, fighter, make_profile, make_statline
):
    """The same strip the hire screen carries, and under it every fighter
    with their pinned rating — the one being equipped named in ink, the
    others as links to this same screen for them."""
    profile = make_profile("Champ", price=40)
    make_statline(profile)
    with operation(gang, actor=tester) as op:
        other = op.hire(profile, "Karn", paid=40)

    client.force_login(tester)
    page = page_of(client.get(equip_url(fighter)))
    gang.refresh_from_db()
    assert (
        next(item for item in page["figures"]["items"] if item["short"] == "Cr")[
            "value"
        ]
        == f"{gang.credits}¢"
    )
    assert page["figures"]["roster"]["count"] == 2
    assert {model["name"] for model in page["figures"]["roster"]["models"]} == {
        fighter.name,
        other.name,
    }
    switcher = page["model"]["switcher"]
    assert switcher["current"] == equip_url(fighter)
    assert equip_url(other) in [item["href"] for item in switcher["items"]]


def test_a_gang_with_no_budget_is_offered_no_refund(
    client, tester, gang, fighter, house_list
):
    """Unlimited-budget gangs receive Remove controls when no credits are refundable."""
    from n26.library.models import Wargear

    sword = Wargear.objects.get(name="Sword")
    client.force_login(tester)
    client.post(equip_url(fighter, house_list), {"thing": key_of(sword)})

    owned = Assignment.objects.get(
        miniature=fighter, parent__isnull=True, archived=False
    )
    assert any(
        "refund=" in action["target"]
        for action in rows_of(client.get(equip_url(fighter, house_list)))["Sword"][
            "copies"
        ][0]["actions"]
    )
    gang.starting_credits = None
    gang.save(update_fields=["starting_credits"])
    row = rows_of(client.get(equip_url(fighter, house_list)))["Sword"]
    assert not any(
        "refund=" in action["target"] for action in row["copies"][0]["actions"]
    )
    asked = page_of(client.get(f"{equip_url(fighter, house_list)}&refund={owned.pk}"))[
        "dialog"
    ]
    assert asked["kind"] == "remove"
    assert asked["submit_label"] == "Delete"
    assert "Removal does not refund the purchase." in asked["lead"]


@pytest.fixture
def accessories(db):
    """Two accessories: one that fits anything, one for las weapons only."""
    from n26.library.authoring import create_weapon_accessory

    las = create_category("Ranged Weapons", "Las Weapons", 0)
    return (
        create_weapon_accessory("Telescopic sight", price=25),
        create_weapon_accessory("Focusing crystal", price=30, fits_category=las),
    )


@pytest.fixture
def owned_gun(client, tester, gang, fighter, gun_list):
    """An autogun on the fighter, bought through the catalogue."""
    from n26.library.models import Weapon

    with operation(gang, actor=tester) as op:
        return op.buy(fighter, thing=Weapon.objects.get(name="Autogun"), paid=20)


def panel_for(response, assignment):
    panel = page_of(response)["dialog"]
    assert panel is not None and panel["assignment"] == str(assignment.pk)
    return panel


class TestTheAccessoryDialog:
    """A weapon the fighter owns is somewhere to bolt something onto. The
    panel is on the page before it is asked for, and the address still
    says which one is open."""

    def test_an_owned_weapon_draws_the_way_to_one_beside_its_name(
        self, client, tester, fighter, gun_list, owned_gun
    ):
        """Beside the name rather than among the acts: everything on the
        right of the row takes the gun away, and this adds to it."""
        client.force_login(tester)
        response = client.get(equip_url(fighter, gun_list))
        copy = rows_of(response)["Autogun"]["copies"][0]
        assert copy["id"] == str(owned_gun.pk)
        assert (
            f"?list={gun_list.pk}&accessorise={owned_gun.pk}"
            in copy["accessorise"]["target"]
        )
        assert page_of(response)["dialog"] is None

    def test_the_click_opens_the_panel_the_page_is_already_holding(
        self, client, tester, fighter, gun_list, owned_gun, accessories
    ):
        """The link and the click reach one state. The click does it
        without asking for a catalogue of several hundred rows again."""
        client.force_login(tester)
        page = page_of(client.get(equip_url(fighter, gun_list)))
        assert page["dialog"] is None
        response = client.get(
            reverse("n26-equip-fighter-display", args=[fighter.pk]),
            {"list": str(gun_list.pk), "accessorise": str(owned_gun.pk)},
        )
        assert response.status_code == 200
        panel = response.json()["page"]["dialog"]
        assert panel["assignment"] == str(owned_gun.pk)
        assert panel["kind"] == "accessorise"
        assert panel["accessories"][0]["name"] == "Telescopic sight"

    def test_every_gun_carries_its_own_panel_on_a_plain_visit(
        self, client, tester, gang, fighter, gun_list, owned_gun, accessories
    ):
        """Nothing is asked for, and every gun's question is answered
        anyway — that is what makes the click instant."""
        from n26.library.models import Weapon

        with operation(gang, actor=tester) as op:
            second = op.buy(fighter, thing=Weapon.objects.get(name="Autogun"), paid=20)

        client.force_login(tester)
        response = client.get(equip_url(fighter, gun_list))
        page = page_of(response)
        assert page["dialog"] is None
        copies = rows_of(response)["Autogun"]["copies"]
        assert {copy["id"] for copy in copies} == {str(owned_gun.pk), str(second.pk)}
        for copy in copies:
            assert f"accessorise={copy['id']}" in copy["accessorise"]["target"]
            loaded = client.get(
                reverse("n26-equip-fighter-display", args=[fighter.pk]),
                {"list": str(gun_list.pk), "accessorise": copy["id"]},
            ).json()["page"]["dialog"]
            assert loaded["assignment"] == copy["id"]
            assert loaded["accessories"][0]["name"] == "Telescopic sight"

    def test_the_address_opens_it(
        self, client, tester, fighter, gun_list, owned_gun, accessories
    ):
        """A link somebody sent, or a reload of a page opened by a click.
        The server draws that one open and the rest closed."""
        client.force_login(tester)
        response = client.get(
            f"{equip_url(fighter, gun_list)}&accessorise={owned_gun.pk}"
        )
        panel = panel_for(response, owned_gun)
        assert panel["open"] is True
        assert panel["kind"] == "accessorise"
        assert panel["submit_label"] == "Add accessory"

    def test_it_offers_what_fits_the_weapon_and_names_the_price(
        self, client, tester, fighter, gun_list, owned_gun, accessories
    ):
        """An autogun is homed nowhere near Las Weapons, so the crystal is
        not on the list — narrowing is what fitting does."""
        client.force_login(tester)
        response = client.get(
            f"{equip_url(fighter, gun_list)}&accessorise={owned_gun.pk}"
        )

        offered = panel_for(response, owned_gun)["accessories"]
        assert [row["name"] for row in offered] == ["Telescopic sight"]
        assert offered[0]["price"] == 25
        assert panel_for(response, owned_gun)["kind"] == "accessorise"

    def test_the_guns_cost_one_read_of_the_accessories_between_them(
        self, client, tester, gang, fighter, gun_list, owned_gun, accessories
    ):
        """The panels are precomputed, which is only worth having if the
        precomputing is flat: a second gun must not be a second read."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from n26.library.models import Weapon

        client.force_login(tester)
        url = equip_url(fighter, gun_list)
        # Once first: a session row is written on the first request of a
        # session and only updated on the rest.
        client.get(url)

        with CaptureQueriesContext(connection) as one_gun:
            assert client.get(url).status_code == 200
        with operation(gang, actor=tester) as op:
            op.buy(fighter, thing=Weapon.objects.get(name="Autogun"), paid=20)
        with CaptureQueriesContext(connection) as two_guns:
            assert client.get(url).status_code == 200

        def accessory_reads(captured):
            return [
                query
                for query in captured.captured_queries
                if "library_weaponaccessory" in query["sql"]
            ]

        assert len(accessory_reads(one_gun)) == 1
        assert len(accessory_reads(two_guns)) == 1

    def test_a_fighter_with_no_gun_asks_nothing_of_the_accessories(
        self, client, tester, fighter, house_list, accessories
    ):
        """Nowhere to fit one is no question to answer, and no read to
        make answering it."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        client.force_login(tester)
        url = equip_url(fighter, house_list)
        client.get(url)

        with CaptureQueriesContext(connection) as captured:
            response = client.get(url)

        assert page_of(response)["dialog"] is None
        assert not [
            query
            for query in captured.captured_queries
            if "library_weaponaccessory" in query["sql"]
        ]

    def test_an_unfitting_accessory_is_still_one_the_till_will_take(
        self, client, tester, gang, fighter, gun_list, owned_gun, accessories
    ):
        """Inform, never police: the shorter list is help, and the route
        behind it enforces nothing."""
        _, crystal = accessories
        client.force_login(tester)

        client.post(
            reverse("n26-accessorise", args=[owned_gun.pk]),
            {"accessory": str(crystal.pk), "list": str(gun_list.pk)},
        )

        bolted = Assignment.objects.get(weapon_accessory=crystal)
        assert bolted.parent_id == owned_gun.pk

    def test_a_weapon_with_nothing_to_fit_it_is_told_so_and_offered_no_click(
        self, client, tester, fighter, gun_list, owned_gun
    ):
        """No accessories authored at all. A green button over an empty
        list would promise an act it could not do."""
        client.force_login(tester)
        response = client.get(
            f"{equip_url(fighter, gun_list)}&accessorise={owned_gun.pk}"
        )
        panel = panel_for(response, owned_gun)
        assert panel["lead"] == "Nothing in the library fits this weapon."
        assert panel["submit_label"] == ""
        assert panel["accessories"] == []

    def test_a_row_that_is_not_a_weapon_draws_no_dialog(
        self, client, tester, gang, fighter, house_list
    ):
        from n26.library.models import Wargear

        client.force_login(tester)
        client.post(
            equip_url(fighter, house_list),
            {"thing": key_of(Wargear.objects.get(name="Knife"))},
        )
        knife = Assignment.objects.get(wargear__name="Knife")

        response = client.get(
            f"{equip_url(fighter, house_list)}&accessorise={knife.pk}"
        )
        assert page_of(response)["dialog"] is None
        assert page_of(response)["dialog"] is None
        assert "<dialog open" not in response.content.decode()

    def test_a_knife_is_offered_no_way_to_fit_one(
        self, client, tester, fighter, house_list
    ):
        """Nothing else on a card is somewhere to bolt an accessory, so
        nothing else draws the control."""
        from n26.library.models import Wargear

        client.force_login(tester)
        client.post(
            equip_url(fighter, house_list),
            {"thing": key_of(Wargear.objects.get(name="Knife"))},
        )

        body = client.get(equip_url(fighter, house_list)).content.decode()
        assert "Add accessory to Knife" not in body

    def test_the_dialog_carries_the_list_and_tab_through_the_click(
        self, client, tester, fighter, gun_list, owned_gun, accessories
    ):
        """Cancel comes back to the page as it was, and so does the answer."""
        client.force_login(tester)
        response = client.get(
            f"{equip_url(fighter, gun_list)}&section=Weapons&accessorise={owned_gun.pk}"
        )
        page = page_of(response)
        assert page["scope"] == str(gun_list.pk)
        assert page["section"] == "Weapons"
        assert page["dialog"]["assignment"] == str(owned_gun.pk)
        assert "section=Weapons" in page["dialog"]["cancel_url"]


class TestTheSellDialogWhenSomethingIsBoltedOn:
    """The sale of a gun with a sight on it is two sales at two prices,
    so the confirmation asks which one is meant."""

    def test_a_bare_weapon_is_asked_no_question(
        self, client, tester, fighter, gun_list, owned_gun
    ):
        client.force_login(tester)
        response = client.get(f"{equip_url(fighter, gun_list)}&sell={owned_gun.pk}")

        assert "keepable" not in page_of(response)["dialog"]
        assert "Stash the accessory" not in str(page_of(response)["dialog"])

    def test_a_kitted_weapon_is_asked_which_sale_it_is(
        self, client, tester, gang, fighter, gun_list, owned_gun, accessories
    ):
        from n26.core.models import Stash

        # Somewhere for the sight to go. With no stash there is no choice
        # to offer, and the dialog does not offer one.
        Stash.objects.get_or_create(gang=gang)
        sight, _ = accessories
        with operation(gang, actor=tester) as op:
            op.buy(owned_gun, thing=sight)

        client.force_login(tester)
        response = client.get(f"{equip_url(fighter, gun_list)}&sell={owned_gun.pk}")
        dialog = page_of(response)["dialog"]
        assert dialog["keepable"] == "Telescopic sight"
        assert dialog["proceeds"] == 10
        assert dialog["keep_label"] == "Stash the accessory"
        assert dialog["sell_all_label"] == "Sell the accessory too"
        assert "23¢" in dialog["sell_all_detail"]


class TestBuyingWithoutRebuildingThePage:
    """A Buy that asks for the row it changed instead of the whole screen.

    The catalogue's filters, the section on screen and the prices typed
    into other rows are all client state: rebuilding the page throws
    every bit of it away, so a purchase answers with the row and the
    gang's figures and leaves the rest of the screen alone.
    """

    def asked(self, client, fighter, collection, thing, **extra):
        """Buy the way a browser with script does — asking for the row."""
        return client.post(
            equip_url(fighter, collection),
            {"thing": key_of(thing), **extra},
            headers={"HX-Request": "true"},
        )

    def test_a_buy_returns_the_owned_row_updated_card_hosts_and_success_toast(
        self, client, tester, fighter, house_list
    ):
        import json

        from n26.core.reconcile import assert_reconciled
        from n26.library.models import Wargear

        knife = Wargear.objects.get(name="Knife")
        client.force_login(tester)
        response = self.asked(client, fighter, house_list, knife)
        assert response.status_code == 200
        body = response.content.decode()
        assert 'data-row="library.wargear:' in body
        assert "<html" not in body
        assert ">1</span>" in body
        assert "equipped" in body
        assert "Buy another" in body
        assert "OwnedRow(" not in body
        assert "OwnedCopyRow(" not in body
        assert f'id="n26-row-{slugify(key_of(knife))}"' in body
        assert 'id="n26-gang-wealth"' in body
        assert 'id="n26-accessorise-host"' in body
        host = body[body.index('id="n26-model-card-host"') :]
        assert 'hx-swap-oob="true"' in host[: host.index(">")]
        assert body.count('hx-swap-oob="true"') == 4
        card = host[: host.index('id="n26-gang-wealth"')]
        assert "Knife" in card
        assert "More for Knife" in card
        assert "sell=" in card
        said = json.loads(response["HX-Trigger"])["n26-toasts"]
        assert [item["variant"] for item in said] == ["success"]
        assert "Bought Knife" in said[0]["message"]
        assert Assignment.objects.filter(miniature=fighter, wargear=knife).count() == 1
        fighter.gang.refresh_from_db()
        assert_reconciled(fighter.gang)

    def test_a_refusal_swaps_nothing_and_still_says_why(
        self, client, tester, gang, fighter, house_list
    ):
        """Validation failures display their reason without replacing unchanged page content."""
        import json

        from n26.library.authoring import create_wargear

        client.force_login(tester)
        response = self.asked(
            client, fighter, house_list, create_wargear("Elsewhere", price=5)
        )
        assert response.status_code == 204
        said = json.loads(response["HX-Trigger"])["n26-toasts"]
        assert said[0]["variant"] == "error"
        # A refusal stands until it is dismissed.
        assert said[0]["duration"] == 0


class TestOpeningAConfirmationWithoutRebuildingThePage:
    """Server-rendered action panels preserve the catalogue beneath them."""

    def asked(self, client, fighter, gun_list, assignment, kind="sell"):
        return client.get(
            equip_url(fighter, gun_list) + f"&{kind}={assignment.pk}",
            headers={"HX-Request": "true"},
        )

    def test_the_partial_panel_carries_its_host_address_and_submission(
        self, client, tester, fighter, gun_list, owned_gun
    ):
        client.force_login(tester)
        response = self.asked(client, fighter, gun_list, owned_gun)
        assert response.status_code == 200
        assert response.content == b""
        assert (
            response["HX-Redirect"]
            == equip_url(fighter, gun_list) + f"&sell={owned_gun.pk}"
        )

    def test_asking_with_nothing_named_closes_whatever_was_open(
        self, client, tester, fighter, gun_list, owned_gun
    ):
        client.force_login(tester)
        response = client.get(
            equip_url(fighter, gun_list), headers={"HX-Request": "true"}
        )
        assert response.status_code == 200
        assert response["HX-Redirect"] == equip_url(fighter, gun_list)
        assert response.content == b""

    def test_without_the_header_the_whole_page_still_draws_the_panel(
        self, client, tester, fighter, gun_list, owned_gun
    ):
        """Nothing here is the only way to reach a confirmation."""
        client.force_login(tester)
        response = client.get(equip_url(fighter, gun_list) + f"&sell={owned_gun.pk}")
        body = response.content.decode()

        assert "<html" in body
        assert "Sell Autogun?" in body


def _support_js():
    """The client glue, read off disk — the page only carries a script tag."""
    from pathlib import Path

    import n26.core

    return (
        Path(n26.core.__file__).parent / "static" / "n26" / "htmx_support.js"
    ).read_text()


class TestTheWiringEveryActLeansOn:
    """The glue that nothing else on the page would miss, and whose
    absence looks like the acts themselves being broken."""

    def test_a_click_on_a_control_built_after_load_is_still_caught(self):
        """Delegated handling covers controls created after htmx's initial wiring."""
        js = _support_js()

        assert 'event.target.closest("a[hx-get]")' in js
        # A control htmx did wire handles its own click first and calls
        # preventDefault, so nothing is requested twice.
        assert "event.defaultPrevented" in js

    def test_toasts_are_read_from_inside_the_wrapper(self):
        """htmx wraps a trigger payload that is not a plain object as
        {value: ...}; read event.detail as the list itself and it is
        silently empty."""
        js = _support_js()

        assert 'addEventListener("n26-toasts"' in js
        assert "detail.value" in js

    def test_a_swapped_in_noscript_is_emptied(self):
        """Clear noscript bodies after htmx swaps a response.

        Fragment parsing can activate styles that the original page parser treated
        as text, exposing hidden controls or duplicate menu content.
        """
        js = _support_js()

        assert 'addEventListener("htmx:afterSwap"' in js
        assert 'addEventListener("htmx:oobAfterSwap"' in js
        assert 'querySelectorAll("noscript")' in js
        assert "replaceChildren()" in js


class TestSellingWithoutRebuildingThePage:
    """Confirming the act, not just opening the panel. Selling is what the
    reader came to do, and it must cost them their place no more than
    opening the question did."""

    def sold(self, client, fighter, gun_list, assignment, **extra):
        return client.post(
            reverse("n26-sell", args=[assignment.pk]),
            {"return": equip_url(fighter, gun_list), "list": str(gun_list.pk), **extra},
            headers={"HX-Request": "true"},
        )

    def test_a_sale_restores_the_listing_closes_the_panel_and_reports_success(
        self, client, tester, fighter, gun_list, owned_gun
    ):
        import json

        from n26.core.reconcile import assert_reconciled

        client.force_login(tester)
        response = self.sold(client, fighter, gun_list, owned_gun)
        assert response.status_code == 200
        body = response.content.decode()
        assert "<html" not in body
        assert f'id="n26-row-{slugify(key_of(owned_gun.assignable))}"' in body
        assert "equipped" not in body
        assert "Buy" in body
        assert 'id="n26-dialog-host"' in body
        assert "Sell Autogun?" not in body
        assert "sell=" not in response["HX-Replace-Url"]
        said = json.loads(response["HX-Trigger"])["n26-toasts"]
        assert said[0]["variant"] == "success"
        assert "Sold Autogun" in said[0]["message"]
        owned_gun.refresh_from_db()
        assert owned_gun.archived
        fighter.gang.refresh_from_db()
        assert_reconciled(fighter.gang)

    def test_the_row_comes_back_open_where_it_was_open(
        self, client, tester, fighter, gun_list, gang, tester_kit=None
    ):
        """Carry the expanded state when redrawing a listing entry after a command."""
        from n26.library.models import Weapon

        autogun = Weapon.objects.get(name="Autogun")
        with operation(gang, actor=tester) as op:
            first = op.buy(fighter, thing=autogun, paid=20)
            op.buy(fighter, thing=autogun, paid=20)

        client.force_login(tester)
        body = self.sold(
            client, fighter, gun_list, first, owned=key_of(autogun)
        ).content.decode()

        # One copy left, and the row still standing open on it.
        assert 'aria-expanded="true"' in body

    def test_a_plain_sale_still_answers_with_the_whole_page(
        self, client, tester, fighter, gun_list, owned_gun
    ):
        client.force_login(tester)
        response = client.post(
            reverse("n26-sell", args=[owned_gun.pk]),
            {"return": equip_url(fighter, gun_list), "list": str(gun_list.pk)},
        )
        assert response.status_code == 302


class TestOpeningTheCopiesOfAnOwnedRow:
    """The copies a row opens onto are already on the page, so opening it
    asks the server for nothing at all."""

    def test_the_row_opens_where_it_stands_and_says_so_in_the_address(
        self, client, tester, fighter, gun_list, owned_gun
    ):
        client.force_login(tester)
        page = page_of(client.get(equip_url(fighter, gun_list)))
        assert page["owned"] == ""
        row = rows_of(client.get(equip_url(fighter, gun_list)))["Autogun"]
        assert row["count"] == 1
        assert row["copies"][0]["id"] == str(owned_gun.pk)
        assert row["expanded"] is False

    def test_it_is_still_a_link(self, client, tester, fighter, gun_list, owned_gun):
        """Without script the server renders the row open."""
        client.force_login(tester)
        opened = client.get(
            equip_url(fighter, gun_list) + f"&owned={key_of(owned_gun.assignable)}"
        )

        assert opened.status_code == 200
        assert page_of(opened)["owned"] == key_of(owned_gun.assignable)
        assert rows_of(opened)["Autogun"]["expanded"] is True


class TestTheLibraryTab:
    """Every item in the library, for the thing no held list offers —
    the same tab the gang's screen has, noted for this fighter."""

    @pytest.fixture
    def library(self, default_pack):
        """Gear no list the fighter holds offers, one piece of it
        restricted to a subtype the fighter is not."""
        from n26.library.authoring import create_subtype, create_weapon

        walker = create_subtype("Walker")
        create_wargear("Mesh Armour", price=15)
        create_weapon(
            "Autogun", price=20, profiles=[("", 0)], usable_by_subtypes=[walker]
        )
        return walker

    def test_it_is_not_built_until_the_address_asks_for_it(
        self, client, tester, fighter, house_list, library
    ):
        client.force_login(tester)
        body = client.get(equip_url(fighter)).content.decode()

        assert "Knife" in body
        assert "Mesh Armour" not in body

    def test_it_draws_the_library_noted_for_this_fighter(
        self, client, tester, fighter, house_list, library
    ):
        """A list restricts what it offers; the library restricts nothing,
        so a use restriction is likeliest to bite here — and it is drawn
        the way it is on any list: a note, never a missing row."""
        client.force_login(tester)
        response = client.get(f"{equip_url(fighter)}?list=all")
        rows = rows_of(response)

        assert "Knife" in rows
        assert "Mesh Armour" in rows
        assert rows["Mesh Armour"]["purchase"]["notes"] == []
        assert [note["text"] for note in rows["Autogun"]["purchase"]["notes"]] == [
            "usable by Walker only"
        ]

    def test_a_restricted_round_under_a_gun_is_noted_on_its_own_box(
        self, client, tester, fighter, house_list, library
    ):
        """The gun is open to everyone; one of its rounds is not. The
        note sits on that round's tick box, and the box stays."""
        from n26.library.authoring import add_weapon_profile, create_weapon

        launcher = create_weapon("Grenade launcher", price=55, profiles=[("", 0)])
        add_weapon_profile(
            launcher, name="krak grenades", price=30, usable_by_subtypes=[library]
        )
        client.force_login(tester)
        response = client.get(f"{equip_url(fighter)}?list=all")
        rows = rows_of(response)

        assert rows["Grenade launcher"]["purchase"]["notes"] == []
        (krak,) = rows["Grenade launcher"]["purchase"]["parts"]
        assert [note["text"] for note in krak["notes"]] == ["usable by Walker only"]
        assert "usable by Walker only" in response.content.decode()

    def test_the_page_says_where_it_is(
        self, client, tester, fighter, house_list, library
    ):
        client.force_login(tester)
        response = client.get(f"{equip_url(fighter)}?list=all")
        page = page_of(response)
        assert [tab["current"] for tab in page["scopeTabs"]] == [False, True]
        assert page["scope"] == "all"
        assert page["scopeLabel"] == "all equipment"
        assert page["action"] == f"{equip_url(fighter)}?list=all"

    def test_buying_from_it_lands_on_the_fighter(
        self, client, tester, gang, fighter, house_list, library
    ):
        from n26.core.reconcile import assert_reconciled
        from n26.library.models import Wargear

        armour = Wargear.objects.get(name="Mesh Armour")
        client.force_login(tester)
        response = client.post(
            f"{equip_url(fighter)}?list=all", {"thing": key_of(armour)}
        )

        assert response.status_code == 302
        assert response.url == f"{equip_url(fighter)}?list=all"
        assert Assignment.objects.get(wargear=armour).miniature == fighter
        gang.refresh_from_db()
        assert gang.credits == 85
        assert_reconciled(gang)

    def test_a_listed_item_is_priced_as_the_fighters_list_prices_it(
        self, client, tester, fighter, house_list, library
    ):
        """The library's own figure is a reference price. A fighter buys
        from the lists they hold, so an item one of them offers is priced
        as that list prices it, on that list's terms."""
        from n26.core.views.equip import _screen

        screen = _screen(fighter.gang, miniature=fighter, list_param="all")
        lines = {str(line.thing): line for line in screen.view.all_lines()}

        # The list's override, not the wargear's 20.
        assert lines["Sword"].credits == 35
        assert lines["Sword"].entry is not None
        assert lines["Sword"].charges_trade_points is False
        # Nothing held offers it: reference.
        assert lines["Mesh Armour"].credits == 15
        assert lines["Mesh Armour"].entry is None

    def test_an_unlisted_item_is_priced_as_the_trading_post_prices_it(
        self, client, tester, fighter, house_list, library
    ):
        """Where no held list offers it and the post does, the post's line
        stands — Trade Points shown and charged, as on the post's own
        tab — and the fighter's own list still wins over the post."""
        from n26.library.authoring import create_trading_post
        from n26.library.models import Wargear

        create_wargear("Lho Sticks", price=5, trade_point_price=1)
        sword = Wargear.objects.get(name="Sword")
        sword.trade_point_price = 4
        sword.save(update_fields=["trade_point_price"])
        create_trading_post()

        from n26.core.views.equip import _screen

        screen = _screen(fighter.gang, miniature=fighter, list_param="all")
        lines = {str(line.thing): line for line in screen.view.all_lines()}
        client.force_login(tester)
        response = client.get(f"{equip_url(fighter)}?list=all")
        rows = rows_of(response)

        assert lines["Lho Sticks"].trade_points == 1
        assert lines["Lho Sticks"].shows_trade_points is True
        assert lines["Lho Sticks"].charges_trade_points is True
        assert lines["Sword"].credits == 35
        assert lines["Sword"].charges_trade_points is False
        assert lines["Mesh Armour"].shows_trade_points is False
        # And what the page draws says the same: a figure on the post's
        # line, none on the list's, and the slider to steer by it.
        assert rows["Lho Sticks"]["tradePoints"] == 1
        assert rows["Sword"]["tradePoints"] is None
        assert page_of(response)["hasTradePoints"] is True

    def test_a_fighter_with_no_list_is_pointed_at_it(
        self, client, tester, fighter, library
    ):
        """An empty equipment list links to the library tab and retains that tab."""
        client.force_login(tester)
        empty = client.get(equip_url(fighter))
        assert page_of(empty)["sections"] == []
        assert page_of(empty)["scopeTabs"][-1]["href"] == "?list=all"

        response = client.get(f"{equip_url(fighter)}?list=all")
        assert [tab["label"] for tab in page_of(response)["scopeTabs"]] == [
            "Unrestricted"
        ]
        assert page_of(response)["scopeTabs"][0]["current"] is True
        assert "Mesh Armour" in response.content.decode()


class TestSupplementaryPetsNavigation:
    @pytest.mark.parametrize("json_command", [False, True])
    def test_unrestricted_keeps_pet_list_terms_before_the_post(
        self, client, tester, fighter, gang, json_command
    ):
        from uuid import uuid4

        from n26.core.owned import thing_key
        from n26.core.reconcile import assert_reconciled
        from n26.library.authoring import create_trading_post
        from n26.library.models import Wargear

        harness = create_wargear("Pet harness", price=40, trade_point_price=3)
        pets = create_collection(
            "Supplementary Pets", entries=[(harness, {"price_override": 10})]
        )
        post = create_trading_post(contains=[Wargear])
        with operation(gang, actor=tester) as op:
            op.assign(pets, gang=gang)
        client.force_login(tester)
        props = page_of(client.get(f"{equip_url(fighter)}?list=all"))
        assert [tab["key"] for tab in props["scopeTabs"]] == [
            str(post.pk),
            str(pets.pk),
            "all",
        ]
        row = next(
            row
            for section in props["sections"]
            for category in section["categories"]
            for row in category["entries"]
            if row["name"] == "Pet harness"
        )
        assert row["purchase"]["price"] == 10 and row["purchase"]["tradePoints"] is None
        payload = {"thing": thing_key(harness), "confirmed": "1"}
        at = f"{equip_url(fighter)}?list=all"
        if json_command:
            at = reverse("n26-equip-fighter-command", args=[fighter.pk])
            payload.update(
                action="buy",
                request_key=str(uuid4()),
                list="all",
                selection="[]",
                parts="[]",
            )
        response = client.post(at, payload)
        assert response.status_code == (200 if json_command else 302)
        if json_command:
            assert response.json()["outcome"] == "completed"
        holding = Assignment.objects.get(miniature_root=fighter, wargear=harness)
        assert holding.ledger_entry.paid == 10
        assert holding.ledger_entry.trade_points == 0
        gang.refresh_from_db()
        assert gang.credits == 90
        assert_reconciled(gang)

    @pytest.mark.parametrize("with_house", [True, False])
    def test_pets_follow_the_standard_post_without_becoming_the_default(
        self, client, tester, fighter, gang, house_list, with_house
    ):
        from n26.library.authoring import create_trading_post

        pets = create_collection(
            "Supplementary Pets", entries=[create_wargear("Pet harness", price=5)]
        )
        post = create_trading_post()
        with operation(gang, actor=tester) as op:
            op.assign(pets, gang=gang)
            if not with_house:
                op.remove(Assignment.objects.get(gang_root=gang, collection=house_list))
        client.force_login(tester)
        props = page_of(client.get(equip_url(fighter)))
        assert [tab["key"] for tab in props["scopeTabs"]] == [
            *([str(house_list.pk)] if with_house else []),
            str(post.pk),
            str(pets.pk),
            "all",
        ]
        assert props["scope"] == str(house_list.pk if with_house else post.pk)
        selected = page_of(client.get(equip_url(fighter, pets)))
        assert selected["scope"] == str(pets.pk)

    def test_pets_remain_available_without_a_standard_post(
        self, client, tester, fighter, gang
    ):
        pets = create_collection(
            "Supplementary Pets", entries=[create_wargear("Pet harness", price=5)]
        )
        with operation(gang, actor=tester) as op:
            op.assign(pets, gang=gang)
        client.force_login(tester)
        props = page_of(client.get(equip_url(fighter)))
        assert props["scope"] == str(pets.pk)
        assert [tab["key"] for tab in props["scopeTabs"]] == [str(pets.pk), "all"]


class TestTheLibraryTabsQueryBudget:
    """The library is hundreds of rows, and a query per row is how a page
    stops loading. Pinned so it changes deliberately, and measured after
    one warm request — the first request of a session writes its own row.
    """

    def measure(self, client, url):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        assert client.get(url).status_code == 200
        with CaptureQueriesContext(connection) as captured:
            assert client.get(url).status_code == 200
        return len(captured.captured_queries)

    @pytest.fixture
    def stocked(self, default_pack):
        from n26.library.authoring import create_subtype, create_weapon

        walker = create_subtype("Walker")
        create_wargear("Mesh Armour", price=15)
        create_weapon(
            "Autogun", price=20, profiles=[("", 0)], usable_by_subtypes=[walker]
        )
        return walker

    def test_it_costs_a_fixed_number(
        self, client, tester, fighter, house_list, stocked
    ):
        client.force_login(tester)

        # The reader and their session, the gang, the fighter's card with
        # its options and — since the card is drawn above the listing —
        # its characteristics strip, which is the statline's own handful
        # of reads plus the owner's hand-set values, the roster behind
        # the header's count, which held lists hold gear, the campaign's
        # assets the gang holds — the library: one query per gear kind, plus the
        # guns' paid rounds, each kind's offers and each restricted
        # kind's use lists — and a browse of each list held, which is
        # what prices the library's lines. A fixed number per list,
        # never one per item. One more reads the gang's dismissed offers,
        # and one reads the n26 write-pause state for the page notice.
        # Action controls read tracking state, earned uses, drafts and history
        # once for this model, independent of the number of library rows.
        # One read checks the built-in visit's default visibility.
        assert self.measure(client, f"{equip_url(fighter)}?list=all") == 68

    def test_it_costs_the_same_however_much_it_holds(
        self, client, tester, fighter, house_list, stocked
    ):
        """Restricted weapons in particular: each carries three use
        lists, and noting the library without them loaded would be three
        queries a gun."""
        from n26.library.authoring import create_weapon

        client.force_login(tester)
        url = f"{equip_url(fighter)}?list=all"

        few = self.measure(client, url)
        for index in range(5):
            create_wargear(f"Filler {index}", price=5)
            create_weapon(
                f"Filler gun {index}",
                price=5,
                profiles=[("", 0)],
                usable_by_subtypes=[stocked],
            )
        assert self.measure(client, url) == few


class TestTheCardAboveTheListing:
    """The Equip screen draws the model's card above its tabs — the same
    card the Edit face draws, its controls out — so what the model holds
    and what it makes of them are in view while buying.
    """

    def test_the_card_sits_between_the_header_and_the_tabs(
        self, client, tester, fighter, house_list
    ):
        client.force_login(tester)
        response = client.get(equip_url(fighter, house_list))
        model = page_of(response)["model"]
        assert model["name"] == fighter.name
        assert model["card"]["name"] == fighter.name
        assert [
            cell["shortName"] for group in model["card"]["statGroups"] for cell in group
        ]
        assert next(tab for tab in model["tabs"] if tab["current"])["label"] == "Equip"

    def test_it_is_drawn_in_edit_mode_with_the_kit_acts_out(
        self, client, tester, gang, fighter, house_list
    ):
        """The kit acts open over this screen, which holds the panels
        the listing's own copies open."""
        from n26.library.models import Wargear

        with operation(gang, actor=tester) as op:
            op.buy(fighter, thing=Wargear.objects.get(name="Sword"), paid=35)
        client.force_login(tester)
        response = client.get(equip_url(fighter, house_list))
        model = page_of(response)["model"]
        lines = [
            line
            for row in model["card"]["details"]
            for part in row["parts"]
            if part["kind"] == "gear"
            for line in part["lines"]
        ]
        sword = next(line for line in lines if line["text"] == "Sword")
        assert {action["label"] for action in sword["actions"]} >= {
            "Sell",
            "Reassign",
            "Refund",
            "Delete",
        }
        assert model["card"]["stored"]["statusHref"]
        assert model["card"]["stored"]["renameHref"]

    def counter_on(self, gang, tester, fighter):
        """The fighter's XP counter, given once."""
        from n26.library.authoring import create_counter

        with operation(gang, actor=tester) as op:
            op.assign(create_counter("XP"), miniature=fighter)
        return Assignment.objects.get(miniature=fighter, counter__name="XP")

    def tallied_from(self, client, counter, back):
        """The counter moved over htmx, the control posting ``back`` as
        the screen it was drawn on — and the card sent back."""
        response = client.post(
            reverse("n26-tally", args=[counter.pk]),
            {"change": "1", "back": back},
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        body = response.content.decode()
        return body[body.index('id="n26-model-card-host"') :]

    def test_a_tally_from_here_sends_back_a_card_addressed_to_here(
        self, client, tester, gang, fighter, house_list
    ):
        """The card an act sends back replaces the one on the page, kit
        menus and all. A card addressed to the Edit face would leave the
        Equip screen with a Sell that opens somewhere else."""
        from n26.library.models import Wargear

        with operation(gang, actor=tester) as op:
            op.buy(fighter, thing=Wargear.objects.get(name="Sword"), paid=35)
        client.force_login(tester)
        here = equip_url(fighter, house_list)

        card = self.tallied_from(client, self.counter_on(gang, tester, fighter), here)

        assert f'href="{here}&amp;sell=' in card
        assert f"{reverse('n26-edit-fighter', args=[fighter.pk])}?sell=" not in card

    def test_a_tally_naming_another_screen_is_answered_for_the_edit_face(
        self, client, tester, gang, fighter, house_list, make_profile, make_statline
    ):
        """What the control posted names a screen and nothing more: the
        address is rebuilt from the route, so another model's page, a
        page elsewhere, or a query nobody's screen carries never reaches
        a link on the card."""
        from n26.library.models import Wargear

        juve = make_profile("Juve", price=0)
        make_statline(juve)
        with operation(gang, actor=tester) as op:
            other = op.hire(juve, "Kid")
            op.buy(fighter, thing=Wargear.objects.get(name="Sword"), paid=35)
        client.force_login(tester)
        edit = reverse("n26-edit-fighter", args=[fighter.pk])
        counter = self.counter_on(gang, tester, fighter)

        # Another model's Equip screen, and a page that is not this app's:
        # neither is a screen of this model, so the Edit face is drawn.
        for back in (equip_url(other, house_list), "https://elsewhere.example/n26/"):
            card = self.tallied_from(client, counter, back)
            assert f'href="{edit}?sell=' in card
            assert "elsewhere.example" not in card
            assert str(other.pk) not in card

        # This model's own Equip screen with a parameter no screen carries:
        # the screen is recognised and the parameter is dropped.
        here = equip_url(fighter, house_list)
        card = self.tallied_from(client, counter, f"{here}&evil=1")
        assert f'href="{here}&amp;sell=' in card
        assert "evil" not in card

    def test_a_tally_naming_no_address_at_all_is_answered_for_the_edit_face(
        self, client, tester, gang, fighter, house_list
    ):
        """``back`` is a hidden field anybody can type into. A value that
        is not an address — an unclosed IPv6 bracket — is read as the
        Edit face like any other stranger, and never as an error."""
        from n26.library.models import Wargear

        with operation(gang, actor=tester) as op:
            op.buy(fighter, thing=Wargear.objects.get(name="Sword"), paid=35)
        client.force_login(tester)
        edit = reverse("n26-edit-fighter", args=[fighter.pk])
        counter = self.counter_on(gang, tester, fighter)

        for back in ("http://[::1/edit/", "http://[::1/n26/fighters/x/equip/"):
            card = self.tallied_from(client, counter, back)
            assert f'href="{edit}?sell=' in card
            assert "[::1" not in card

    def test_the_options_face_draws_it_too(self, client, tester, fighter):
        client.force_login(tester)
        body = client.get(
            reverse("n26-fighter-options", args=[fighter.pk])
        ).content.decode()
        assert body.index('id="n26-model-card-host"') < body.index("This model")


class TestTheCardsQueryBudget:
    """The card above the listing is read from the same rows the rows
    are, so drawing it costs a fixed number however much the model holds
    and however large the gang around it. Measured after one warm
    request — the first request of a session writes its own row.
    """

    def measure(self, client, url):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        assert client.get(url).status_code == 200
        with CaptureQueriesContext(connection) as captured:
            assert client.get(url).status_code == 200
        return len(captured.captured_queries)

    def test_the_rest_of_the_gang_costs_nothing(
        self, client, tester, gang, fighter, house_list, make_profile, make_statline
    ):
        client.force_login(tester)
        alone = self.measure(client, equip_url(fighter, house_list))
        juve = make_profile("Juve", price=0)
        make_statline(juve)
        for n in range(12):
            with operation(gang, actor=tester) as op:
                op.hire(juve, f"Extra {n}")
        assert self.measure(client, equip_url(fighter, house_list)) == alone

    def test_the_kit_costs_nothing_per_copy(
        self, client, tester, gang, fighter, house_list
    ):
        """Each piece of kit on the card carries Sell and the rest, and
        saying what a copy was bought with must come off the card already
        built, never from a query per copy."""
        from n26.library.authoring import create_weapon
        from n26.library.models import Wargear

        knife = Wargear.objects.get(name="Knife")
        gun = create_weapon("Lasgun", price=5, profiles=[("", 0)])
        with operation(gang, actor=tester) as op:
            op.buy(fighter, thing=knife, paid=10)
            op.buy(fighter, thing=gun, paid=5)
        client.force_login(tester)
        one_each = self.measure(client, equip_url(fighter, house_list))
        with operation(gang, actor=tester) as op:
            for _ in range(4):
                op.buy(fighter, thing=knife, paid=10)
                op.buy(fighter, thing=gun, paid=5)
        assert self.measure(client, equip_url(fighter, house_list)) == one_each
