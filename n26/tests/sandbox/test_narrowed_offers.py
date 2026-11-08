"""Collection-entry restrictions apply only to that collection's offer.

Another list can offer the same item without inheriting the entry restriction.
Item-wide restrictions apply wherever the item appears. Evaluate both and
show failures as notes while leaving purchases available.
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
    """Return a named collection line with use notes for this model."""
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
    """Create two profile entries so only one matches the collection restriction."""
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
    """Create one collection entry restricted to the Forge-born profile."""
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
        """Do not apply one collection's entry restriction to another collection."""
        bruiser = hire_with_option(gang, ranks["bruiser"], "Krug")

        assert line_for(cult_list, bruiser, "Heavy rock saw").notes == ()

    def test_the_saw_itself_is_left_open(self, goliath_list, saw):
        """Entry restrictions must not mutate the shared item's use restrictions."""
        assert saw.usable_by_words() == ""
        assert str(saw.usable_by_selector()) == "anything"

    def test_the_line_is_marked_and_still_bought(self, gang, ranks, goliath_list):
        """Allow a purchase with restriction notes and preserve ledger totals."""
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
        """Restrict the shared saw to Mounted models and this entry to Forge-born profiles."""
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
        """Matching the entry restriction does not bypass the item restriction."""
        forge_born = hire_with_option(gang, ranks["forge_born"], "Slag")

        (note,) = line_for(narrowed_both_ways, forge_born, "Heavy rock saw").notes

        assert note.text == "usable by Mounted only"

    def test_satisfying_the_item_leaves_only_the_lists_word(
        self, gang, ranks, person_type, saw, goliath_list
    ):
        """Show only the entry restriction when the model satisfies the item restriction."""
        restrict_use(saw, person_type)
        bruiser = hire_with_option(gang, ranks["bruiser"], "Krug")

        notes = line_for(goliath_list, bruiser, "Heavy rock saw").notes

        assert [note.text for note in notes] == [
            "this list offers it to Goliath Forge-born only"
        ]


class TestASweptLineHasNoOffer:
    """Sweeps have no entry-specific restrictions and retain ordinary reference pricing."""

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
        """Apply item restrictions to swept lines even though they have no entry restrictions."""
        restrict_use(saw, create_subtype("Mounted"))
        bruiser = hire_with_option(gang, ranks["bruiser"], "Krug")

        (note,) = line_for(everything, bruiser, "Heavy rock saw").notes

        assert note.text == "usable by Mounted only"


class TestWhatAnEntryOfThisCollectionAsks:
    """Use entry_asks for both entry forms and definition tables so their fields agree."""

    def test_a_list_asks_for_its_prices_and_who_it_offers_to(self, db):
        equipment_list = create_collection("Goliath Equipment List")

        assert equipment_list.entry_asks() == (
            "price_override",
            "trade_point_override",
            "usable_by_profile_types",
            "usable_by_subtypes",
            "usable_by_profiles",
        )

    def test_a_menu_asks_for_nothing_but_the_item(self, db):
        """Non-pricing menus expose no entry overrides; the offering modifier controls their recipients."""
        menu = create_collection("Corruptions", prices_its_entries=False)

        assert menu.entry_asks() == ()

    def test_the_asks_are_every_extra_an_entry_can_state(self, db):
        """Keep the catalogue's entry fields aligned with the shared ENTRY_ASKS definition."""
        from n26.library.models.collection import ENTRY_ASKS

        assert set(create_collection("Catalogue").entry_asks()) == set(ENTRY_ASKS)


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


class TestTheItemsOwnBracketIsNotedOnTheCollectionPage:
    """Show item-wide restrictions separately from entry restrictions and link to the item editor."""

    def test_a_restricted_items_line_says_so_and_links_the_items_page(
        self, author, saw, ranks, cult_list
    ):
        restrict_use(saw, ranks["forge_born"])

        body = author.get(f"/n26/authoring/collection/{cult_list.pk}/").content.decode()

        assert "The item itself is usable by Goliath Forge-born only" in body
        assert "Change this on the item" in body
        assert f"/n26/authoring/weapon/{saw.pk}/" in body

    def test_an_open_items_line_carries_no_such_note(self, author, cult_list):
        body = author.get(f"/n26/authoring/collection/{cult_list.pk}/").content.decode()

        assert "The item itself is usable by" not in body

    def test_the_lists_own_narrowing_and_the_items_are_told_apart(
        self, author, saw, ranks, goliath_list
    ):
        restrict_use(saw, ranks["bruiser"])

        body = author.get(
            f"/n26/authoring/collection/{goliath_list.pk}/"
        ).content.decode()

        assert "offered to Goliath Forge-born only" in body
        assert "The item itself is usable by Goliath Bruiser only" in body

    def test_a_listed_rounds_note_links_the_rounds_own_page(self, author, ranks):
        from n26.library.authoring import add_weapon_profile

        launcher = create_weapon(
            "Assault grenade launcher",
            profiles=[("", 0)],
            price=65,
            category=create_category("Ranged", "Grenade launchers"),
        )
        krak = add_weapon_profile(launcher, name="krak grenades", price=30)
        restrict_use(krak, ranks["forge_born"])
        listing = create_collection("Rounds", entries=[krak])

        body = author.get(f"/n26/authoring/collection/{listing.pk}/").content.decode()

        assert "The item itself is usable by Goliath Forge-born only" in body
        assert f"/n26/authoring/weapon-profiles/{krak.pk}/" in body

    def test_noting_the_items_adds_no_queries_as_a_list_grows(self, author, ranks):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from n26.tests.sandbox.actions import create_wargear

        def listing_of(size):
            listing = create_collection(f"List of {size}")
            for index in range(size):
                item = create_wargear(f"Gear {size}-{index}", price=10)
                restrict_use(item, ranks["forge_born"])
                add_entry(listing, item)
            return listing

        def queries_for(listing):
            with CaptureQueriesContext(connection) as captured:
                body = author.get(
                    f"/n26/authoring/collection/{listing.pk}/"
                ).content.decode()
            return len(captured), body

        # Warm the session before measuring query growth.
        small_listing = listing_of(3)
        queries_for(small_listing)
        small, _ = queries_for(small_listing)
        large, body = queries_for(listing_of(12))

        assert body.count("The item itself is usable by Goliath Forge-born only") == 12
        assert large == small


class TestAnEntryIsEditedOnItsOwnPage:
    """Edit an entry's price and recipient restrictions without replacing the listed item."""

    def entry_of(self, listing):
        from n26.library.models import CollectionEntry

        return CollectionEntry.objects.get(collection=listing)

    def test_the_definition_offers_to_edit_each_line(self, author, goliath_list):
        entry = self.entry_of(goliath_list)

        body = author.get(
            f"/n26/authoring/collection/{goliath_list.pk}/"
        ).content.decode()

        assert f"/n26/authoring/entries/{entry.pk}/edit/" in body

    def test_the_page_opens_with_what_is_there_already_chosen(
        self, author, saw, ranks, goliath_list
    ):
        import re

        entry = self.entry_of(goliath_list)
        entry.price_override = 75
        entry.save()

        body = author.get(f"/n26/authoring/entries/{entry.pk}/edit/").content.decode()

        assert "Heavy rock saw in Goliath Equipment List" in body
        assert re.search(rf'value="{ranks["forge_born"].pk}"\s+selected', body)
        assert not re.search(rf'value="{ranks["bruiser"].pk}"\s+selected', body)
        assert 'value="75"' in body
        # The thing listed is the entry's identity, not a field.
        assert 'name="edit-thing_kind"' not in body
        assert 'name="edit-thing_weapon"' not in body

    def test_saving_replaces_the_narrowing_and_the_price(
        self, author, saw, ranks, goliath_list
    ):
        entry = self.entry_of(goliath_list)

        saved = author.post(
            f"/n26/authoring/entries/{entry.pk}/edit/",
            {
                "edit-price_override": "75",
                "edit-usable_by_profiles": [str(ranks["bruiser"].pk)],
            },
        )

        assert saved.status_code == 302
        assert saved["Location"] == f"/n26/authoring/collection/{goliath_list.pk}/"
        entry.refresh_from_db()
        assert entry.price_override == 75
        assert entry.usable_by_words() == "Goliath Bruiser"
        # The saw itself is untouched, wherever else it is offered.
        assert saw.usable_by_words() == ""

    def test_clearing_the_boxes_opens_the_line_at_reference_price(
        self, author, saw, ranks, goliath_list
    ):
        entry = self.entry_of(goliath_list)
        entry.price_override = 75
        entry.save()

        author.post(f"/n26/authoring/entries/{entry.pk}/edit/", {})

        entry.refresh_from_db()
        assert entry.price_override is None
        assert entry.usable_by_words() == ""
        assert entry.price.credits == 90

    def test_a_fighter_priced_below_nothing_is_refused_in_words(self, author, ranks):
        listing = create_collection("Hired guns")
        add_entry(listing, ranks["bruiser"])
        entry = self.entry_of(listing)

        refused = author.post(
            f"/n26/authoring/entries/{entry.pk}/edit/",
            {"edit-price_override": "-5"},
        )

        assert refused.status_code == 200
        assert refused.content.decode().count("cannot be below zero") == 1
        entry.refresh_from_db()
        assert entry.price_override is None

    def test_a_refusal_about_the_whole_submission_is_printed_once(
        self, author, saw, goliath_list, monkeypatch
    ):
        """Inject a model-wide validation error to verify the page prints non-field errors once."""
        from django.core.exceptions import ValidationError

        from n26.library.models import CollectionEntry

        def refuse(self):
            raise ValidationError("This line cannot be offered like that.")

        monkeypatch.setattr(CollectionEntry, "clean", refuse)
        entry = self.entry_of(goliath_list)

        refused = author.post(
            f"/n26/authoring/entries/{entry.pk}/edit/",
            {"edit-price_override": "75"},
        )

        assert refused.status_code == 200
        body = refused.content.decode()
        assert body.count("This line cannot be offered like that.") == 1

    def test_the_page_says_when_the_item_itself_is_restricted(
        self, author, saw, ranks, goliath_list
    ):
        restrict_use(saw, ranks["bruiser"])
        entry = self.entry_of(goliath_list)

        body = author.get(f"/n26/authoring/entries/{entry.pk}/edit/").content.decode()

        assert "The item itself is restricted" in body
        assert "usable by Goliath Bruiser only" in body
        assert f"/n26/authoring/weapon/{saw.pk}/" in body

    def test_a_menus_entry_has_nothing_to_edit(self, author, saw):
        menu = create_collection("A menu", prices_its_entries=False, entries=[saw])
        entry = self.entry_of(menu)

        body = author.get(f"/n26/authoring/collection/{menu.pk}/").content.decode()
        sent_back = author.get(f"/n26/authoring/entries/{entry.pk}/edit/")

        assert f"/n26/authoring/entries/{entry.pk}/edit/" not in body
        assert sent_back.status_code == 302
        assert sent_back["Location"] == f"/n26/authoring/collection/{menu.pk}/"

    def test_only_staff_may_reach_it(self, client, saw, goliath_list):
        entry = self.entry_of(goliath_list)

        assert client.get(f"/n26/authoring/entries/{entry.pk}/edit/").status_code in (
            302,
            403,
        )


class TestTheItemsOwnBracketIsTypedOnItsPage:
    """Create and edit item-wide use restrictions on the item's own authoring page."""

    def test_the_create_page_asks_who_may_use_it(self, author):
        body = author.get("/n26/authoring/weapon/new/").content.decode()

        # Label profile restrictions as fighter entries to distinguish them from weapon profiles.
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
        """Replace the submitted multi-select set so removed recipients no longer remain allowed."""
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
        """Expose the same use-restriction fields when creating skills."""
        from n26.library.models import Skill

        walker = create_subtype("Walker")

        made = author.post(
            "/n26/authoring/skill/new/",
            {"name": "Mounted Charge", "usable_by_subtypes": [str(walker.pk)]},
        )

        assert made.status_code == 302
        assert Skill.objects.get(name="Mounted Charge").usable_by_words() == "Walker"

    def test_what_is_typed_reaches_a_buyer(self, author, gang, ranks, saw):
        """Show the saved item restriction when a model browses a collection containing it."""
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
    """restrict_use adds allowed recipients; set_usable_by replaces each supplied recipient set."""

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
        """Leave recipient sets unchanged when set_usable_by omits their arguments."""
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
    """Resolve a spec's created model from its model field or identity source."""
    if spec.model is not None:
        return spec.model
    named = spec.fields.get(spec.identity)
    return named.source[0] if named is not None and named.source else None


def restricting_verbs():
    """Discover names of authoring verbs that create models with use restrictions.

    Return stable names because spec function representations differ across workers.
    """
    from n26.library.models.assignable import UsableBy
    from n26.library.specs import specs

    return sorted(
        name
        for name, spec in specs().items()
        if isinstance(_makes(spec), type) and issubclass(_makes(spec), UsableBy)
    )


class TestEveryKindThatRestrictsUseAsksForIt:
    """Require forms for every discovered use-restricted kind to expose all recipient sets."""

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
        """Declare the replacement verb on every editable recipient-set field."""
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
        """Load entry restrictions with the listing so adding restricted entries adds no queries."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        bruiser = hire_with_option(gang, ranks["bruiser"], "Krug")
        buyer = usability_for(computed_for(bruiser))

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
                noted = with_use_notes(browse(collection), buyer)
                lines = list(noted.all_lines())
                assert lines and all(line.notes for line in lines)
            return len(captured.captured_queries)

        assert measure(narrowed(2)) == measure(narrowed(12))


class TestANamedProfileCanBeNarrowedOnItsOwn:
    """Apply a weapon profile's restriction independently of its unrestricted parent weapon."""

    @pytest.fixture
    def launcher(self, default_pack):
        from n26.library.authoring import add_weapon_profile

        weapon = create_weapon(
            "Assault grenade launcher",
            profiles=[("", 0)],
            price=65,
            category=create_category("Ranged", "Grenade launchers"),
        )
        add_weapon_profile(weapon, name="krak grenades", price=30)
        return weapon

    @pytest.fixture
    def krak(self, launcher):
        from n26.library.models import WeaponProfile

        return WeaponProfile.objects.get(weapon=launcher, name="krak grenades")

    def test_the_round_under_the_gun_carries_its_own_note(
        self, gang, ranks, launcher, krak
    ):
        listing = create_collection("Goliath Equipment List", entries=[launcher, krak])
        restrict_use(krak, ranks["forge_born"])
        bruiser = hire_with_option(gang, ranks["bruiser"], "Krug")

        line = line_for(listing, bruiser, "Assault grenade launcher")

        assert line.notes == ()
        (part,) = line.parts
        assert [note.text for note in part.notes] == [
            "usable by Goliath Forge-born only"
        ]

    def test_the_named_rank_hears_nothing(self, gang, ranks, launcher, krak):
        listing = create_collection("Goliath Equipment List", entries=[launcher, krak])
        restrict_use(krak, ranks["forge_born"])
        forge_born = hire_with_option(gang, ranks["forge_born"], "Slag")

        (part,) = line_for(listing, forge_born, "Assault grenade launcher").parts

        assert part.notes == ()

    def test_noting_a_narrowed_round_costs_no_query_per_line(
        self, gang, ranks, launcher, krak
    ):
        """Load weapon-profile restrictions with the listing rather than querying per round."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        bruiser = hire_with_option(gang, ranks["bruiser"], "Krug")
        buyer = usability_for(computed_for(bruiser))

        def narrowed(count):
            from n26.library.authoring import add_weapon_profile

            listing = create_collection(f"List of {count}")
            for index in range(count):
                weapon = create_weapon(f"Launcher {count}-{index}", profiles=[("", 0)])
                round_ = add_weapon_profile(weapon, name="krak", price=30)
                restrict_use(round_, ranks["forge_born"])
                add_entry(listing, weapon)
                add_entry(listing, round_)
            return listing

        def measure(collection):
            with CaptureQueriesContext(connection) as captured:
                noted = with_use_notes(browse(collection), buyer)
                parts = [part for line in noted.all_lines() for part in line.parts]
                assert parts and all(part.notes for part in parts)
            return len(captured.captured_queries)

        assert measure(narrowed(2)) == measure(narrowed(12))
