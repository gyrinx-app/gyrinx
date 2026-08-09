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
    body = client.get(equip_url(fighter, gun_list)).content.decode()

    assert f'name="{parts_field(autogun)}"' in body
    assert 'value="0"' in body
    # The round is priced in a box of its own, under the gun's: two
    # charges on one press, so two numbers a reader can set.
    assert f'name="{price_field(autogun, 0)}"' in body
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


# --- the price is the reader's to set --------------------------------------


def test_the_row_quotes_its_price_in_a_box(client, tester, fighter, house_list):
    """A price a table can change is a box holding the listing's number,
    not a printed figure — and the box the reader types in must be the
    one the till reads back."""
    from n26.library.models import Wargear

    sword = Wargear.objects.get(name="Sword")
    client.force_login(tester)
    body = client.get(equip_url(fighter, house_list)).content.decode()

    assert f'name="{price_field(sword)}"' in body
    # The list's own price for the sword, which is what the till will
    # charge if nobody touches it.
    assert 'value="35"' in body


def test_the_price_typed_in_is_the_price_charged(
    client, tester, gang, fighter, house_list
):
    from n26.core.reconcile import assert_reconciled
    from n26.library.models import Wargear

    sword = Wargear.objects.get(name="Sword")
    client.force_login(tester)
    client.post(
        equip_url(fighter, house_list),
        {"thing": key_of(sword), price_field(sword): "8"},
    )

    gang.refresh_from_db()
    assert gang.credits == 92  # 100 - 8, not 100 - 35
    assert_reconciled(gang)


def test_a_discount_leaves_the_gang_owning_the_same_thing(
    client, tester, gang, fighter, house_list
):
    """What a purchase adds to a gang's worth is the thing's price, not
    the deal struck on it: a sword haggled down is not a lesser sword.
    The entry says both numbers, and the gap between them is the
    discount."""
    from n26.core.models import LedgerEntry
    from n26.core.reconcile import assert_reconciled
    from n26.library.models import Wargear

    sword = Wargear.objects.get(name="Sword")
    client.force_login(tester)
    client.post(
        equip_url(fighter, house_list),
        {"thing": key_of(sword), price_field(sword): "8"},
    )

    entry = LedgerEntry.objects.get(assignment__wargear=sword)
    assert (entry.paid, entry.list_price, entry.discount) == (8, 35, 27)
    assert entry.rating_contribution == 35

    fighter.refresh_from_db()
    gang.refresh_from_db()
    assert fighter.rating == 35
    assert gang.rating == 35
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
        {"thing": key_of(sword), price_field(sword): "0"},
    )

    gang.refresh_from_db()
    assert gang.credits == 100
    assert gang.rating == 35
    assert_reconciled(gang)


def test_an_empty_box_leaves_the_listing_to_price_it(
    client, tester, gang, fighter, house_list
):
    """A box cleared and pressed is not an offer of nothing. With no
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


@pytest.mark.parametrize(
    "hostile",
    [
        "-5",  # would hand the gang credits
        "+5",
        "abc",
        "12.5",
        "1_0",  # Python's int() would read this as ten
        "1e3",
        "100001",  # past the ceiling
        "999999999999",  # past the ledger's column, too
    ],
)
def test_a_price_that_is_not_whole_credits_in_range_buys_nothing(
    client, tester, gang, fighter, house_list, hostile
):
    """The box is typed into by hand and arrives from the browser, so it
    is read as a whole number of credits and nothing else. Anything else
    is refused outright rather than trimmed to fit: charging a figure
    nobody typed is the worse answer."""
    from n26.core.models import Assignment
    from n26.library.models import Wargear

    sword = Wargear.objects.get(name="Sword")
    client.force_login(tester)
    response = client.post(
        equip_url(fighter, house_list),
        {"thing": key_of(sword), price_field(sword): hostile},
    )

    assert response.status_code == 302
    assert not Assignment.objects.filter(wargear=sword).exists()
    gang.refresh_from_db()
    assert gang.credits == 100


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
    """With no script running, a press submits every box on the page.
    Only the boxes scoped to the pressed line may charge anything —
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
        },
    )

    gang.refresh_from_db()
    assert gang.credits == 96
    assert_reconciled(gang)


def test_a_round_is_charged_at_the_price_typed_on_its_own_row(
    client, tester, gang, fighter, gun_list
):
    """One press, two charges: a discount on the gun is not a discount
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
    """Every price on the press is read before anything is written, so a
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
        },
    )

    from n26.core.models import Assignment

    assert not Assignment.objects.filter(weapon_profile=warp).exists()
    gang.refresh_from_db()
    assert gang.credits == 88
    assert_reconciled(gang)


def pinned_tags(body):
    """Every tag inside the picker's one pinned box.

    Walked rather than matched on the order things appear in the page: what
    makes the bands stay on screen together is that they are *inside* that
    box, and a test comparing positions would pass just as happily with one
    of them left outside it.
    """
    from html.parser import HTMLParser

    class Inside(HTMLParser):
        def __init__(self):
            super().__init__()
            self.depth = 0
            self.tags = []

        def handle_starttag(self, tag, attrs):
            found = dict(attrs)
            if self.depth:
                self.tags.append(found)
                if tag == "div":
                    self.depth += 1
            # The box that reads the offset, not the page that sets it: the
            # layout puts --n26-sticky-top on <body>, so matching the name
            # alone starts the walk at the whole document.
            elif "var(--n26-sticky-top" in (found.get("style") or ""):
                self.depth = 1

        def handle_endtag(self, tag):
            if self.depth and tag == "div":
                self.depth -= 1

    reader = Inside()
    reader.feed(body)
    return reader.tags


def test_the_bands_a_reader_steers_with_stay_on_screen_together(
    client, tester, fighter, house_list
):
    """Which list, how it is narrowed, and which shelf: all three stay put
    while the rows scroll under them. They are pinned by sitting in one
    sticky box rather than three, so no band has to know how tall the ones
    above it are — a number only measurement gives, and a wrong one either
    overlaps a band or leaves a stripe of scrolling list between two."""
    from n26.library.authoring import create_trading_post

    create_trading_post()

    client.force_login(tester)
    body = client.get(equip_url(fighter, house_list)).content.decode()

    assert body.count("--n26-sticky-top, 0px") == 1
    inside = pinned_tags(body)
    assert any(tag.get("aria-label") == "Which list" for tag in inside)
    assert any(tag.get("role") == "search" for tag in inside)
    assert any(tag.get("role") == "tablist" for tag in inside)
    # The rows themselves are not: they are what scrolls under it.
    assert not any(tag.get("name") == "thing" for tag in inside)


def test_a_shelf_the_strip_has_no_room_for_is_still_reachable(
    client, tester, fighter, house_list
):
    """Narrow, the strip is the shelf you are on and a chevron holding the
    rest. The strip and that menu are drawn from one list of shelves at
    every width, so a shelf too wide to be a tab is never a shelf with no
    way to it."""
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
    body = response.content.decode()
    shelves = response.context["sections"]
    assert len(shelves) == 2

    rows = [tag for tag in pinned_tags(body) if tag.get("role") == "menuitem"]
    assert rows
    # Each shelf's name reaches its row through the row's own state, which
    # is where the menu reads it back from when the row is pressed.
    for shelf in shelves:
        assert any(shelf in (tag.get("x-data") or "") for tag in rows)


def test_a_strip_that_cannot_measure_itself_draws_every_tab(
    client, tester, fighter, house_list
):
    """How many tabs fit is measured, and measuring can fail — a browser
    with no ResizeObserver, a strip with no width yet, the frame before the
    first reading. Every one of those has to leave the strip showing
    everything and wrapping, because the alternative failure is a strip
    that measures nothing and hides every shelf. The starting value is
    what guarantees it, and the copy the tabs are measured on is what
    stops the strip being measured while it is already hiding things."""
    client.force_login(tester)
    body = client.get(equip_url(fighter, house_list)).content.decode()

    assert "fitted: null," in body
    assert "return this.fitted === null || this.fitted.includes(name)" in body
    assert 'x-ref="ghost"' in body


def test_the_shelf_menu_asks_the_listing_and_not_the_menu(
    client, tester, fighter, house_list
):
    """The switcher's panel keeps state under the same names this component
    does — items, matches, register — so a row asking how full a shelf is
    gets the menu's own row count instead, every shelf reads as empty, and
    nothing anywhere says why. The listing's scope is therefore held under
    a name of its own for the rows to reach."""
    client.force_login(tester)
    body = client.get(equip_url(fighter, house_list)).content.decode()

    assert "{ picker: $data }" in body
    assert "picker.countInSection(label)" in body
    assert "picker.visibleSection" in body


def test_the_count_above_the_list_counts_the_shelf_on_screen(
    client, tester, fighter, house_list
):
    """The readout is client-side, so what is pinned here is the
    arrangement that keeps it honest: it counts the same array the rows
    come from, narrowed to the section the tab strip is showing. A total
    spanning the shelves a tab is hiding is a number that contradicts the
    list directly beneath it."""
    client.force_login(tester)
    body = client.get(equip_url(fighter, house_list)).content.decode()

    assert 'x-text="shown"' in body
    assert "i.section === this.visibleSection" in body
    # The "N of M" form: how many are left, out of how many the shelf has.
    assert 'x-show="shown !== total"' in body
    assert "get total() { return this.onScreen.length }" in body


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
