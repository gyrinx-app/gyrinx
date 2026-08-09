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
from n26.library.models import Collection

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


def test_each_list_is_a_tab_of_its_own(client, tester, fighter, house_list):
    """The lists a fighter's built-ins carry, then the Trading Post — one
    tab each, every one a link, and exactly one of them current."""
    from n26.library.authoring import create_trading_post

    create_wargear("Lho Sticks", price=5, trade_point_price=1)
    create_trading_post()

    client.force_login(tester)
    tabs = client.get(equip_url(fighter, house_list)).context["collection_tabs"]
    assert [tab["label"] for tab in tabs] == ["House List", "Trading Post"]
    assert [tab["href"] for tab in tabs] == [
        f"?list={house_list.pk}",
        f"?list={Collection.objects.get(name='Trading Post').pk}",
    ]
    assert [tab["current"] for tab in tabs] == [True, False]


def test_the_strip_holds_this_fighters_list_and_no_other_houses(
    client, tester, gang, make_profile, make_statline
):
    """A pack holds every house's equipment list at once. Which of them a
    fighter can buy from is a fact about the fighter — the collection
    their built-ins carry — and never a fact about the pack: a Squats
    fighter offered the Van Saar list is being shown the library rather
    than their own kit.

    "Skills & Powers" is the case that makes the difference load-bearing.
    It is a Collection and not an equipment list, so a strip built by
    asking the pack for its collections would offer it as somewhere to
    shop; a strip built from the fighter cannot.
    """
    from n26.library.authoring import add_built_in, create_trading_post

    for house in ["Van Saar", "Orlock", "Escher", "Goliath", "Delaque"]:
        create_collection(
            f"{house} Equipment List", entries=[create_wargear(f"{house} Kit", price=5)]
        )
    create_collection("Skills & Powers", entries=[create_wargear("Psy Focus", price=5)])
    ours = create_collection(
        "Ironhead Squats Equipment List",
        entries=[create_wargear("Las-cutter", price=10)],
    )
    create_wargear("Lho Sticks", price=5, trade_point_price=1)
    create_trading_post()

    # The built-in has to be on the profile before the hire: hiring is
    # what turns a profile's built-ins into the fighter's own rows, and a
    # fighter hired before the list was attached never receives it.
    profile = make_profile("Charter Master", price=0)
    make_statline(profile, movement=4, weapon_skill=3, toughness=4)
    add_built_in(profile, ours)
    with operation(gang, actor=tester) as op:
        fighter = op.hire(profile, "Grum")

    assert Collection.objects.count() == 8

    client.force_login(tester)
    tabs = client.get(equip_url(fighter)).context["collection_tabs"]
    assert [tab["label"] for tab in tabs] == ["Ironhead Squats", "Trading Post"]


def test_a_lone_list_draws_no_strip_and_the_search_box_says_where_you_are(
    client, tester, fighter, house_list
):
    """One list is not a choice. A strip of one tab would be a control that
    does nothing, so the only thing naming the list is the box you search
    it with — which means that name has to be there."""
    client.force_login(tester)
    response = client.get(equip_url(fighter))
    html = response.content.decode()
    assert len(response.context["collection_tabs"]) == 1
    assert "Search House List" in html
    assert 'aria-label="Which list"' not in html


def test_a_tab_drops_the_words_every_tab_shares(client, tester, gang, fighter):
    """Every tab is a list to buy from, so a name that ends by saying so
    spends the strip's width on the one word they all have. The full name
    stays on the link for anyone who wants it."""
    from n26.library.authoring import create_trading_post

    nomads = create_collection(
        "Ash Waste Nomads Equipment List", entries=[create_wargear("Rope", price=5)]
    )
    with operation(gang, actor=tester) as op:
        op.assign(nomads, gang=gang)
    create_trading_post()

    client.force_login(tester)
    body = client.get(equip_url(fighter, nomads)).content.decode()
    assert ">Ash Waste Nomads<" in body
    assert 'title="Ash Waste Nomads Equipment List"' in body


def test_two_names_that_shorten_alike_keep_their_full_names():
    """Two tabs reading the same word is worse than two long ones, and a
    strip is read as a set — so the whole strip falls back together."""
    from n26.core.views.equip import collection_tabs

    class Shelf:
        def __init__(self, name, pk):
            self.name, self.pk = name, pk

        def __str__(self):
            return self.name

    shelves = [Shelf("Orlock Equipment List", 1), Shelf("Orlock", 2)]
    assert [tab["label"] for tab in collection_tabs(shelves, shelves[0])] == [
        "Orlock Equipment List",
        "Orlock",
    ]


def test_the_filter_bar_offers_nothing_to_submit(client, tester, fighter, house_list):
    """The bar narrows rows already on the page, as you type. There is no
    server search behind it, so a Search button would be a control that
    cannot do anything — and a real submit would press the Buy form it sits
    inside."""
    client.force_login(tester)
    body = client.get(equip_url(fighter, house_list)).content.decode()
    assert 'role="search"' in body
    # Every submit on this page buys something.
    assert body.count('type="submit"') == body.count('name="thing"')


def test_the_page_has_a_strip_for_the_list_and_a_strip_for_the_shelf(
    client, tester, fighter, house_list
):
    """Two strips, choosing two different things. The upper one picks the
    list and is links the server answers; the lower one picks which shelf
    of that list is on screen and swaps it in the hand. Lose the lower one
    and every shelf draws at once, one under the next."""
    from n26.library.authoring import create_trading_post

    create_trading_post()

    client.force_login(tester)
    body = client.get(equip_url(fighter, house_list)).content.decode()
    assert 'aria-label="Which list"' in body
    assert 'role="tablist"' in body
    # The shelf strip is the picker's, so the sections must not also be
    # drawing themselves as headings to open.
    assert 'x-show="!tabbed"' in body


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
    body = response.content.decode()
    assert "Armour & shields" in response.context["categories"]
    # Both sides write the name into an attribute, so both are escaped once
    # and the browser hands Alpine the same two strings. Escaped twice, the
    # category's copy would arrive with a literal "&amp;" in it and compare
    # equal to nothing.
    assert '"Armour &amp; shields"' in body
    assert "&amp;amp;" not in body


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
