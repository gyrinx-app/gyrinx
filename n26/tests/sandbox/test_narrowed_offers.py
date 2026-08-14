"""A list that offers one of its lines to only some fighters.

The books restrict lines per list. A Goliath equipment list prints "Heavy
rock saw (Forge-born only)"; the Genestealer Cults and Corpse Grinder
Cults lists offer the same saw to anyone. So the restriction is a fact
about the *offer* and not about the saw, and it lives on the collection's
entry.

What a player saw when it lived on the saw instead: a Corpse Grinder
browsing their own equipment list found the rock saw marked "usable by
Goliath Forge-born only" — a restriction their book never prints.

The item's own restriction is the other fact, and stays: a saddle no
model without a mount can use is true wherever the saddle is offered. A
fighter must satisfy both, and failing either is noted, never refused.
"""

import pytest
from django.contrib.auth.models import User

from n26.core.browse import browse, usability_for, with_use_notes
from n26.core.card import build_card, build_modifier_index
from n26.core.effects import compute
from n26.core.reconcile import assert_reconciled
from n26.tests.sandbox.actions import (
    add_entry,
    buy,
    create_category,
    create_collection,
    create_subtype,
    create_weapon,
    found_gang,
    hire_with_option,
    restrict_use,
)

pytestmark = pytest.mark.django_db


def computed_for(miniature):
    card = build_card(miniature)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    return compute(card, index)


def line_for(collection, miniature, name):
    """One line of a collection as this fighter reads it, notes and all."""
    view = with_use_notes(browse(collection), usability_for(computed_for(miniature)))
    return next(line for line in view.all_lines() if line.name == name)


@pytest.fixture
def player():
    return User.objects.create_user("tom")


@pytest.fixture
def author(client, default_pack):
    """A staff client, for the tests that go through the pages."""
    client.force_login(User.objects.create_user("author", is_staff=True))
    return client


@pytest.fixture
def gang(gang_type, player):
    return found_gang("The Ironhead Boys", gang_type, owner=player, budget=1000)


@pytest.fixture
def ranks(make_profile):
    """Two fighter entries of one gang: the rank the book names in the
    bracket, and one it does not."""
    return {
        "forge_born": make_profile("Goliath Forge-born", price=50),
        "bruiser": make_profile("Goliath Bruiser", price=80),
    }


@pytest.fixture
def saw(db):
    return create_weapon(
        "Heavy rock saw",
        profiles=[("", 0)],
        price=90,
        category=create_category("Close combat", "Unwieldy Weapons"),
    )


@pytest.fixture
def goliath_list(saw, ranks):
    """The list that prints the bracket: one entry, narrowed."""
    listing = create_collection("Goliath Equipment List")
    restrict_use(add_entry(listing, saw), ranks["forge_born"])
    return listing


@pytest.fixture
def cult_list(saw):
    """Another gang's list, offering the same saw plainly."""
    return create_collection("Corpse Grinder Cults Equipment List", entries=[saw])


class TestOneListsOwnBracket:
    """ "(Forge-born only)" on the Goliath list, and nowhere else."""

    def test_a_fighter_of_another_rank_is_told_the_list_will_not_offer_it(
        self, gang, ranks, goliath_list, saw
    ):
        bruiser = hire_with_option(gang, ranks["bruiser"], "Krug")

        (note,) = line_for(goliath_list, bruiser, "Heavy rock saw").notes

        assert note.text == "this list offers it to Goliath Forge-born only"
        # Identity, so a surface hangs the remark on the row it is about.
        assert note.about == saw

    def test_the_rank_the_bracket_names_reads_the_line_plainly(
        self, gang, ranks, goliath_list
    ):
        forge_born = hire_with_option(gang, ranks["forge_born"], "Slag")

        assert line_for(goliath_list, forge_born, "Heavy rock saw").notes == ()

    def test_another_lists_offer_of_the_same_item_says_nothing(
        self, gang, ranks, goliath_list, cult_list
    ):
        """The bug in one test: the Goliath list's bracket must not reach
        a gang whose book offers the saw to anyone."""
        bruiser = hire_with_option(gang, ranks["bruiser"], "Krug")

        assert line_for(cult_list, bruiser, "Heavy rock saw").notes == ()

    def test_the_saw_itself_is_left_open(self, goliath_list, saw):
        """Nothing about the item changed — which is the whole point."""
        assert saw.usable_by_words() == ""
        assert str(saw.usable_by_selector()) == "anything"

    def test_the_line_is_marked_and_still_bought(self, gang, ranks, goliath_list):
        """Inform, never police: the owner may buy off-bracket, and the
        books add up afterwards."""
        bruiser = hire_with_option(gang, ranks["bruiser"], "Krug")
        line = line_for(goliath_list, bruiser, "Heavy rock saw")

        assignment = buy(bruiser, line)

        assert assignment.ledger_entry.paid == 90
        gang.refresh_from_db()
        assert gang.rating == 80 + 90
        assert_reconciled(gang)


class TestTheTwoRestrictionsCompose:
    """The item's and the list's are both true, so both are checked."""

    @pytest.fixture
    def mounted(self, db):
        return create_subtype("Mounted")

    @pytest.fixture
    def narrowed_both_ways(self, saw, mounted, ranks, goliath_list):
        """A saw only a Mounted model can wield anywhere, that this list
        offers to Forge-born alone."""
        restrict_use(saw, mounted)
        return goliath_list

    def test_a_fighter_failing_both_is_told_both(self, gang, ranks, narrowed_both_ways):
        bruiser = hire_with_option(gang, ranks["bruiser"], "Krug")

        notes = line_for(narrowed_both_ways, bruiser, "Heavy rock saw").notes

        assert [note.text for note in notes] == [
            "usable by Mounted only",
            "this list offers it to Goliath Forge-born only",
        ]

    def test_the_named_rank_still_hears_the_items_own_restriction(
        self, gang, ranks, narrowed_both_ways
    ):
        """Being on the list's bracket says nothing about being able to
        wield the thing."""
        forge_born = hire_with_option(gang, ranks["forge_born"], "Slag")

        (note,) = line_for(narrowed_both_ways, forge_born, "Heavy rock saw").notes

        assert note.text == "usable by Mounted only"

    def test_satisfying_the_item_leaves_only_the_lists_word(
        self, gang, ranks, person_type, saw, goliath_list
    ):
        """The item restricted to something everyone here is — its
        question is asked, and chosen for."""
        restrict_use(saw, person_type)
        bruiser = hire_with_option(gang, ranks["bruiser"], "Krug")

        notes = line_for(goliath_list, bruiser, "Heavy rock saw").notes

        assert [note.text for note in notes] == [
            "this list offers it to Goliath Forge-born only"
        ]


class TestASweptLineHasNoOffer:
    """A sweep has no entry, so there is nothing to narrow: what the
    criteria caught is offered to everyone at reference prices."""

    @pytest.fixture
    def everything(self, saw, goliath_list):
        from n26.library.models import Weapon

        return create_collection("Everything, swept", contains=[Weapon])

    def test_a_swept_line_carries_no_entry_and_no_note(self, gang, ranks, everything):
        bruiser = hire_with_option(gang, ranks["bruiser"], "Krug")

        line = line_for(everything, bruiser, "Heavy rock saw")

        assert line.entry is None
        assert line.notes == ()

    def test_the_items_own_restriction_still_reaches_a_swept_line(
        self, gang, ranks, saw, everything
    ):
        """Which is the difference between the two facts, in one pair of
        tests: only the item's travels."""
        restrict_use(saw, create_subtype("Mounted"))
        bruiser = hire_with_option(gang, ranks["bruiser"], "Krug")

        (note,) = line_for(everything, bruiser, "Heavy rock saw").notes

        assert note.text == "usable by Mounted only"


class TestWhatAnEntryOfThisCollectionAsks:
    """``entry_asks`` is the seam: the entry form and the page's tables
    both read it, so they cannot disagree about what an entry may say."""

    def test_a_shop_asks_for_its_prices_and_who_it_offers_to(self, db):
        shop = create_collection("Goliath Equipment List")

        assert shop.entry_asks() == (
            "price_override",
            "trade_point_override",
            "usable_by_profile_types",
            "usable_by_subtypes",
            "usable_by_profiles",
            "usable_by_specialisations",
        )

    def test_a_menu_asks_for_nothing_but_the_item(self, db):
        """A menu's entries are what a question offers rather than
        things anybody acquires: no price, and nobody to narrow to —
        which models are asked at all is the offering modifier's word."""
        menu = create_collection("Corruptions", prices_its_entries=False)

        assert menu.entry_asks() == ()

    def test_the_asks_are_every_extra_an_entry_can_state(self, db):
        """The superset a surface drops the unasked-for fields from — so
        a new ask cannot be added to one collection's form and forgotten
        on another's."""
        from n26.library.models.collection import ENTRY_ASKS

        assert set(create_collection("Shop").entry_asks()) == set(ENTRY_ASKS)


class TestNarrowingAnOfferThroughThePages:
    def test_the_entry_form_asks_who_the_list_offers_each_row_to(
        self, author, saw, goliath_list
    ):
        body = author.get(
            f"/n26/authoring/collection/{goliath_list.pk}/"
        ).content.decode()

        assert "Offered to fighter entries" in body
        assert "Offered to subtypes" in body

    def test_a_menus_entry_form_does_not(self, author, saw):
        menu = create_collection("Corruptions", prices_its_entries=False)

        body = author.get(f"/n26/authoring/collection/{menu.pk}/").content.decode()

        assert "Offered to fighter entries" not in body
        assert "Price override" not in body

    def test_listing_an_item_narrowed_writes_the_offers_own_lists(
        self, author, saw, ranks
    ):
        from n26.library.models import CollectionEntry

        listing = create_collection("Goliath Equipment List")
        page = f"/n26/authoring/collection/{listing.pk}/"

        made = author.post(
            page,
            {
                "act": "entry",
                "thing_kind": "weapon",
                "thing_weapon": str(saw.pk),
                "price_override": "90",
                "usable_by_profiles": [str(ranks["forge_born"].pk)],
            },
        )

        assert made.status_code == 302
        entry = CollectionEntry.objects.get(collection=listing)
        assert entry.price_override == 90
        assert entry.usable_by_words() == "Goliath Forge-born"
        # And the saw is untouched, wherever else it is offered.
        assert saw.usable_by_words() == ""

    def test_the_definition_says_who_each_row_is_offered_to(
        self, author, saw, goliath_list
    ):
        body = author.get(
            f"/n26/authoring/collection/{goliath_list.pk}/"
        ).content.decode()

        assert "offered to Goliath Forge-born only" in body


class TestTheItemsOwnBracketIsTypedOnItsPage:
    """The other half of the pair, and where it is written.

    "Wyld bow (Wyld Runner only)" is a fact about the bow, so its own
    page is where it is said — asked for when the bow is made and again
    whenever it is changed. Before this, the only way in was a
    spreadsheet import, which is how a fact belonging to one list came to
    be written on the item every list shares.
    """

    def test_the_create_page_asks_who_may_use_it(self, author):
        body = author.get("/n26/authoring/weapon/new/").content.decode()

        # Named for what an author is choosing, not for the column: on a
        # weapon's page "profiles" would be taken for its firing lines.
        assert "Usable by fighter entries" in body
        assert "Usable by types" in body
        assert 'name="usable_by_profiles"' in body
        assert 'name="usable_by_subtypes"' in body

    def test_making_one_writes_the_lists(self, author, ranks):
        from n26.library.models import Weapon

        walker = create_subtype("Walker")

        made = author.post(
            "/n26/authoring/weapon/new/",
            {
                "name": "Wyld bow",
                "slots": "1",
                "price": "35",
                "usable_by_profiles": [str(ranks["forge_born"].pk)],
                "usable_by_subtypes": [str(walker.pk)],
            },
        )

        assert made.status_code == 302
        bow = Weapon.objects.get(name="Wyld bow")
        assert bow.usable_by_words() == "Goliath Forge-born or Walker"

    def test_the_page_opens_with_what_is_there_already_chosen(self, author, saw, ranks):
        import re

        restrict_use(saw, ranks["forge_born"])

        body = author.get(f"/n26/authoring/weapon/{saw.pk}/").content.decode()

        assert re.search(rf'value="{ranks["forge_born"].pk}"\s+selected', body)
        # The rank the saw does not name is offered, and not chosen.
        assert not re.search(rf'value="{ranks["bruiser"].pk}"\s+selected', body)

    def test_editing_replaces_the_list_rather_than_adding_to_it(
        self, author, saw, ranks
    ):
        """A multi-select carries the whole answer, so a rank it stops
        naming stops being named. Added to instead, a restriction typed
        once could never be corrected."""
        restrict_use(saw, ranks["forge_born"])

        saved = author.post(
            f"/n26/authoring/weapon/{saw.pk}/",
            {
                "act": "edit",
                "edit-name": "Heavy rock saw",
                "edit-slots": "2",
                "edit-price": "90",
                "edit-usable_by_profiles": [str(ranks["bruiser"].pk)],
            },
        )

        assert saved.status_code == 302
        saw.refresh_from_db()
        assert saw.usable_by_words() == "Goliath Bruiser"

    def test_clearing_the_lists_opens_it_to_everyone(self, author, saw, ranks):
        restrict_use(saw, ranks["forge_born"])

        author.post(
            f"/n26/authoring/weapon/{saw.pk}/",
            {
                "act": "edit",
                "edit-name": "Heavy rock saw",
                "edit-slots": "2",
                "edit-price": "90",
            },
        )

        saw.refresh_from_db()
        assert saw.usable_by_words() == ""
        assert str(saw.usable_by_selector()) == "anything"

    def test_a_skill_is_narrowed_on_its_own_page_too(self, author, ranks):
        """The bracket a skill's heading prints — "(Fighter Or Walker
        Only)" — asked for on the page that makes one, because it is the
        same question about the same four lists."""
        from n26.library.models import Skill

        walker = create_subtype("Walker")

        made = author.post(
            "/n26/authoring/skill/new/",
            {"name": "Mounted Charge", "usable_by_subtypes": [str(walker.pk)]},
        )

        assert made.status_code == 302
        assert Skill.objects.get(name="Mounted Charge").usable_by_words() == "Walker"

    def test_what_is_typed_reaches_a_shopper(self, author, gang, ranks, saw):
        """End to end: a restriction typed on the item's page is what a
        fighter browsing a list that offers it is told."""
        plain = create_collection("Trade Row", entries=[saw])
        author.post(
            f"/n26/authoring/weapon/{saw.pk}/",
            {
                "act": "edit",
                "edit-name": "Heavy rock saw",
                "edit-slots": "2",
                "edit-price": "90",
                "edit-usable_by_profiles": [str(ranks["forge_born"].pk)],
            },
        )

        bruiser = hire_with_option(gang, ranks["bruiser"], "Krug")

        (note,) = line_for(plain, bruiser, "Heavy rock saw").notes
        assert note.text == "usable by Goliath Forge-born only"


class TestSayingWhoMayUseAThing:
    """Two verbs write the four lists, and they differ in what leaving
    them out means: one adds an allowed thing, the other states the whole
    list."""

    def test_restricting_use_adds_one_at_a_time(self, saw, ranks):
        restrict_use(saw, ranks["forge_born"])
        restrict_use(saw, ranks["bruiser"])

        # Both kept, read out in the fighter entries' own order rather
        # than the order they were named.
        assert saw.usable_by_words() == "Goliath Bruiser or Goliath Forge-born"

    def test_setting_the_list_replaces_it(self, saw, ranks):
        from n26.library.authoring import set_usable_by

        restrict_use(saw, ranks["forge_born"])

        set_usable_by(saw, usable_by_profiles=[ranks["bruiser"]])

        assert saw.usable_by_words() == "Goliath Bruiser"

    def test_a_list_not_named_is_left_as_it_was(self, saw, ranks):
        """Saying nothing about an arm is not the same as emptying it: a
        form that draws one picker must not silently open the others."""
        from n26.library.authoring import set_usable_by

        walker = create_subtype("Walker")
        restrict_use(saw, walker)

        set_usable_by(saw, usable_by_profiles=[ranks["forge_born"]])

        assert saw.usable_by_words() == "Goliath Forge-born or Walker"

    def test_an_empty_list_opens_that_arm(self, saw, ranks):
        from n26.library.authoring import set_usable_by

        restrict_use(saw, ranks["forge_born"])

        set_usable_by(saw, usable_by_profiles=[])

        assert saw.usable_by_words() == ""

    def test_creating_one_restricted_takes_the_lists(self, ranks):
        walker = create_subtype("Walker")

        bow = create_weapon(
            "Wyld bow",
            price=35,
            usable_by_profiles=[ranks["forge_born"]],
            usable_by_subtypes=[walker],
        )

        assert bow.usable_by_words() == "Goliath Forge-born or Walker"


def _makes(spec):
    """The model a spec's verb writes, or None where it writes no row of
    its own — a scope or an effect verb names no model and has no name
    field to read one off."""
    if spec.model is not None:
        return spec.model
    named = spec.fields.get(spec.identity)
    return named.source[0] if named is not None and named.source else None


def restricting_verbs():
    """Every verb that writes a row carrying the four use lists, by name —
    found by reflection, so a new kind that carries them is checked the
    day it is authorable. Names rather than specs: a spec holds function
    objects, whose printed form differs between test workers."""
    from n26.library.models.assignable import UsableBy
    from n26.library.specs import specs

    return sorted(
        name
        for name, spec in specs().items()
        if isinstance(_makes(spec), type) and issubclass(_makes(spec), UsableBy)
    )


class TestEveryKindThatRestrictsUseAsksForIt:
    """A discovering guard. A kind carrying the use lists whose form does
    not ask for them can only be restricted by a spreadsheet — which is
    how a Goliath-only line came to be written on an item three gangs
    list. The form asks, so the fact can be typed where it belongs.
    """

    def test_there_is_something_to_check(self):
        assert {"create_weapon", "create_skill", "create_wargear"} <= set(
            restricting_verbs()
        )

    @pytest.mark.parametrize("name", restricting_verbs(), ids=str)
    def test_its_form_asks_for_all_four_lists(self, name):
        from n26.library.models.assignable import USABLE_BY_LISTS
        from n26.library.specs import specs

        spec = specs()[name]
        made = _makes(spec).__name__
        missing = set(USABLE_BY_LISTS) - set(spec.fields)
        assert not missing, (
            f"{made} says who may use it, but the {name} form never asks "
            f"for {sorted(missing)}. Add specs.use_lists({made}) to its "
            f"spec and the same names to the verb."
        )

    @pytest.mark.parametrize("name", restricting_verbs(), ids=str)
    def test_each_list_names_the_verb_that_replaces_it(self, name):
        """An edit form writes a set through the verb that owns it, and
        finds the verb on the spec field. Without one the page refuses
        rather than replacing a set nobody decided the meaning of."""
        from n26.library.models.assignable import USABLE_BY_LISTS
        from n26.library.specs import specs

        for field_name in USABLE_BY_LISTS:
            assert specs()[name].fields[field_name].replaced_by is not None, (
                f"{name}.{field_name} is a set an author can edit with no "
                f"verb owning its replacement — name one with replaced_by."
            )


class TestScaling:
    def test_noting_narrowed_offers_costs_no_more_queries_as_a_list_grows(
        self, gang, ranks
    ):
        """The entries' own use lists load with the listing, exactly as
        the items' do — so a list where every line is narrowed costs what
        an open one does."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        bruiser = hire_with_option(gang, ranks["bruiser"], "Krug")
        shopper = usability_for(computed_for(bruiser))

        def narrowed(count):
            listing = create_collection(f"List of {count}")
            for index in range(count):
                weapon = create_weapon(
                    f"Saw {count}-{index}", profiles=[("", 0)], price=10
                )
                restrict_use(add_entry(listing, weapon), ranks["forge_born"])
            return listing

        def measure(collection):
            with CaptureQueriesContext(connection) as captured:
                noted = with_use_notes(browse(collection), shopper)
                lines = list(noted.all_lines())
                assert lines and all(line.notes for line in lines)
            return len(captured.captured_queries)

        assert measure(narrowed(2)) == measure(narrowed(12))
