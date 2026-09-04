"""Buying and managing equipment in a gang's stash.

``browse``, ``Operation.buy`` and the fighter's equip page have their own
tests. These cover the gang-specific destination, lists, stash management,
and the absence of fighter usability rules.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.models import Assignment, Gang
from n26.core.operations import operation
from n26.library.authoring import (
    create_collection,
    create_option_group,
    create_subtype,
    create_wargear,
    create_weapon,
    offer_option,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def tester(db):
    """The signed-in person these tests look at the app as."""
    return User.objects.create_user("player")


@pytest.fixture
def gang(gang_type, tester):
    """A founded gang: founding writes the stash, so this is the shape the
    app really serves rather than a bare gang with no store."""
    gang = Gang.objects.create(
        name="The Ashen Choir",
        owner=tester,
        gang_type=gang_type,
        starting_credits=1000,
        credits=1000,
    )
    with operation(gang, actor=tester) as op:
        op.found(gang_type)
    return gang


@pytest.fixture
def house_list(gang, tester):
    """An equipment list the gang holds: a knife at reference, a sword the
    list prices its own way."""
    knife = create_wargear("Knife", price=10)
    sword = create_wargear("Sword", price=20)
    collection = create_collection(
        "House List", entries=[knife, (sword, {"price_override": 35})]
    )
    with operation(gang, actor=tester) as op:
        op.assign(collection, gang=gang)
    return collection


def equip_url(gang, collection=None, scope=None):
    url = reverse("n26-equip-gang", args=[gang.pk])
    if scope is not None:
        return f"{url}?list={scope}"
    return f"{url}?list={collection.pk}" if collection else url


def key_of(thing):
    return f"{thing._meta.label_lower}:{thing.pk}"


def price_field(thing):
    """The box a line's price is typed into, spelt out rather than
    imported: a test that asks the code under test what it named its
    fields cannot catch the code renaming them."""
    from django.utils.text import slugify

    return f"{slugify(key_of(thing))}:price"


def choice_field(thing, group):
    from django.utils.text import slugify

    return f"{slugify(key_of(thing))}:option:{group}"


class TestTheWayIn:
    """The gang page offers the act, and only to whoever owns the gang."""

    def test_the_owner_is_offered_equip_on_the_stash(self, client, tester, gang):
        client.force_login(tester)
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()

        assert "Equip" in body
        assert reverse("n26-equip-gang", args=[gang.pk]) in body
        assert "Buy Equipment" not in body

    def test_a_reader_who_does_not_own_it_is_offered_nothing(self, client, gang):
        """A roster anybody may read, with none of the acts on it: not a
        disabled button, which is a control saying no, but nothing."""
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()

        assert "Buy Equipment" not in body
        assert reverse("n26-equip-gang", args=[gang.pk]) not in body


class TestWhichListsAreOffered:
    """The gang's own lists, the standard Trading Post, and the library."""

    def test_the_gangs_lists_come_first_and_the_library_last(
        self, client, tester, gang, house_list
    ):
        from n26.library.authoring import create_trading_post

        create_wargear("Lho Sticks", price=5, trade_point_price=1)
        create_trading_post()

        client.force_login(tester)
        tabs = client.get(equip_url(gang)).context["collection_tabs"]

        assert [tab["label"] for tab in tabs] == [
            "In stash",
            "House List",
            "Trading Post",
            "Unrestricted",
        ]
        assert tabs[1]["current"]
        assert tabs[-1]["href"] == "?list=all"

    def test_a_list_of_skills_is_no_tab_however_the_gang_holds_it(
        self, client, tester, gang, house_list
    ):
        """Holding a collection and buying from it are different things:
        a gang carries its skill sets the same way it carries an equipment
        list, and only one of the two is somewhere to buy from."""
        from n26.library.authoring import create_category, create_skill

        ferocity = create_category("Skills", "Ferocity")
        skills = create_collection(
            "Skill Sets", entries=[create_skill("Nerves of Steel", ferocity)]
        )
        with operation(gang, actor=tester) as op:
            op.assign(skills, gang=gang)

        client.force_login(tester)
        tabs = client.get(equip_url(gang)).context["collection_tabs"]

        assert [tab["label"] for tab in tabs] == [
            "In stash",
            "House List",
            "Unrestricted",
        ]

    def test_a_shortened_tab_keeps_its_full_name_on_the_link(
        self, client, tester, gang
    ):
        """Every row of the rail is a list to buy from, so a name that ends
        by saying so spends the rail's width on the one word they all
        have — and as an attribute rather than as words, because a
        template tag written inside a component's attributes is not read
        as one and lands in the page as text."""
        import re

        nomads = create_collection(
            "Ash Waste Nomads Equipment List",
            entries=[create_wargear("Rope", price=5)],
        )
        with operation(gang, actor=tester) as op:
            op.assign(nomads, gang=gang)

        client.force_login(tester)
        body = client.get(equip_url(gang, nomads)).content.decode()

        assert re.search(r">\s*Ash Waste Nomads\s*<", body)
        assert 'title="Ash Waste Nomads Equipment List"' in body
        assert "{% if" not in body

    def test_a_gang_with_no_lists_still_reaches_the_library(self, client, tester, gang):
        """The library tab is always there, so a gang whose content gave it
        no list of its own has somewhere to go rather than an empty page."""
        client.force_login(tester)
        response = client.get(equip_url(gang))

        assert response.context["catalogue"] is None
        assert [tab["label"] for tab in response.context["collection_tabs"]] == [
            "In stash",
            "Unrestricted",
        ]
        assert "No equipment lists yet" in response.content.decode()

    def test_the_chosen_list_is_url_state(self, client, tester, gang, house_list):
        from n26.library.authoring import create_trading_post

        create_wargear("Lho Sticks", price=5, trade_point_price=1)
        post = create_trading_post()

        client.force_login(tester)
        on_house = client.get(equip_url(gang, house_list)).content.decode()
        on_post = client.get(equip_url(gang, post)).content.decode()

        assert "Knife" in on_house
        assert "Lho Sticks" not in on_house
        assert "Lho Sticks" in on_post


class TestBuyingIntoTheStash:
    """A purchase here belongs to the gang, not to anybody on the roster."""

    def test_a_buy_lands_in_the_stash_at_the_servers_price(
        self, client, tester, gang, house_list
    ):
        from n26.core.reconcile import assert_reconciled
        from n26.library.models import Wargear

        sword = Wargear.objects.get(name="Sword")
        client.force_login(tester)
        response = client.post(equip_url(gang, house_list), {"thing": key_of(sword)})
        assert response.status_code == 302

        bought = Assignment.objects.get(wargear=sword)
        assert bought.stash == gang.stash
        assert bought.miniature is None
        gang.refresh_from_db()
        # The list's override, not the wargear's 20 — the pricing seam.
        assert gang.credits == 965
        assert_reconciled(gang)

    def test_the_stash_is_worth_it_and_the_roster_is_not(
        self, client, tester, gang, house_list
    ):
        """Rating is what the models are worth; stashed gear counts in
        wealth instead."""
        from n26.core.reconcile import assert_reconciled
        from n26.library.models import Wargear

        client.force_login(tester)
        client.post(
            equip_url(gang, house_list),
            {"thing": key_of(Wargear.objects.get(name="Sword"))},
        )

        gang.refresh_from_db()
        gang.stash.refresh_from_db()
        assert gang.rating == 0
        assert gang.stash.rating == 35
        assert gang.wealth == 965 + 35
        assert_reconciled(gang)

    def test_the_confirmation_says_where_it_went(
        self, client, tester, gang, house_list
    ):
        from n26.library.models import Wargear

        client.force_login(tester)
        response = client.post(
            equip_url(gang, house_list),
            {"thing": key_of(Wargear.objects.get(name="Knife"))},
            follow=True,
        )

        assert "Bought Knife for the stash — 10¢." in response.content.decode()

    def test_a_buy_stays_on_the_list_it_was_clicked_on(
        self, client, tester, gang, house_list
    ):
        from n26.library.models import Wargear

        client.force_login(tester)
        response = client.post(
            equip_url(gang, house_list),
            {
                "thing": key_of(Wargear.objects.get(name="Knife")),
                "section": "Wargear",
            },
        )

        assert response.status_code == 302
        assert f"list={house_list.pk}" in response.url
        assert "section=Wargear" in response.url

    def test_the_price_typed_in_is_the_price_charged(
        self, client, tester, gang, house_list
    ):
        from n26.core.models import LedgerEntry
        from n26.core.reconcile import assert_reconciled
        from n26.library.models import Wargear

        sword = Wargear.objects.get(name="Sword")
        client.force_login(tester)
        client.post(
            equip_url(gang, house_list),
            {"thing": key_of(sword), price_field(sword): "8"},
        )

        entry = LedgerEntry.objects.get(assignment__wargear=sword)
        assert (entry.paid, entry.list_price, entry.discount) == (8, 35, 27)
        gang.refresh_from_db()
        assert gang.credits == 992
        assert_reconciled(gang)

    @pytest.mark.parametrize("hostile", ["-5", "abc", "12.5", "100001"])
    def test_a_price_that_is_not_whole_credits_in_range_buys_nothing(
        self, client, tester, gang, house_list, hostile
    ):
        from n26.library.models import Wargear

        sword = Wargear.objects.get(name="Sword")
        client.force_login(tester)
        response = client.post(
            equip_url(gang, house_list),
            {"thing": key_of(sword), price_field(sword): hostile},
        )

        assert response.status_code == 302
        assert not Assignment.objects.filter(wargear=sword).exists()
        gang.refresh_from_db()
        assert gang.credits == 1000

    def test_a_thing_not_on_the_list_is_refused(self, client, tester, gang, house_list):
        """A purchase only accepts lines the browse produced."""
        stray = create_wargear("Contraband", price=5)

        client.force_login(tester)
        response = client.post(equip_url(gang, house_list), {"thing": key_of(stray)})

        assert response.status_code == 302
        assert not Assignment.objects.filter(wargear=stray).exists()
        gang.refresh_from_db()
        assert gang.credits == 1000

    def test_an_overspend_refuses_and_writes_nothing(
        self, client, tester, gang, house_list
    ):
        dear = create_wargear("Archeotech", price=5000)
        house_list.entries.create(wargear=dear)

        client.force_login(tester)
        response = client.post(equip_url(gang, house_list), {"thing": key_of(dear)})

        assert response.status_code == 302
        assert not Assignment.objects.filter(wargear=dear).exists()
        gang.refresh_from_db()
        assert gang.credits == 1000


class TestOptionsTravelWithThePurchase:
    """A thing bought with a swap is a dearer thing, not a discounted one —
    and what it comes with is caused by the purchase, so it sits in the
    stash beside it."""

    @pytest.fixture
    def mount(self, gang, tester, default_pack):
        """Comes with grenade launchers and swaps them for plasma guns,
        fifteen dearer. No built-ins: nothing is ever replaced, so "comes
        with X, may replace X with Y" is a pick-one set headed by X."""
        cutter = create_wargear("Escher Cutter", price=120)
        for name, price in [
            ("Cutter grenade launchers", 0),
            ("Cutter plasma guns", 15),
        ]:
            offer_option(
                cutter,
                name,
                price=price,
                thing=create_weapon(name, profiles=[("Standard", 0)]),
            )
        create_option_group(cutter, "Hull fittings", choose="one")
        collection = create_collection("Motor Pool", entries=[cutter])
        with operation(gang, actor=tester) as op:
            op.assign(collection, gang=gang)
        return cutter, collection

    def test_with_nothing_picked_the_standard_option_arrives(
        self, client, tester, gang, mount
    ):
        from n26.core.reconcile import assert_reconciled

        cutter, collection = mount
        client.force_login(tester)
        client.post(equip_url(gang, collection), {"thing": key_of(cutter)})

        bought = Assignment.objects.get(wargear=cutter)
        assert bought.stash == gang.stash
        launchers = Assignment.objects.get(weapon__name="Cutter grenade launchers")
        assert launchers.stash == gang.stash
        assert launchers.caused_by == bought
        gang.refresh_from_db()
        assert gang.credits == 880
        assert_reconciled(gang)

    def test_a_picked_option_is_charged_and_owned(self, client, tester, gang, mount):
        """The surcharge lands on both figures: a mount with plasma guns is
        a dearer mount, not a discounted one."""
        from n26.core.models import LedgerEntry
        from n26.core.reconcile import assert_reconciled

        cutter, collection = mount
        client.force_login(tester)
        client.post(
            equip_url(gang, collection),
            {"thing": key_of(cutter), choice_field(cutter, 0): "1"},
        )

        assert Assignment.objects.filter(weapon__name="Cutter plasma guns").exists()
        assert not Assignment.objects.filter(
            weapon__name="Cutter grenade launchers"
        ).exists()
        entry = LedgerEntry.objects.get(assignment__wargear=cutter)
        assert (entry.paid, entry.list_price, entry.rating_contribution) == (
            135,
            135,
            135,
        )
        gang.refresh_from_db()
        assert gang.credits == 865
        assert_reconciled(gang)

    def test_an_option_the_listing_does_not_offer_is_a_broken_link(
        self, client, tester, gang, mount
    ):
        cutter, collection = mount
        client.force_login(tester)
        response = client.post(
            equip_url(gang, collection),
            {"thing": key_of(cutter), choice_field(cutter, 0): "7"},
        )

        assert response.status_code == 404
        assert not Assignment.objects.filter(wargear=cutter).exists()


class TestNothingSaysWhoMayUseIt:
    """A use restriction is about a model, and the stash is not one."""

    def test_a_restricted_line_draws_no_note(self, client, tester, gang):
        walker = create_subtype("Walker")
        harness = create_wargear("Grav-harness", price=25, usable_by_subtypes=[walker])
        collection = create_collection("House List", entries=[harness])
        with operation(gang, actor=tester) as op:
            op.assign(collection, gang=gang)

        client.force_login(tester)
        response = client.get(equip_url(gang, collection))
        row = next(
            row
            for row in response.context["catalogue"].all_rows()
            if row.name == "Grav-harness"
        )

        assert row.notes == ()
        assert "Walker only" not in response.content.decode()


class TestTheRail:
    def test_it_says_where_a_clicked_tabs_page_will_land(
        self, client, tester, gang, house_list
    ):
        """The same wait as a fighter's screen: on the catalogue, not the
        tab."""
        client.force_login(tester)
        html = client.get(equip_url(gang)).content.decode()

        assert 'data-busy-replaces="#equip-catalogue"' in html
        assert 'id="equip-catalogue"' in html
        assert "<template data-busy-wait>" in html


class TestTheLibraryTab:
    """Everything a list could sell, for the thing no list carries."""

    @pytest.fixture
    def library(self, default_pack):
        """Gear of each kind a collection can hold, homed so the tab has
        headings to file them under."""
        from n26.library.authoring import add_weapon_profile, create_category

        wargear = create_category("Gear", "Wargear", 0)
        guns = create_category("Gear", "Pistols", 1)
        create_wargear("Mesh Armour", price=15, category=wargear)
        autogun = create_weapon("Autogun", price=20, profiles=[("", 0)], category=guns)
        add_weapon_profile(autogun, name="warp round", price=10)
        return autogun

    def test_it_is_not_built_until_the_address_asks_for_it(
        self, client, tester, gang, house_list, library
    ):
        """It prices the library, which is not something to pay for on
        every visit — so the gang's own list is what a bare address draws."""
        client.force_login(tester)
        body = client.get(equip_url(gang)).content.decode()

        assert "Knife" in body
        assert "Mesh Armour" not in body

    def test_it_draws_the_library_under_its_own_headings(
        self, client, tester, gang, house_list, library
    ):
        client.force_login(tester)
        response = client.get(equip_url(gang, scope="all"))
        catalogue = response.context["catalogue"]

        drawn = {
            category.name: [row.name for row in category.rows]
            for section in catalogue.sections
            for category in section.categories
        }
        assert drawn["Wargear"] == ["Mesh Armour"]
        assert drawn["Pistols"] == ["Autogun"]
        # Gear the content gave no home keeps an unnamed category, drawn
        # straight inside its section — and a list the gang holds is in
        # the library too, because everything is.
        assert sorted(drawn[""]) == ["Knife", "Sword"]

    def test_a_guns_paid_rounds_ride_under_it(self, client, tester, gang, library):
        """A firing line names one particular weapon and is bought onto it,
        so it is drawn under the gun rather than as a row of its own."""
        client.force_login(tester)
        catalogue = client.get(equip_url(gang, scope="all")).context["catalogue"]
        rows = {row.name: row for row in catalogue.all_rows()}

        assert "warp round" not in rows
        assert [option.name for option in rows["Autogun"].options] == ["warp round"]

    def test_buying_from_it_lands_in_the_stash(self, client, tester, gang, library):
        from n26.core.reconcile import assert_reconciled
        from n26.library.models import Wargear

        armour = Wargear.objects.get(name="Mesh Armour")
        client.force_login(tester)
        response = client.post(equip_url(gang, scope="all"), {"thing": key_of(armour)})

        assert response.status_code == 302
        assert response.url.endswith("?list=all")
        assert Assignment.objects.get(wargear=armour).stash == gang.stash
        gang.refresh_from_db()
        assert gang.credits == 985
        assert_reconciled(gang)

    def test_another_packs_gear_is_not_in_it(
        self, client, tester, gang, library, homebrew
    ):
        """A discovery surface offers what a reader may newly pick: the
        standard pack's content, the same question the accessory picker
        asks."""
        create_wargear("Bootleg Stimms", price=5, pack=homebrew)

        client.force_login(tester)
        body = client.get(equip_url(gang, scope="all")).content.decode()

        assert "Bootleg Stimms" not in body


class TestWhoMayReadIt:
    def test_another_owners_gang_is_not_found(self, client, tester, gang_type):
        """Scoped to the reader's own gangs: whose gangs exist is not
        something to be probed for, so a stranger's is a 404."""
        stranger = User.objects.create_user("stranger")
        theirs = Gang.objects.create(
            name="Their Gang", owner=stranger, gang_type=gang_type
        )

        client.force_login(tester)
        assert client.get(equip_url(theirs)).status_code == 404

    def test_a_pk_that_is_not_a_ulid_is_not_found(self, client, tester):
        client.force_login(tester)
        assert client.get(reverse("n26-equip-gang", args=["nonsense"])).status_code == (
            404
        )

    def test_a_signed_out_reader_is_sent_to_sign_in(self, client, gang):
        response = client.get(equip_url(gang))

        assert response.status_code == 302
        assert "/accounts/login/" in response.url


class TestTheQueryBudget:
    """A catalogue is hundreds of rows, and a query per row is how a page
    stops loading. Both counts are pinned so they change deliberately.

    Each is measured after one warm request. The first request of a
    session writes its own row and reads the site, so measuring it would
    pin the session machinery alongside the page.
    """

    def measure(self, client, url):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        assert client.get(url).status_code == 200
        with CaptureQueriesContext(connection) as captured:
            assert client.get(url).status_code == 200
        return len(captured.captured_queries)

    def test_the_gangs_own_list_costs_a_fixed_number(
        self, client, tester, gang, house_list
    ):
        client.force_login(tester)

        # The reader and their session, the gang, its card — two
        # assignment queries and one hydration pass per kind they name — the
        # roster behind the header's count, which of its lists hold gear, and
        # the browse of the one chosen with its entries, their use lists and
        # their offers. The drawer asks once whether campaigns are open to
        # this reader, so it draws that place as a link or as a plain word.
        # The page's own furniture answers for the rest.
        #
        # No Visit Trading Post action is open here, which is a column read
        # and no query: what a visit has left is only asked of the ledger
        # where there is a visit to ask about.
        assert self.measure(client, equip_url(gang, house_list)) == 37

    def test_the_library_costs_a_fixed_number(self, client, tester, gang, house_list):
        create_wargear("Mesh Armour", price=15)
        create_weapon("Autogun", price=20, profiles=[("", 0)])

        client.force_login(tester)

        # The same page with the library beside that browse: one query
        # per gear kind, plus the guns' paid rounds and the wargear's
        # offers — never one per item, and no use lists, because a gang has
        # nothing to test a restriction against — and the browse of each
        # list held, which prices the library's lines. Plus the drawer's
        # one question about whether campaigns are open.
        assert self.measure(client, equip_url(gang, scope="all")) == 42

    def test_the_library_costs_the_same_however_much_it_holds(
        self, client, tester, gang, house_list
    ):
        create_wargear("Mesh Armour", price=15)
        create_weapon("Autogun", price=20, profiles=[("", 0)])
        client.force_login(tester)
        url = equip_url(gang, scope="all")

        few = self.measure(client, url)
        for index in range(5):
            create_wargear(f"Filler {index}", price=5)
            create_weapon(f"Filler gun {index}", price=5, profiles=[("", 0)])
        assert self.measure(client, url) == few


class TestStashManagement:
    """Held gear is manageable on the gang equip page, including orphans."""

    def test_the_page_is_called_equip(self, client, tester, gang, house_list):
        client.force_login(tester)
        body = client.get(equip_url(gang, house_list)).content.decode()

        assert ">Equip</h1>" in body
        assert "Buy Equipment" not in body

    def test_the_search_box_does_not_buy_on_enter(
        self, client, tester, gang, house_list
    ):
        """The bar narrows rows already on the page, as you type. Enter
        would otherwise submit the Buy form and buy the first listed
        item into the stash."""
        client.force_login(tester)
        body = client.get(equip_url(gang, house_list)).content.decode()
        assert 'role="search"' in body
        assert "@keydown.enter.prevent" in body

    def test_a_held_item_on_the_browsed_list_draws_in_stash(
        self, client, tester, gang, house_list
    ):
        from n26.library.models import Wargear

        knife = Wargear.objects.get(name="Knife")
        with operation(gang, actor=tester) as op:
            bought = op.buy(gang.stash, thing=knife, paid=10)

        client.force_login(tester)
        body = client.get(equip_url(gang, house_list)).content.decode()

        assert "in stash" in body
        assert f"sell={bought.pk}" in body

    def test_gear_the_list_does_not_sell_is_on_the_stash_tab(
        self, client, tester, gang, house_list
    ):
        from n26.library.authoring import create_weapon

        autogun = create_weapon("Autogun", price=20, profiles=[("", 0)])
        with operation(gang, actor=tester) as op:
            bought = op.buy(gang.stash, thing=autogun, paid=20)

        client.force_login(tester)
        on_house = client.get(equip_url(gang, house_list))
        on_stash = client.get(
            f"{equip_url(gang, scope='stash')}&owned={key_of(autogun)}"
        )
        body = on_stash.content.decode()

        assert "Autogun" not in {
            row.name for row in on_house.context["catalogue"].all_rows()
        }
        assert on_stash.context["stash_tab"] is True
        (row,) = on_stash.context["catalogue"].all_rows()
        assert row.expanded is True
        assert "Autogun" in body
        assert f"sell={bought.pk}" in body
        assert 'aria-expanded="true"' in body
        assert '@click="expanded = !expanded"' not in body
        sell = body.index(f"sell={bought.pk}")
        assert body.rfind("<template", 0, sell) <= body.rfind("</template>", 0, sell)

    def test_selling_from_the_stash_tab_returns_to_it(
        self, client, tester, gang, house_list
    ):
        from n26.library.models import Wargear

        knife = Wargear.objects.get(name="Knife")
        with operation(gang, actor=tester) as op:
            bought = op.buy(gang.stash, thing=knife, paid=10)

        client.force_login(tester)
        response = client.post(
            reverse("n26-sell", args=[bought.pk]),
            {"return": equip_url(gang, scope="stash")},
        )

        assert response.status_code == 302
        assert response["Location"] == equip_url(gang, scope="stash")


class TestBuyingIntoTheStashWithoutRebuildingThePage:
    """The gang's page answers a Buy the way a fighter's does: with the
    row that changed, and nothing else."""

    def test_the_answer_is_the_stash_row_and_not_a_redirect(
        self, client, tester, gang, house_list
    ):
        from django.utils.text import slugify

        from n26.library.models import Wargear

        knife = Wargear.objects.get(name="Knife")
        client.force_login(tester)
        response = client.post(
            equip_url(gang, house_list),
            {"thing": key_of(knife)},
            headers={"HX-Request": "true"},
        )

        assert response.status_code == 200
        body = response.content.decode()
        assert f'id="n26-row-{slugify(key_of(knife))}"' in body
        assert "<html" not in body
        # What the gang holds sits in the stash, and the row says so
        # rather than calling it equipped.
        assert "in stash" in body

    def test_a_plain_buy_still_answers_with_the_whole_page(
        self, client, tester, gang, house_list
    ):
        from n26.library.models import Wargear

        client.force_login(tester)
        response = client.post(
            equip_url(gang, house_list),
            {"thing": key_of(Wargear.objects.get(name="Knife"))},
        )
        assert response.status_code == 302
