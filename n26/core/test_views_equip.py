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
from n26.core.taxonomy import UNCATEGORISED
from n26.library.authoring import create_category, create_collection, create_wargear
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


def test_a_buy_stays_on_the_section_tab_too(client, tester, fighter, house_list):
    """The picker's section tab is client state, posted along and echoed
    back in the redirect — buying from the Wargear tab must not land the
    reader back on the first tab."""
    from n26.library.models import Wargear

    knife = Wargear.objects.get(name="Knife")
    client.force_login(tester)
    response = client.post(
        equip_url(fighter, house_list),
        {"thing": key_of(knife), "section": "Close combat weapons"},
    )
    assert response.status_code == 302
    assert f"list={house_list.pk}" in response.url
    assert "section=Close+combat+weapons" in response.url


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


def test_a_collection_of_skills_is_no_tab_however_the_fighter_holds_it(
    client, tester, gang, make_profile, make_statline
):
    """Holding a collection and shopping from it are different things.

    A fighter's skill sets reach their card by exactly the route their
    equipment list does — a built-in on their profile — so nothing about
    how it is held can tell the two apart. What is in it can: there is
    nothing in a set of skills to buy, so a collection of them is offered
    to nobody as somewhere to shop.
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
    assert [tab["label"] for tab in response.context["collection_tabs"]] == [
        "Ironhead Squats"
    ]
    assert "Catfall" not in response.content.decode()


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
    """Every row of the rail is a list to buy from, so a name that ends by
    saying so spends the rail's width on the one word they all have. The
    full name stays on the link for anyone who wants it."""
    import re

    from n26.library.authoring import create_trading_post

    nomads = create_collection(
        "Ash Waste Nomads Equipment List", entries=[create_wargear("Rope", price=5)]
    )
    with operation(gang, actor=tester) as op:
        op.assign(nomads, gang=gang)
    create_trading_post()

    client.force_login(tester)
    body = client.get(equip_url(fighter, nomads)).content.decode()
    assert re.search(r">\s*Ash Waste Nomads\s*<", body)
    assert 'title="Ash Waste Nomads Equipment List"' in body


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


def test_the_strip_names_each_section_once(client, tester, gang, fighter):
    """The strip keys its tabs by name, so a repeat draws neither — and
    the page would serve rows no tab could reach. The listing gives each
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

    strip = response.context["sections"]
    assert strip == ["Close combat", "Ranged"]
    assert [s.name for s in response.context["listing"].sections] == strip


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

    assert response.context["has_trade_points"] is False
    assert "Trade points" not in response.content.decode()


def test_the_trading_post_draws_one(client, tester, gang, fighter):
    """It is the surface the figure means something on."""
    from n26.library.authoring import create_trading_post

    create_wargear("Lho Sticks", price=5, trade_point_price=3)
    post = create_trading_post()

    client.force_login(tester)
    response = client.get(equip_url(fighter, post))

    assert response.context["has_trade_points"] is True
    assert response.context["tp_ceiling"] == 3


def test_the_page_has_a_strip_for_the_list_and_a_strip_for_the_section(
    client, tester, fighter, house_list
):
    """Two strips, choosing two different things. The upper one picks the
    list and is links the server answers; the lower one picks which section
    of that list is on screen and swaps it in the hand. Lose the lower one
    and every section draws at once, one under the next."""
    from n26.library.authoring import create_trading_post

    create_trading_post()

    client.force_login(tester)
    body = client.get(equip_url(fighter, house_list)).content.decode()
    assert 'aria-label="Which list"' in body
    assert 'role="tablist"' in body
    # The section strip is the picker's, so the sections must not also be
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
        category.name or section.name
        for section in response.context["listing"].sections
        for category in section.categories
    }
    assert registration_names <= set(response.context["categories"])


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
    assert response.context["sections"] == ["Armoury", UNCATEGORISED]

    drawn = {section.name for section in response.context["listing"].sections}
    assert drawn <= set(response.context["sections"])
    registration_names = {
        category.name or section.name
        for section in response.context["listing"].sections
        for category in section.categories
    }
    assert registration_names <= set(response.context["categories"])


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
    """How the list is narrowed and which section is on screen: both stay
    put while the rows scroll under them, pinned by sitting in one sticky
    box rather than two, so neither band has to know how tall the other
    is. Which list is the rail's business — beside the listing, not
    pinned over it — so it must not be in the box."""
    from n26.library.authoring import create_trading_post

    create_trading_post()

    client.force_login(tester)
    body = client.get(equip_url(fighter, house_list)).content.decode()

    assert body.count("--n26-sticky-top, 0px") == 1
    assert 'aria-label="Which list"' in body
    inside = pinned_tags(body)
    assert not any(tag.get("aria-label") == "Which list" for tag in inside)
    assert any(tag.get("role") == "search" for tag in inside)
    assert any(tag.get("role") == "tablist" for tag in inside)
    # The rows themselves are not: they are what scrolls under it.
    assert not any(tag.get("name") == "thing" for tag in inside)


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
    body = response.content.decode()
    sections = response.context["sections"]
    assert len(sections) == 2

    rows = [tag for tag in pinned_tags(body) if tag.get("role") == "menuitem"]
    assert rows
    # Each section's name reaches its row through the row's own state, which
    # is where the menu reads it back from when the row is pressed.
    for section_name in sections:
        assert any(section_name in (tag.get("x-data") or "") for tag in rows)


def test_the_strip_is_two_shapes_and_the_width_picks_one(
    client, tester, fighter, house_list
):
    """Two strips are written, and only one of them is on screen at a time:
    the full row of tabs from sm up, the single current tab plus a menu
    below it. A breakpoint, not a measurement, so there is nothing to
    mis-measure."""
    client.force_login(tester)
    body = client.get(equip_url(fighter, house_list)).content.decode()

    strips = [tag for tag in pinned_tags(body) if tag.get("role") == "tablist"]
    assert len(strips) == 2
    wide, narrow = (tag.get("class") or "" for tag in strips)
    assert "hidden" in wide and "sm:flex" in wide
    assert "flex" in narrow and "sm:hidden" in narrow

    # The measuring strip is gone entirely, not merely disused.
    assert "ResizeObserver" not in body
    assert 'x-ref="ghost"' not in body


def test_pressing_a_tab_in_the_full_strip_moves_nothing(
    client, tester, fighter, house_list
):
    """Where every section is a tab, the row is fixed: choosing one changes
    which is accented and nothing else, so a reader can go straight back to
    the tab they came from. Nothing in the strip may set flex order or hide
    a tab from the row — both are ways of putting the current one first,
    which is the narrow strip's job and this one's bug."""
    client.force_login(tester)
    body = client.get(equip_url(fighter, house_list)).content.decode()

    assert "order: -1" not in body
    assert "'border-accent" in body
    assert "'border-box-border text-muted" in body
    assert "hidden sm:flex" not in body


def test_the_narrow_strip_is_the_current_tab_and_a_counted_menu(
    client, tester, fighter, house_list
):
    """Below sm the strip is the section you are on plus a menu of the rest.
    The tab is bound straight to the section on screen — there is only ever
    one of it, with no sibling to hide — and the menu's button counts what
    it holds, so a chevron beside a lone tab is not mistaken for decoration.

    The count says "more" at every number, which is why nothing here reads
    like a plural waiting to be written."""
    client.force_login(tester)
    body = client.get(equip_url(fighter, house_list)).content.decode()

    assert 'x-text="visibleSection"' in body
    assert "`+${picker.liveSections.length - 1} more`" in body


def test_the_section_menu_asks_the_listing_and_not_the_menu(
    client, tester, fighter, house_list
):
    """The switcher's panel keeps state under the same names this component
    does — items, matches, register — so a row asking how full a section is
    gets the menu's own row count instead, every section reads as empty, and
    nothing anywhere says why. The listing's scope is therefore held under
    a name of its own for the rows to reach."""
    client.force_login(tester)
    body = client.get(equip_url(fighter, house_list)).content.decode()

    assert "{ picker: $data }" in body
    assert "picker.countInSection(label)" in body
    assert "picker.visibleSection" in body


def test_the_count_above_the_list_counts_the_section_on_screen(
    client, tester, fighter, house_list
):
    """The readout is client-side, so what is pinned here is the
    arrangement that keeps it honest: it counts the same array the rows
    come from, narrowed to the section the tab strip is showing. A total
    spanning the sections a tab is hiding is a number that contradicts the
    list directly beneath it."""
    client.force_login(tester)
    body = client.get(equip_url(fighter, house_list)).content.decode()

    assert 'x-text="shown"' in body
    assert "this.countInSection(this.visibleSection)" in body
    # The "N of M" form: how many are left, out of how many the section has.
    assert 'x-show="shown !== total"' in body
    assert "this.counts.sectionTotal[this.visibleSection]" in body


def buy_one(gang, fighter, tester, thing, **kwargs):
    """One of these on the fighter, through the ledger like anything else."""
    with operation(gang, actor=tester) as op:
        return op.buy(fighter, thing=thing, **kwargs)


def rows_of(response):
    """The listing's rows, by name. What the page was handed to draw."""
    return {row.name: row for row in response.context["listing"].all_rows()}


def test_owning_one_is_a_state_of_the_row_whatever_kind_of_thing_it_is(
    client, tester, gang, fighter, house_list
):
    """Not a treatment reserved for some rows. The knife is an ordinary
    line — freely available, no exclusivity, nothing special about it —
    and holding one turns its row into the owned kind all the same."""
    from n26.core.listing import OwnedRow, PricedRow
    from n26.library.models import Wargear

    knife = Wargear.objects.get(name="Knife")
    client.force_login(tester)
    rows = rows_of(client.get(equip_url(fighter, house_list)))
    assert rows["Knife"].is_exclusive is False
    assert isinstance(rows["Knife"], PricedRow)

    buy_one(gang, fighter, tester, knife, paid=10)

    rows = rows_of(client.get(equip_url(fighter, house_list)))
    assert isinstance(rows["Knife"], OwnedRow)
    assert rows["Knife"].count == 1


def test_two_of_one_weapon_are_two_lines_that_can_be_told_apart(
    client, tester, gang, fighter, gun_list
):
    """Each is its own row in the ledger, each may carry different ammo,
    and each is sold on its own — so one line counted twice would be a
    control that acts on whichever the server picked. The page carries an
    address per copy and per part; the shape behind it is pinned in the
    listing's own suite."""
    from n26.library.models import Weapon, WeaponProfile

    autogun = Weapon.objects.get(name="Autogun")
    warp = WeaponProfile.objects.get(name="warp round")
    with operation(gang, actor=tester) as op:
        first = op.give_weapon(fighter, autogun, paid=20)
        ammo = op.buy_weapon_profile(first, warp)
        second = op.give_weapon(fighter, autogun, paid=20)

    client.force_login(tester)
    response = client.get(equip_url(fighter, gun_list))
    row = rows_of(response)["Autogun"]

    assert {copy.id for copy in row.copies} == {str(first.pk), str(second.pk)}
    body = response.content.decode()
    for assignment in (first, second, ammo):
        assert f"sell={assignment.pk}" in body


def test_what_a_fighter_is_gets_no_controls(client, tester, gang, fighter, house_list):
    """The card holds the profile that *is* the fighter, the XP they have
    earned and the skills they know. None of it is kit, and none of it may
    grow a Sell button — see n26.core.owned.is_possession."""
    from n26.library.authoring import create_skill

    with operation(gang, actor=tester) as op:
        op.learn(fighter, create_skill("Marksman"))

    client.force_login(tester)
    body = client.get(equip_url(fighter, house_list)).content.decode()

    assert f"sell={fighter.membership.pk}" not in body


def test_a_row_for_something_owned_counts_it_and_still_sells_another(
    client, tester, gang, fighter, house_list
):
    """The count stands where Buy was, and Buy moves under it. A reader
    looking at a row for a thing they are carrying is usually asking what
    to do with the one they have — but owning one has never been a reason
    the shop stops selling it, so the offer is still on the page."""
    from n26.core.listing import PricedRow
    from n26.library.models import Wargear

    knife = Wargear.objects.get(name="Knife")
    client.force_login(tester)
    assert isinstance(
        rows_of(client.get(equip_url(fighter, house_list)))["Knife"], PricedRow
    )

    buy_one(gang, fighter, tester, knife, paid=10)
    buy_one(gang, fighter, tester, knife, paid=10)

    response = client.get(equip_url(fighter, house_list))
    rows = rows_of(response)
    assert rows["Knife"].count == 2
    assert isinstance(rows["Sword"], PricedRow)
    # The count is drawn in words, and the Buy the row replaced is still
    # submitted by the same key from inside it.
    body = response.content.decode()
    assert "2</span> equipped" in body
    assert f'value="{key_of(knife)}"' in body


def test_buying_another_from_inside_an_owned_row_buys_one(
    client, tester, gang, fighter, house_list
):
    """The nested row is the ordinary row, so its press is the ordinary
    press: same key, same till, same result as a fighter with none."""
    from n26.library.models import Wargear

    knife = Wargear.objects.get(name="Knife")
    buy_one(gang, fighter, tester, knife, paid=10)

    client.force_login(tester)
    response = client.post(equip_url(fighter, house_list), {"thing": key_of(knife)})

    assert response.status_code == 302
    assert rows_of(client.get(equip_url(fighter, house_list)))["Knife"].count == 2


def test_a_thing_taken_off_the_card_stops_being_counted(
    client, tester, gang, fighter, house_list
):
    from n26.core.listing import PricedRow
    from n26.library.models import Wargear

    knife = Wargear.objects.get(name="Knife")
    assignment = buy_one(gang, fighter, tester, knife, paid=10)
    with operation(gang, actor=tester) as op:
        op.remove(assignment)

    client.force_login(tester)
    rows = rows_of(client.get(equip_url(fighter, house_list)))
    assert isinstance(rows["Knife"], PricedRow)


def test_the_owned_row_offers_everything_that_can_happen_to_a_copy(
    client, tester, gang, fighter, house_list
):
    from n26.library.models import Wargear

    assignment = buy_one(
        gang, fighter, tester, Wargear.objects.get(name="Knife"), paid=10
    )
    client.force_login(tester)
    body = client.get(equip_url(fighter, house_list)).content.decode()

    for act in ("sell", "reassign", "refund", "remove"):
        assert f"?list={house_list.pk}&amp;{act}={assignment.pk}" in body


def test_no_dialog_until_the_url_asks_for_one(client, tester, fighter, house_list):
    client.force_login(tester)
    assert client.get(equip_url(fighter, house_list)).context["dialog"] is None


def test_a_sale_confirmation_states_its_arithmetic(
    client, tester, gang, fighter, house_list
):
    """The figure is worked out from rows the reader cannot see, and it is
    money, so the dialog shows its working. Thirty-five halves to
    seventeen and a half, and a sale rounds the player's way."""
    from n26.library.models import Wargear

    sword = buy_one(gang, fighter, tester, Wargear.objects.get(name="Sword"), paid=35)
    client.force_login(tester)
    response = client.get(f"{equip_url(fighter, house_list)}&sell={sword.pk}")
    body = response.content.decode()

    assert response.context["dialog"]["proceeds"] == 18
    assert "Half of 35¢, rounded up — 18¢." in body
    assert "<dialog open" in body
    assert reverse("n26-sell", args=[sword.pk]) in body


def test_a_sale_of_something_worth_almost_nothing_names_the_floor(
    client, tester, gang, fighter, house_list
):
    from n26.library.authoring import create_wargear

    trinket = buy_one(gang, fighter, tester, create_wargear("Charm", price=4), paid=4)
    client.force_login(tester)
    body = client.get(
        f"{equip_url(fighter, house_list)}&sell={trinket.pk}"
    ).content.decode()

    assert "5¢: half of 4¢ is less than the 5¢ a sale never goes under." in body


def test_a_move_offers_the_stash_and_the_roster(
    client, tester, gang, fighter, house_list
):
    from n26.library.models import Wargear

    knife = buy_one(gang, fighter, tester, Wargear.objects.get(name="Knife"), paid=10)
    with operation(gang, actor=tester) as op:
        op.hire(fighter.membership.assignable, "Nell")

    client.force_login(tester)
    response = client.get(f"{equip_url(fighter, house_list)}&reassign={knife.pk}")
    body = response.content.decode()

    assert [model.name for model in response.context["dialog"]["models"]] == ["Nell"]
    assert 'name="to" value="stash"' in body
    assert 'name="miniature"' in body


def test_a_move_with_nobody_else_on_the_roster_is_a_move_to_the_stash(
    client, tester, gang, fighter, house_list
):
    """One fighter and a stash is not a choice between two places, so the
    only act on the form is the one place it can go."""
    from n26.library.models import Wargear

    knife = buy_one(gang, fighter, tester, Wargear.objects.get(name="Knife"), paid=10)
    client.force_login(tester)
    response = client.get(f"{equip_url(fighter, house_list)}&reassign={knife.pk}")
    body = response.content.decode()

    assert response.context["dialog"]["submit_label"] == "To the stash"
    assert '<input type="hidden" name="to" value="stash">' in body
    assert 'name="miniature"' not in body


def test_a_removal_says_the_money_stays_spent(
    client, tester, gang, fighter, house_list
):
    from n26.library.models import Wargear

    knife = buy_one(gang, fighter, tester, Wargear.objects.get(name="Knife"), paid=10)
    client.force_login(tester)
    body = client.get(
        f"{equip_url(fighter, house_list)}&remove={knife.pk}"
    ).content.decode()

    assert "stays spent" in body
    assert reverse("n26-remove", args=[knife.pk]) in body


def test_a_refund_names_what_was_paid_and_not_what_it_is_worth(
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
    body = client.get(
        f"{equip_url(fighter, house_list)}&refund={knife.pk}"
    ).content.decode()

    assert "5¢ comes back" in body
    assert "not what it is worth" in body
    assert reverse("n26-refund", args=[knife.pk]) in body


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
    assert response.context["dialog"] is None


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


def test_the_figures_and_the_roster_line_stand_above_the_listing(
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
    body = client.get(equip_url(fighter)).content.decode()
    assert "Models in the gang" in body
    assert ">2</dd>" in body
    gang.refresh_from_db()
    assert f">{gang.credits}\u00a2</dd>" in body
    # Karn links to his own equip screen, with his rating beside the name.
    assert equip_url(other) in body
    assert f"{other.rating}\u00a2" in body
    # Vex is where the reader already is: named, marked, not a link.
    assert 'aria-current="page"' in body


def test_a_gang_with_no_budget_is_offered_no_refund(
    client, tester, gang, fighter, house_list
):
    """A gang founded without a budget never paid credits, so its owned rows
    offer Remove alone — and a refund address, followed anyway, asks the
    remove question rather than promising 0\u00a2 back."""
    from n26.library.models import Wargear

    sword = Wargear.objects.get(name="Sword")
    client.force_login(tester)
    client.post(equip_url(fighter, house_list), {"thing": key_of(sword)})

    body = client.get(equip_url(fighter, house_list)).content.decode()
    assert ">Refund<" in body  # budgeted: the act is offered

    gang.starting_credits = None
    gang.save(update_fields=["starting_credits"])
    body = client.get(equip_url(fighter, house_list)).content.decode()
    assert ">Refund<" not in body
    assert ">Delete<" in body

    owned = Assignment.objects.get(
        miniature=fighter, parent__isnull=True, archived=False
    )
    asked = client.get(
        f"{equip_url(fighter, house_list)}&refund={owned.pk}"
    ).content.decode()
    assert "Delete" in asked
    assert "Refund" not in asked


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
    """An autogun on the fighter, bought through the listing."""
    from n26.library.models import Weapon

    with operation(gang, actor=tester) as op:
        return op.buy(fighter, thing=Weapon.objects.get(name="Autogun"), paid=20)


def panel_for(response, assignment):
    """The accessory panel this page is carrying about one weapon."""
    return next(
        panel
        for panel in response.context["accessorise"]
        if panel["id"] == str(assignment.pk)
    )


def name_cell(body, label):
    """Whatever is drawn alongside the control carrying ``label``.

    Everything back to the last closed element, which is the run of
    markup the control shares a line with — so a control that moved into
    the acts on the right of the row would come back with the acts and
    not with the words it is about.
    """
    return body[: body.index(f'aria-label="{label}"')].rsplit("</span>", 1)[-1]


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
        body = client.get(equip_url(fighter, gun_list)).content.decode()

        assert f"?list={gun_list.pk}&amp;accessorise={owned_gun.pk}" in body
        assert 'aria-label="Add accessory to Autogun"' in body
        assert "Autogun" in name_cell(body, "Add accessory to Autogun")

    def test_the_press_opens_the_panel_the_page_is_already_holding(
        self, client, tester, fighter, gun_list, owned_gun, accessories
    ):
        """The link and the press reach one state. The press does it
        without asking for a listing of several hundred rows again."""
        client.force_login(tester)
        body = client.get(equip_url(fighter, gun_list)).content.decode()

        assert f'id="n26-accessorise-{owned_gun.pk}"' in body
        assert (
            f"$dispatch('n26-dialog-open', {{ id: 'n26-accessorise-{owned_gun.pk}'"
            in body
        )

    def test_every_gun_carries_its_own_panel_on_a_plain_visit(
        self, client, tester, gang, fighter, gun_list, owned_gun, accessories
    ):
        """Nothing is asked for, and every gun's question is answered
        anyway — that is what makes the press instant."""
        from n26.library.models import Weapon

        with operation(gang, actor=tester) as op:
            second = op.buy(fighter, thing=Weapon.objects.get(name="Autogun"), paid=20)

        client.force_login(tester)
        response = client.get(equip_url(fighter, gun_list))
        body = response.content.decode()

        assert {panel["id"] for panel in response.context["accessorise"]} == {
            str(owned_gun.pk),
            str(second.pk),
        }
        assert not any(panel["open"] for panel in response.context["accessorise"])
        # Closed, so no `open` attribute — a browser draws nothing until
        # the press, and a reader with no script follows the link instead.
        assert "<dialog open" not in body
        assert body.count("Telescopic sight — 25¢") == 2

    def test_the_address_opens_it(
        self, client, tester, fighter, gun_list, owned_gun, accessories
    ):
        """A link somebody sent, or a reload of a page opened by a press.
        The server draws that one open and the rest closed."""
        client.force_login(tester)
        response = client.get(
            f"{equip_url(fighter, gun_list)}&accessorise={owned_gun.pk}"
        )
        body = response.content.decode()

        assert panel_for(response, owned_gun)["open"] is True
        assert "<dialog open" in body
        assert reverse("n26-accessorise", args=[owned_gun.pk]) in body
        assert "Add accessory" in body

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
        assert "Telescopic sight — 25¢" in response.content.decode()

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

        assert response.context["accessorise"] == []
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

    def test_a_weapon_with_nothing_to_fit_it_is_told_so_and_offered_no_press(
        self, client, tester, fighter, gun_list, owned_gun
    ):
        """No accessories authored at all. A green button over an empty
        list would promise an act it could not do."""
        client.force_login(tester)
        body = client.get(
            f"{equip_url(fighter, gun_list)}&accessorise={owned_gun.pk}"
        ).content.decode()

        assert "Nothing in the library fits this weapon." in body
        assert ">Add accessory<" not in body

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
        assert response.context["dialog"] is None
        assert response.context["accessorise"] == []
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

    def test_the_dialog_carries_the_list_and_tab_through_the_press(
        self, client, tester, fighter, gun_list, owned_gun, accessories
    ):
        """Cancel comes back to the page as it was, and so does the answer."""
        client.force_login(tester)
        body = client.get(
            f"{equip_url(fighter, gun_list)}&section=Weapons&accessorise={owned_gun.pk}"
        ).content.decode()

        assert f'name="list" value="{gun_list.pk}"' in body
        assert 'name="section" value="Weapons"' in body


class TestTheSellDialogWhenSomethingIsBoltedOn:
    """The sale of a gun with a sight on it is two sales at two prices,
    so the confirmation asks which one is meant."""

    def test_a_bare_weapon_is_asked_no_question(
        self, client, tester, fighter, gun_list, owned_gun
    ):
        client.force_login(tester)
        response = client.get(f"{equip_url(fighter, gun_list)}&sell={owned_gun.pk}")

        assert "keepable" not in response.context["dialog"]
        assert "Stash the accessor" not in response.content.decode()

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
        dialog = response.context["dialog"]
        body = response.content.decode()

        assert dialog["keepable"] == "Telescopic sight"
        # Twenty credits of gun halves to ten; the gun and its sight
        # together are forty-five, which halves to twenty-three.
        assert dialog["proceeds"] == 10
        assert "Stash the accessory" in body
        assert "Sell the accessory too" in body
        assert "23¢" in body
        assert 'value="stash"' in body
        assert 'value="sell"' in body
