"""The screen shown after an act, for what the act brought.

An author attaches a screen to a slot. When founding a gang, hiring a
model or making a pick puts that slot on a card, the reader is shown
the screen — heading, words and the picker — before landing where they
were going. Nothing is stored: the address names every question and
where Continue leads, and the screen derives itself from it each time.

What this file pins: which acts send the reader here and which never
do; that the picker on this screen is the pick screen's own; how Skip
and Continue behave; what a broken or borrowed address does; and that
the printed sheet and the text card do not know the screen exists.
"""

from html import unescape
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from django.contrib.auth.models import User
from django.test import RequestFactory
from django.urls import reverse

from n26.core.arrivals import any_interstitials, arrived, asking, onward
from n26.core.capture import differences, gang_state
from n26.core.models import Assignment
from n26.core.operations import operation
from n26.core.owned import with_query
from n26.core.render import GANG_SLOT_HOST, render_gang
from n26.core.render_text import gang_to_text
from n26.library.authoring import (
    attach_interstitial,
    create_interstitial,
    revise,
)
from n26.tests.sandbox.actions import (
    add_built_in,
    create_pickable,
    create_picklist,
    create_profile,
    create_slot,
    create_slot_type,
    ef_adds,
    ef_removes,
    found_gang,
    hire,
    modifier,
    targets_gang,
)

pytestmark = pytest.mark.django_db

#: The edition's core package, for the guards that read its source.
CORE = Path(__file__).resolve().parents[2] / "core"


# --- A gang type whose founding asks one question ---------------------------


@pytest.fixture
def legacy(default_pack):
    return create_slot_type("Archetype", allows_repeats=False)


@pytest.fixture
def archetypes(legacy):
    return {name: create_pickable(name, legacy) for name in ("Brawler", "Gunslinger")}


@pytest.fixture
def picklist(legacy, archetypes):
    return create_picklist("Archetypes", legacy, members=list(archetypes.values()))


@pytest.fixture
def archetype_slot(legacy, picklist, gang_type):
    """The gang's own question, built into the gang type: founding
    brings it."""
    slot = create_slot("Archetype", legacy, picklist, assigned_to="gang")
    add_built_in(gang_type, slot)
    return slot


@pytest.fixture
def shown(archetype_slot):
    """The screen attached to it. Not skippable."""
    return create_interstitial(
        "Outcast archetype",
        title="Choose an archetype",
        description="The archetype shapes the whole gang. Pick one before hiring.",
        slots=[archetype_slot],
    )


@pytest.fixture
def hunter(person_type, gang_type, legacy, picklist):
    """A profile whose hire brings a question of the model's own, with a
    skippable screen on it."""
    profile = create_profile("Hunter", person_type, gang_type, price=100)
    slot = create_slot("Hunter's path", legacy, picklist)
    add_built_in(profile, slot)
    create_interstitial(
        "Hunter's path",
        description="A hunter's path can be chosen later.",
        skippable=True,
        slots=[slot],
    )
    return profile


def founding_post(gang_type, name="The Forgotten"):
    return {
        "name": name,
        "gang_type": str(gang_type.pk),
        "starting_credits": "1000",
        "colour": "",
    }


def found_through_the_page(client, owner, gang_type):
    """Found through the page that founds one: the response, and the gang."""
    from n26.core.models import Gang

    client.force_login(owner)
    response = client.post(reverse("n26-create-gang"), founding_post(gang_type))
    assert response.status_code == 302
    return response, Gang.objects.get(name="The Forgotten")


def page(client, url):
    """The page as a reader sees it: an apostrophe in a slot's label
    arrives escaped, and every assertion here is about the words."""
    return unescape(client.get(url).content.decode())


def asks_in(url):
    parts = urlsplit(url)
    query = parse_qs(parts.query)
    return parts.path, query.get("ask", []), query.get("next", [""])[0]


def sheet_slot(gang, label):
    """One question's line off the gang sheet, the gang's own or a member's."""
    sheet = render_gang(gang)
    for line in sheet.choices:
        if line.kind_label == label:
            return line
    for card in sheet.models:
        for line in card.questions:
            if line.kind_label == label:
                return line
    raise AssertionError(f"no {label!r} on the sheet")


def screen_url(gang, keys, back=None):
    from n26.core.arrivals import next_url

    return next_url(gang, keys, back or reverse("n26-gang", args=[gang.pk]))


def pick_key(pickable):
    return f"{pickable._meta.label_lower}:{pickable.pk}"


# --- Which acts send the reader here ----------------------------------------


class TestFoundingAGang:
    """Founding brings the gang type's slots. Where one carries a
    screen, the founder lands on it, not on the sheet."""

    def test_it_lands_on_the_screen_when_a_slot_carries_one(
        self, client, owner, gang_type, shown
    ):
        response, gang = found_through_the_page(client, owner, gang_type)

        path, asks, back = asks_in(response["Location"])
        assert path == reverse("n26-next", args=[gang.pk])
        assert asks == [sheet_slot(gang, "Archetype").key]
        assert back == reverse("n26-gang", args=[gang.pk])

    def test_the_screen_says_what_the_author_wrote_and_offers_the_picker(
        self, client, owner, gang_type, shown
    ):
        response, gang = found_through_the_page(client, owner, gang_type)
        body = page(client, response["Location"])

        assert "Choose an archetype" in body
        assert "The archetype shapes the whole gang." in body
        assert "Archetype" in body and "The Forgotten" in body
        assert "Brawler" in body and "Gunslinger" in body
        # The act's own confirmation draws at the top of this screen.
        assert "Founded The Forgotten." in body

    def test_no_continue_while_the_question_is_open(
        self, client, owner, gang_type, shown
    ):
        response, gang = found_through_the_page(client, owner, gang_type)
        body = page(client, response["Location"])

        assert "Choose Archetype to continue." in body
        assert (
            f'href="{reverse("n26-gang", args=[gang.pk])}"'
            not in body.split("Choose Archetype to continue.")[0].rsplit("<button", 1)[
                1
            ]
        )
        # Not skippable, so no Skip either.
        assert ">Skip<" not in body

    def test_founding_a_gang_whose_slots_carry_nothing_goes_straight_to_the_sheet(
        self, client, owner, gang_type, archetype_slot
    ):
        response, gang = found_through_the_page(client, owner, gang_type)

        assert response["Location"] == reverse("n26-gang", args=[gang.pk])

    def test_the_authors_word_never_reaches_the_player(
        self, client, owner, gang_type, shown
    ):
        response, gang = found_through_the_page(client, owner, gang_type)
        body = page(client, response["Location"])

        assert "nterstitial" not in body


class TestHiringAModel:
    """A hire brings the profile's slots and nothing else: the gang's
    standing question is not asked again."""

    @pytest.fixture
    def gang(self, owner, gang_type, shown):
        return found_gang("The Forgotten", gang_type, owner=owner, budget=1000)

    def test_a_hire_bringing_a_screen_lands_on_it(self, client, owner, gang, hunter):
        client.force_login(owner)
        response = client.post(
            reverse("n26-hire-fighter", args=[gang.pk]),
            {"profile": str(hunter.pk), "name": "Kal"},
        )

        assert response.status_code == 302
        path, asks, back = asks_in(response["Location"])
        assert path == reverse("n26-next", args=[gang.pk])
        assert asks == [sheet_slot(gang, "Hunter's path").key]
        assert back == reverse("n26-hire-fighter", args=[gang.pk])
        body = page(client, response["Location"])
        assert "Hired Kal — Hunter, 100¢." in body
        assert "Kal" in body and "Hunter's path" in body

    def test_a_hire_bringing_nothing_lands_where_it_always_did(
        self, client, owner, gang, person_type, gang_type
    ):
        plain = create_profile("Ganger", person_type, gang_type, price=50)
        client.force_login(owner)
        response = client.post(
            reverse("n26-hire-fighter", args=[gang.pk]),
            {"profile": str(plain.pk), "name": "Rat"},
        )

        assert response["Location"] == reverse("n26-hire-fighter", args=[gang.pk])

    def test_a_library_of_staged_screens_only_derives_nothing_for_an_ordinary_reader(
        self, owner, gang, hunter, shown
    ):
        """A reader who may not see staged content is spared the gang's
        derivation when every attached screen is on hold."""
        from unittest import mock

        from n26.library.models import Interstitial

        Interstitial.objects.update(staged=True)
        request = RequestFactory().get("/")
        request.user = owner
        with operation(gang, actor=owner) as op:
            op.hire(hunter, "Kal")
        with mock.patch("n26.core.arrivals.arrived") as derived:
            assert onward(request, gang, op, "/back/") == "/back/"
        derived.assert_not_called()

    def test_with_nothing_attached_in_the_library_an_act_pays_one_query(
        self, owner, gang, hunter
    ):
        """The short-circuit: a library holding no live attachment costs
        an act one query, whatever it brought."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from n26.library.models import InterstitialSlot

        InterstitialSlot.objects.all().delete()
        request = RequestFactory().get("/")
        request.user = owner
        with operation(gang, actor=owner) as op:
            op.hire(hunter, "Kal")
        with CaptureQueriesContext(connection) as captured:
            assert onward(request, gang, op, "/back/") == "/back/"
        assert len(captured) == 1


class TestWhatArrived:
    """The mechanism: a slot arrives when the assignment it hangs from
    was written by the act that just ran."""

    def test_founding_names_the_gangs_own_slot(self, owner, gang_type, archetype_slot):
        with operation(_fresh_gang(owner, gang_type), actor=owner) as op:
            op.found(gang_type)

        assert [
            (host, slot.kind_label) for host, slot in arrived(op.gang, op.written)
        ] == [(GANG_SLOT_HOST, "Archetype")]

    def test_a_hire_names_its_own_slot_and_not_the_gangs_standing_one(
        self, owner, gang_type, archetype_slot, hunter
    ):
        gang = found_gang("The Forgotten", gang_type, owner=owner, budget=1000)
        with operation(gang, actor=owner) as op:
            kal = op.hire(hunter, "Kal")

        assert [
            (host, slot.kind_label) for host, slot in arrived(gang, op.written)
        ] == [(str(kal.pk), "Hunter's path")]

    def test_a_pick_that_brings_a_slot_names_it(
        self, owner, gang_type, archetype_slot, archetypes, legacy, picklist
    ):
        """A pickable gives a further slot: the pick's own assignment is
        what the new slot hangs from, so it arrives with the pick."""
        follow_up = create_slot("Brawler's creed", legacy, picklist, assigned_to="gang")
        modifier(
            "Brawler: asks a creed",
            targets_gang(),
            ef_adds(follow_up),
            carried_by=archetypes["Brawler"],
        )
        gang = found_gang("The Forgotten", gang_type, owner=owner, budget=1000)
        anchor = sheet_slot(gang, "Archetype")
        with operation(gang, actor=owner) as op:
            op.choose(
                Assignment.objects.get(pk=anchor.key.split(":")[1]),
                archetypes["Brawler"],
                slot=archetype_slot,
            )

        assert [slot.kind_label for _, slot in arrived(gang, op.written)] == [
            "Brawler's creed"
        ]

    def test_only_slots_carrying_a_screen_are_asked_about(
        self, owner, gang_type, archetype_slot, shown
    ):
        gang = _fresh_gang(owner, gang_type)
        with operation(gang, actor=owner) as op:
            op.found(gang_type)
        assert asking(gang, op.written) == [sheet_slot(gang, "Archetype").key]

        shown.attachments.all().delete()
        assert asking(gang, op.written) == []
        assert any_interstitials() is False

    def test_an_archived_screen_still_shows_for_a_gang_holding_the_slot(
        self, owner, gang_type, archetype_slot, homebrew
    ):
        """Archiving is a pack owner's soft delete: it stops a screen
        being newly attached, never retracts one from a gang already
        holding the slot — the same rule every pack's content follows."""
        packed = create_interstitial(
            "Packed away", slots=[archetype_slot], pack=homebrew
        )
        revise(homebrew, archived=True)
        gang = _fresh_gang(owner, gang_type)
        with operation(gang, actor=owner) as op:
            op.found(gang_type)

        assert asking(gang, op.written) == [sheet_slot(gang, "Archetype").key]
        assert any_interstitials() is True

        revise(packed, archived=True)
        assert asking(gang, op.written) == [sheet_slot(gang, "Archetype").key]

    def test_a_staged_screen_is_asked_about_only_by_a_reader_who_sees_staged(
        self, owner, gang_type, archetype_slot, shown
    ):
        revise(shown, staged=True)
        gang = _fresh_gang(owner, gang_type)
        with operation(gang, actor=owner) as op:
            op.found(gang_type)

        assert asking(gang, op.written) == []
        assert asking(gang, op.written, include_staged=True) == [
            sheet_slot(gang, "Archetype").key
        ]

    def test_a_staged_attachment_keeps_its_screen_off_the_player_path(
        self, owner, gang_type, archetype_slot, shown
    ):
        """An attachment on hold — the interstitial itself live — keeps
        the screen off this slot for a reader who may not see staged
        content, and shows it to one who may."""
        revise(shown.attachments.get(), staged=True)
        gang = _fresh_gang(owner, gang_type)
        with operation(gang, actor=owner) as op:
            op.found(gang_type)

        assert asking(gang, op.written) == []
        assert asking(gang, op.written, include_staged=True) == [
            sheet_slot(gang, "Archetype").key
        ]

    def test_purchases_and_clones_never_send_the_reader_here(self):
        """The seam opts in per act: the founding, hire and pick views
        call it, and the equip and cloning views do not."""
        import inspect
        from importlib import import_module

        # By module path: the views package re-exports a view named
        # ``gangs``, which would shadow the module of the same name.
        def module(name):
            return import_module(f"n26.core.views.{name}")

        for name, view in (
            ("gangs", "create_gang"),
            ("hire", "hire_fighter"),
            # The pick view hands where a settled click lands to a helper
            # of its own, and that is where its call lives.
            ("choose", "_landing"),
        ):
            assert "onward(" in inspect.getsource(getattr(module(name), view)), view
        assert "_landing(" in inspect.getsource(module("choose").choose)
        for name in ("equip", "cloning", "options", "owned"):
            assert "onward(" not in inspect.getsource(module(name)), name


def archetype_slot_of(gang):
    """The gang type's own slot, read back off the gang."""
    from n26.library.models import Slot

    return Slot.objects.get(name="Archetype", assigned_to="gang")


def _fresh_gang(owner, gang_type):
    from n26.core.models import Gang

    return Gang.objects.create(
        name="The Forgotten",
        gang_type=gang_type,
        owner=owner,
        starting_credits=1000,
        credits=1000,
    )


# --- Picking on the screen ---------------------------------------------------


class TestPickingOnTheScreen:
    """The picker is the pick screen's own, drawn in place: a click
    writes the same pick, says the same thing, and comes back here."""

    @pytest.fixture
    def landed(self, client, owner, gang_type, shown):
        response, gang = found_through_the_page(client, owner, gang_type)
        return gang, response["Location"]

    def test_a_pick_comes_back_with_it_chosen_and_continue_offered(
        self, client, landed, archetypes
    ):
        gang, here = landed
        key = sheet_slot(gang, "Archetype").key

        response = client.post(
            here, {"ask": key, "thing": pick_key(archetypes["Brawler"])}
        )

        assert response.status_code == 302
        assert asks_in(response["Location"]) == asks_in(here)
        body = page(client, response["Location"])
        assert "Chose Brawler — Archetype." in body
        assert "Chosen: Brawler" in body
        assert f'href="{reverse("n26-gang", args=[gang.pk])}"' in body
        assert "to continue." not in body
        assert Assignment.objects.get(pickable=archetypes["Brawler"]).gang == gang

    def test_continue_leads_where_the_address_says(
        self, client, owner, landed, archetypes
    ):
        gang, _ = landed
        key = sheet_slot(gang, "Archetype").key
        elsewhere = reverse("n26-hire-fighter", args=[gang.pk])
        here = screen_url(gang, [key], back=elsewhere)
        client.post(here, {"ask": key, "thing": pick_key(archetypes["Brawler"])})

        body = page(client, here)

        assert f'href="{elsewhere}"' in body

    def test_a_thing_not_on_the_list_is_refused_in_words(self, client, landed, legacy):
        gang, here = landed
        key = sheet_slot(gang, "Archetype").key
        stranger = create_pickable("Stranger", legacy)

        response = client.post(here, {"ask": key, "thing": pick_key(stranger)})

        assert asks_in(response["Location"]) == asks_in(here)
        body = page(client, response["Location"])
        assert "That is not one of the things available to pick." in body
        assert not Assignment.objects.filter(pickable=stranger).exists()

    def test_a_question_not_on_the_screen_is_refused_in_words(
        self, client, landed, archetypes
    ):
        gang, here = landed

        response = client.post(
            here,
            {"ask": "gang:nothing:nothing", "thing": pick_key(archetypes["Brawler"])},
        )

        body = page(client, response["Location"])
        assert "That choice is no longer on this screen." in body

    def test_a_pick_on_the_pick_screen_reached_from_here_joins_the_address(
        self, client, landed, archetypes, legacy, picklist
    ):
        """Following a question to its own page — for a roll — and picking
        there lands back on this screen with what the pick brought added,
        not on a second screen in front of the first."""
        gang, here = landed
        creed = create_slot("Brawler's creed", legacy, picklist, assigned_to="gang")
        modifier(
            "Brawler: asks a creed",
            targets_gang(),
            ef_adds(creed),
            carried_by=archetypes["Brawler"],
        )
        create_interstitial("Creed", slots=[creed])
        key = sheet_slot(gang, "Archetype").key
        picker = with_query(
            reverse("n26-choose", args=[gang.pk, key]), **{"return": here}
        )

        response = client.post(
            picker, {"thing": pick_key(archetypes["Brawler"]), "return": here}
        )

        path, asks, back = asks_in(response["Location"])
        assert path == reverse("n26-next", args=[gang.pk])
        assert asks == [key, sheet_slot(gang, "Brawler's creed").key]
        assert back == reverse("n26-gang", args=[gang.pk])

    def test_a_worked_at_choice_on_the_pick_screen_still_shows_what_a_pick_brought(
        self, client, owner, gang_type, legacy, picklist, archetypes
    ):
        """A choice of several comes back to its own page after each pick,
        by way of the screen for anything that pick brought."""
        several = create_slot(
            "Paths", legacy, picklist, max_picks=2, assigned_to="gang"
        )
        add_built_in(gang_type, several)
        creed = create_slot("Brawler's creed", legacy, picklist, assigned_to="gang")
        modifier(
            "Brawler: asks a creed",
            targets_gang(),
            ef_adds(creed),
            carried_by=archetypes["Brawler"],
        )
        create_interstitial("Creed", slots=[creed])
        gang = found_gang("The Forgotten", gang_type, owner=owner, budget=1000)
        client.force_login(owner)
        picker = reverse("n26-choose", args=[gang.pk, sheet_slot(gang, "Paths").key])

        response = client.post(picker, {"thing": pick_key(archetypes["Brawler"])})

        path, asks, back = asks_in(response["Location"])
        assert path == reverse("n26-next", args=[gang.pk])
        assert asks == [sheet_slot(gang, "Brawler's creed").key]
        assert back == picker

    def test_a_worked_at_choice_opened_from_here_comes_back_here_with_what_it_brought(
        self, client, owner, gang_type, legacy, picklist, archetypes
    ):
        """A choice of several, reached from this screen for its own page,
        sends what a pick brought back to this screen rather than opening
        a second one — and with nothing brought, comes back to itself."""
        several = create_slot(
            "Paths", legacy, picklist, max_picks=2, assigned_to="gang"
        )
        add_built_in(gang_type, several)
        create_interstitial("Paths", slots=[several])
        creed = create_slot("Brawler's creed", legacy, picklist, assigned_to="gang")
        modifier(
            "Brawler: asks a creed",
            targets_gang(),
            ef_adds(creed),
            carried_by=archetypes["Brawler"],
        )
        create_interstitial("Creed", slots=[creed])
        gang = found_gang("The Forgotten", gang_type, owner=owner, budget=1000)
        client.force_login(owner)
        key = sheet_slot(gang, "Paths").key
        here = screen_url(gang, [key])
        picker = with_query(
            reverse("n26-choose", args=[gang.pk, key]), **{"return": here}
        )

        response = client.post(
            picker, {"thing": pick_key(archetypes["Gunslinger"]), "return": here}
        )
        assert response["Location"].startswith(
            reverse("n26-choose", args=[gang.pk, key])
        )

        response = client.post(
            picker, {"thing": pick_key(archetypes["Brawler"]), "return": here}
        )
        path, asks, back = asks_in(response["Location"])
        assert path == reverse("n26-next", args=[gang.pk])
        assert asks == [key, sheet_slot(gang, "Brawler's creed").key]
        assert back == reverse("n26-gang", args=[gang.pk])

    def test_a_worked_at_choice_stays_the_way_on_until_it_is_full(
        self, client, owner, gang_type, legacy, picklist, archetypes
    ):
        """From the arrival screen, a choice of several: what an early pick
        brings gets a screen whose Continue leads back to the picker for
        the rest, and only the pick that fills the choice hands what it
        brought on to the screen the reader came from."""
        several = create_slot(
            "Paths", legacy, picklist, max_picks=2, assigned_to="gang"
        )
        add_built_in(gang_type, several)
        create_interstitial("Paths", slots=[several])
        for name in ("Brawler", "Gunslinger"):
            brought = create_slot(
                f"{name}'s creed", legacy, picklist, assigned_to="gang"
            )
            modifier(
                f"{name}: asks a creed",
                targets_gang(),
                ef_adds(brought),
                carried_by=archetypes[name],
            )
            create_interstitial(f"{name}'s creed", slots=[brought])
        gang = found_gang("The Forgotten", gang_type, owner=owner, budget=1000)
        client.force_login(owner)
        key = sheet_slot(gang, "Paths").key
        arrival = screen_url(gang, [key])
        picker = with_query(
            reverse("n26-choose", args=[gang.pk, key]), **{"return": arrival}
        )

        first = client.post(
            picker, {"thing": pick_key(archetypes["Brawler"]), "return": arrival}
        )
        path, asks, back = asks_in(first["Location"])
        assert path == reverse("n26-next", args=[gang.pk])
        assert asks == [sheet_slot(gang, "Brawler's creed").key]
        assert back == picker

        second = client.post(
            picker, {"thing": pick_key(archetypes["Gunslinger"]), "return": arrival}
        )
        path, asks, back = asks_in(second["Location"])
        assert path == reverse("n26-next", args=[gang.pk])
        assert asks == [key, sheet_slot(gang, "Gunslinger's creed").key]
        assert back == reverse("n26-gang", args=[gang.pk])

    def test_a_pick_that_takes_its_own_question_away_still_lands(
        self, client, owner, gang_type, legacy, picklist, archetypes
    ):
        """A choice of several whose pick removes the very slot being
        answered, and brings a screen: nothing is left to work at, so
        what the pick brought joins the screen the reader came from
        rather than the click failing after the pick was written."""
        several = create_slot(
            "Paths", legacy, picklist, max_picks=2, assigned_to="gang"
        )
        add_built_in(gang_type, several)
        create_interstitial("Paths", slots=[several])
        creed = create_slot("Brawler's creed", legacy, picklist, assigned_to="gang")
        modifier(
            "Brawler: one path only",
            targets_gang(),
            ef_removes(several),
            carried_by=archetypes["Brawler"],
        )
        modifier(
            "Brawler: asks a creed",
            targets_gang(),
            ef_adds(creed),
            carried_by=archetypes["Brawler"],
        )
        create_interstitial("Creed", slots=[creed])
        gang = found_gang("The Forgotten", gang_type, owner=owner, budget=1000)
        client.force_login(owner)
        key = sheet_slot(gang, "Paths").key
        arrival = screen_url(gang, [key])
        picker = with_query(
            reverse("n26-choose", args=[gang.pk, key]), **{"return": arrival}
        )

        response = client.post(
            picker, {"thing": pick_key(archetypes["Brawler"]), "return": arrival}
        )

        assert response.status_code == 302
        path, asks, back = asks_in(response["Location"])
        assert path == reverse("n26-next", args=[gang.pk])
        assert asks == [key, sheet_slot(gang, "Brawler's creed").key]
        assert back == reverse("n26-gang", args=[gang.pk])
        assert client.get(picker).status_code == 404

    def test_a_pick_that_brings_another_screen_joins_the_address(
        self, client, landed, archetypes, legacy, picklist
    ):
        gang, here = landed
        creed = create_slot("Brawler's creed", legacy, picklist, assigned_to="gang")
        modifier(
            "Brawler: asks a creed",
            targets_gang(),
            ef_adds(creed),
            carried_by=archetypes["Brawler"],
        )
        create_interstitial("Creed", slots=[creed], skippable=True)
        key = sheet_slot(gang, "Archetype").key

        response = client.post(
            here, {"ask": key, "thing": pick_key(archetypes["Brawler"])}
        )

        _, asks, _ = asks_in(response["Location"])
        assert asks == [key, sheet_slot(gang, "Brawler's creed").key]
        body = page(client, response["Location"])
        assert "Creed" in body and "Brawler's creed" in body


# --- Skip and Continue ---------------------------------------------------------


class TestSkipAndContinue:
    """Skip is a link to the same screen without that block's questions;
    Continue waits for every question still on the screen."""

    @pytest.fixture
    def gang(self, owner, gang_type, shown):
        return found_gang("The Forgotten", gang_type, owner=owner, budget=1000)

    def test_a_skippable_block_offers_skip_and_it_drops_only_that_block(
        self, client, owner, gang, hunter
    ):
        kal = hire(gang, hunter, "Kal", paid=100)
        archetype = sheet_slot(gang, "Archetype").key
        path = sheet_slot(gang, "Hunter's path").key
        client.force_login(owner)

        body = page(client, screen_url(gang, [archetype, path]))

        assert ">Skip<" in body
        skip = body.split(">Skip<")[0].rsplit('href="', 1)[1].split('"')[0]
        _, asks, back = asks_in(skip.replace("&amp;", "&"))
        assert asks == [archetype]
        assert back == reverse("n26-gang", args=[gang.pk])
        assert kal.name in body

    def test_continue_waits_for_a_skippable_block_until_it_is_skipped_or_chosen(
        self, client, owner, gang, hunter, archetypes
    ):
        hire(gang, hunter, "Kal", paid=100)
        archetype = sheet_slot(gang, "Archetype").key
        path = sheet_slot(gang, "Hunter's path").key
        client.force_login(owner)
        here = screen_url(gang, [archetype, path])
        client.post(here, {"ask": archetype, "thing": pick_key(archetypes["Brawler"])})

        body = page(client, here)
        assert "Choose Hunter's path to continue." in body

        body = page(client, screen_url(gang, [archetype]))
        assert "to continue." not in body
        assert f'href="{reverse("n26-gang", args=[gang.pk])}"' in body

    def test_when_nothing_is_left_to_ask_the_reader_goes_on(self, client, owner, gang):
        client.force_login(owner)
        elsewhere = reverse("n26-hire-fighter", args=[gang.pk])

        response = client.get(screen_url(gang, [], back=elsewhere))

        assert response.status_code == 302
        assert response["Location"] == elsewhere

    def test_a_question_that_has_since_gone_leaves_the_rest_standing(
        self, client, owner, gang, hunter
    ):
        kal = hire(gang, hunter, "Kal", paid=100)
        archetype = sheet_slot(gang, "Archetype").key
        path = sheet_slot(gang, "Hunter's path").key
        with operation(gang, actor=owner) as op:
            op.remove(kal.membership)
        client.force_login(owner)

        body = page(client, screen_url(gang, [path, archetype]))

        assert "Choose an archetype" in body
        assert "Hunter's path" not in body

    def test_an_address_whose_questions_have_all_gone_goes_on(
        self, client, owner, gang, hunter
    ):
        kal = hire(gang, hunter, "Kal", paid=100)
        path = sheet_slot(gang, "Hunter's path").key
        with operation(gang, actor=owner) as op:
            op.remove(kal.membership)
        client.force_login(owner)

        response = client.get(screen_url(gang, [path]))

        assert response["Location"] == reverse("n26-gang", args=[gang.pk])

    def test_a_choice_with_nothing_to_offer_does_not_hold_the_reader(
        self, client, owner, gang, legacy
    ):
        """A screen that withheld Continue over a choice nobody can make
        would be policing; the card's own note still says it is open."""
        empty = create_picklist("Nothing yet", legacy)
        bare = create_slot("Fate", legacy, empty, assigned_to="gang")
        create_interstitial("Fate", slots=[bare])
        with operation(gang, actor=owner) as op:
            op.assign(bare, gang=gang)
        client.force_login(owner)

        body = page(client, screen_url(gang, [sheet_slot(gang, "Fate").key]))

        assert "Nothing is available to choose here." in body
        assert "to continue." not in body
        assert f'href="{reverse("n26-gang", args=[gang.pk])}"' in body

    def test_a_block_with_no_question_of_its_own_draws_no_skip(
        self, client, owner, gang, archetype_slot
    ):
        """Skip drops a block's own questions; a block whose every
        question another block asks too has nothing to drop, and a Skip
        leading back to the same screen would be a control that does
        nothing."""
        create_interstitial("Also asked", slots=[archetype_slot], skippable=True)
        key = sheet_slot(gang, "Archetype").key
        client.force_login(owner)

        body = page(client, screen_url(gang, [key]))

        assert "Also asked" in body
        assert ">Skip<" not in body

    def test_a_screen_asks_its_slots_in_the_order_the_author_gave_them(
        self, client, owner, gang, hunter, legacy, picklist
    ):
        """One screen on two arriving slots asks in attachment order, not
        in the order the address happens to name them."""
        creed = create_slot("Creed", legacy, picklist, assigned_to="gang")
        with operation(gang, actor=owner) as op:
            op.assign(creed, gang=gang)
        both = create_interstitial("Two at once")
        attach_interstitial(both, archetype_slot_of(gang), position=1)
        attach_interstitial(both, creed, position=0)
        archetype = sheet_slot(gang, "Archetype").key
        creed_key = sheet_slot(gang, "Creed").key
        client.force_login(owner)

        body = page(client, screen_url(gang, [archetype, creed_key]))

        block = body.split("Two at once", 1)[1]
        assert block.index("Creed") < block.index("Archetype")

    def test_slots_given_the_same_place_ask_by_name_however_the_address_names_them(
        self, client, owner, gang, legacy, picklist
    ):
        """Two attachments at one position fall back to the slot's name,
        as the attachments themselves are ordered — never to the order
        the address happens to name them in."""
        creed = create_slot("Creed", legacy, picklist, assigned_to="gang")
        with operation(gang, actor=owner) as op:
            op.assign(creed, gang=gang)
        both = create_interstitial("Two at once")
        attach_interstitial(both, archetype_slot_of(gang), position=0)
        attach_interstitial(both, creed, position=0)
        archetype = sheet_slot(gang, "Archetype").key
        creed_key = sheet_slot(gang, "Creed").key
        client.force_login(owner)

        for keys in ([archetype, creed_key], [creed_key, archetype]):
            block = page(client, screen_url(gang, keys)).split("Two at once", 1)[1]
            assert block.index("Archetype") < block.index("Creed"), keys

    def test_skip_keeps_a_question_another_block_still_asks(
        self, client, owner, gang, archetype_slot, legacy, picklist
    ):
        """A skippable screen on a slot of its own and on one another
        screen also asks about: skipping it drops its own question and
        must not wave the shared one through."""
        creed = create_slot("Creed", legacy, picklist, assigned_to="gang")
        with operation(gang, actor=owner) as op:
            op.assign(creed, gang=gang)
        create_interstitial("Also asked", slots=[archetype_slot, creed], skippable=True)
        archetype = sheet_slot(gang, "Archetype").key
        creed_key = sheet_slot(gang, "Creed").key
        client.force_login(owner)

        body = page(client, screen_url(gang, [archetype, creed_key]))

        skip = body.split(">Skip<")[0].rsplit('href="', 1)[1].split('"')[0]
        _, asks, _ = asks_in(skip)
        assert asks == [archetype]

    def test_a_slot_carrying_no_screen_is_not_asked_about(
        self, client, owner, gang, person_type, gang_type, legacy, picklist
    ):
        plain = create_profile("Ganger", person_type, gang_type, price=50)
        add_built_in(plain, create_slot("Bare", legacy, picklist))
        hire(gang, plain, "Rat", paid=50)
        client.force_login(owner)

        response = client.get(screen_url(gang, [sheet_slot(gang, "Bare").key]))

        assert response["Location"] == reverse("n26-gang", args=[gang.pk])


# --- The address --------------------------------------------------------------


class TestTheAddress:
    @pytest.fixture
    def gang(self, owner, gang_type, shown):
        return found_gang("The Forgotten", gang_type, owner=owner, budget=1000)

    def test_a_reader_who_does_not_own_the_gang_gets_a_404(self, client, gang):
        client.force_login(User.objects.create_user("stranger"))
        key = sheet_slot(gang, "Archetype").key

        assert client.get(screen_url(gang, [key])).status_code == 404

    def test_a_signed_out_reader_is_sent_to_sign_in(self, client, gang):
        response = client.get(screen_url(gang, [sheet_slot(gang, "Archetype").key]))
        assert response.status_code == 302
        assert "login" in response["Location"]

    def test_next_pointing_off_this_site_falls_back_to_the_sheet(
        self, client, owner, gang, archetypes
    ):
        client.force_login(owner)
        key = sheet_slot(gang, "Archetype").key
        here = screen_url(gang, [key], back="https://elsewhere.example/steal")

        body = page(client, here)
        assert "elsewhere.example" not in body

        response = client.post(
            here, {"ask": key, "thing": pick_key(archetypes["Brawler"])}
        )
        _, _, back = asks_in(response["Location"])
        assert back == reverse("n26-gang", args=[gang.pk])

    def test_asking_more_costs_the_offers_and_not_another_derivation(
        self, client, owner, gang, hunter
    ):
        """The gang is derived once for every address at once: asking four
        questions costs the three extra offers — a few queries each —
        and nothing like three more readings of the whole gang."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        for name in ("Kal", "Vex", "Sorrow"):
            hire(gang, hunter, name, paid=100)
        client.force_login(owner)
        one = [sheet_slot(gang, "Archetype").key]
        sheet = render_gang(gang)
        many = one + [
            line.key
            for card in sheet.models
            for line in card.questions
            if line.kind_label == "Hunter's path"
        ]
        assert len(many) == 4
        with CaptureQueriesContext(connection) as few:
            assert client.get(screen_url(gang, one)).status_code == 200
        with CaptureQueriesContext(connection) as more:
            assert client.get(screen_url(gang, many)).status_code == 200
        assert len(more) - len(few) <= 3 * (len(many) - 1)

    def test_a_full_choice_no_longer_offers_its_roll(
        self, client, owner, gang, legacy, archetypes
    ):
        table = create_picklist(
            "Fates",
            legacy,
            dice="d6",
            roll_selects="band",
            members=[archetypes["Brawler"]],
        )
        fated = create_slot("Fate", legacy, table, assigned_to="gang")
        create_interstitial("Fate", slots=[fated])
        with operation(gang, actor=owner) as op:
            op.assign(fated, gang=gang)
        client.force_login(owner)
        key = sheet_slot(gang, "Fate").key
        here = screen_url(gang, [key])
        assert "Roll on its own page" in page(client, here)

        client.post(here, {"ask": key, "thing": pick_key(archetypes["Brawler"])})

        assert "Roll on its own page" not in page(client, here)

    def test_the_address_is_capped_at_twenty_questions(self):
        from django.http import QueryDict

        from n26.core.arrivals import MAX_ASKS
        from n26.core.views.arrivals import _asks

        query = QueryDict(mutable=True)
        query.setlist("ask", [f"gang:{i}:{i}" for i in range(30)] + ["gang:1:1"])
        assert len(_asks(query)) == MAX_ASKS == 20

    def test_more_than_a_screenful_waits_on_a_further_screen(self, gang):
        """Nothing that arrived is dropped: the first screenful is asked
        here, and Continue leads to a screen asking the rest, and only
        then to where the act was going."""
        keys = [f"gang:{i}:{i}" for i in range(25)] + ["gang:3:3"]

        path, asks, back = asks_in(screen_url(gang, keys, back="/n26/"))

        assert asks == keys[:20]
        overflow_path, overflow_asks, overflow_back = asks_in(back)
        assert overflow_path == path
        assert overflow_asks == keys[20:25]
        assert overflow_back == "/n26/"

    def test_one_malformed_question_does_not_take_the_others_with_it(
        self, client, owner, gang, hunter
    ):
        kal = hire(gang, hunter, "Kal", paid=100)
        good = sheet_slot(gang, "Hunter's path").key
        client.force_login(owner)

        body = page(client, screen_url(gang, ["not-a-fighter:x:y", good]))

        assert "Hunter's path" in body and kal.name in body

    def test_a_carrier_spelled_as_a_uuid_is_the_same_question(
        self, client, owner, gang, hunter
    ):
        """A ULID has a UUID spelling too, and an address using it names
        the same row: the question draws, under the address as given."""
        kal = hire(gang, hunter, "Kal", paid=100)
        key = sheet_slot(gang, "Hunter's path").key
        where, anchor, offer = key.split(":")
        assert where == str(kal.pk)
        spelled = f"{kal.pk.to_uuid()}:{anchor}:{offer}"
        client.force_login(owner)

        body = page(client, screen_url(gang, [spelled]))

        assert "Hunter's path" in body and "Kal" in body
        assert f'name="ask" value="{spelled}"' in body

    def test_a_post_naming_a_question_no_screen_draws_settles_nothing(
        self, client, owner, gang, person_type, gang_type, legacy, picklist, archetypes
    ):
        """A valid address for a slot with no screen is not on this page,
        however it got into the address: a post naming it is refused."""
        plain = create_profile("Ganger", person_type, gang_type, price=50)
        add_built_in(plain, create_slot("Bare", legacy, picklist))
        hire(gang, plain, "Rat", paid=50)
        bare = sheet_slot(gang, "Bare").key
        archetype = sheet_slot(gang, "Archetype").key
        client.force_login(owner)
        here = screen_url(gang, [archetype, bare])

        body = page(client, here)
        assert "Bare" not in body

        response = client.post(
            here, {"ask": bare, "thing": pick_key(archetypes["Brawler"])}
        )

        assert "That choice is no longer on this screen." in page(
            client, response["Location"]
        )
        assert not Assignment.objects.filter(pickable=archetypes["Brawler"]).exists()

    def test_a_question_is_asked_once_however_often_the_address_names_it(
        self, client, owner, gang
    ):
        client.force_login(owner)
        key = sheet_slot(gang, "Archetype").key

        body = page(client, screen_url(gang, [key, key, key]))

        assert body.count("Choose an archetype") == 1

    def test_the_nested_return_address_survives_the_pick_screens_round_trip(
        self, client, owner, gang, legacy, picklist, person_type, gang_type
    ):
        """A roll table's question links out to the pick screen, carrying
        this screen's whole address — asks and next — as its return."""
        table = create_picklist("Fates", legacy, dice="d6", roll_selects="band")
        fated = create_slot("Fate", legacy, table, assigned_to="gang")
        create_interstitial("Fate", slots=[fated])
        with operation(gang, actor=owner) as op:
            op.assign(fated, gang=gang)
        client.force_login(owner)
        key = sheet_slot(gang, "Fate").key
        elsewhere = reverse("n26-hire-fighter", args=[gang.pk])
        here = screen_url(gang, [key], back=elsewhere)

        body = page(client, here)

        assert "Roll on its own page" in body
        link = (
            body.split("Roll on its own page")[0].rsplit('href="', 1)[1].split('"')[0]
        )
        link = link.replace("&amp;", "&")
        assert link.startswith(reverse("n26-choose", args=[gang.pk, key]))
        returned = parse_qs(urlsplit(link).query)["return"][0]
        assert asks_in(returned) == (
            reverse("n26-next", args=[gang.pk]),
            [key],
            elsewhere,
        )


# --- The structure ------------------------------------------------------------


class TestWhatTheScreenSays:
    """The structure names what is still to choose the way a sentence
    would, so the line under a withheld Continue reads as one."""

    def screen(self, *labels, settled=()):
        from n26.core.render import (
            ArrivalBlock,
            ArrivalQuestion,
            ArrivalScreen,
            ChoiceOffer,
        )

        return ArrivalScreen(
            blocks=tuple(
                ArrivalBlock(
                    heading=label,
                    description="",
                    questions=(
                        ArrivalQuestion(
                            key=f"gang:{index}:{index}",
                            label=label,
                            bearer="The Forgotten",
                            chosen=None,
                            settled=label in settled,
                            offer=ChoiceOffer(label=label),
                        ),
                    ),
                )
                for index, label in enumerate(labels)
            ),
            next_url="/n26/gangs/1/",
        )

    def test_one_open_question_is_named_alone(self):
        assert self.screen("Archetype").outstanding_words == "Archetype"

    def test_two_are_joined_with_and(self):
        assert (
            self.screen("Archetype", "Creed").outstanding_words == "Archetype and Creed"
        )

    def test_three_are_listed_with_and_before_the_last(self):
        assert (
            self.screen("Archetype", "Creed", "Path").outstanding_words
            == "Archetype, Creed and Path"
        )

    def test_two_questions_sharing_a_label_say_whose_they_are(self):
        from n26.core.render import (
            ArrivalBlock,
            ArrivalQuestion,
            ArrivalScreen,
            ChoiceOffer,
        )

        def question(bearer):
            return ArrivalQuestion(
                key=f"{bearer}:1:1",
                label="Primary skill",
                bearer=bearer,
                chosen=None,
                settled=False,
                offer=ChoiceOffer(label="Primary skill"),
            )

        screen = ArrivalScreen(
            blocks=(
                ArrivalBlock(
                    heading="Skills",
                    description="",
                    questions=(question("Kal"), question("Vex")),
                ),
            ),
            next_url="/n26/gangs/1/",
        )
        assert (
            screen.outstanding_words
            == "Primary skill for Kal and Primary skill for Vex"
        )

    def test_settled_questions_are_left_out(self):
        screen = self.screen("Archetype", "Creed", "Path", settled=("Creed",))
        assert screen.outstanding_words == "Archetype and Path"
        assert screen.may_continue is False
        assert self.screen("Archetype", settled=("Archetype",)).may_continue is True


# --- The other renderers know nothing of this ---------------------------------


class TestTheOtherRenderers:
    """The printed sheet and the text card read cards; a screen attached
    to a slot changes nothing they say."""

    def test_the_captured_sheet_and_the_text_card_do_not_change(
        self, owner, gang_type, archetype_slot
    ):
        gang = found_gang("The Forgotten", gang_type, owner=owner, budget=1000)
        before = gang_state(gang)
        text_before = gang_to_text(gang)

        shown = create_interstitial("Outcast archetype", slots=[archetype_slot])
        assert differences(before, gang_state(gang)) == []
        assert gang_to_text(gang) == text_before

        attach_interstitial(
            shown,
            create_slot("Other", archetype_slot.slot_type, archetype_slot.picklist),
        )
        assert differences(before, gang_state(gang)) == []

    def test_the_print_and_text_renderers_never_read_the_library_for_it(self):
        for name in ("printing.py", "render_text.py", "capture.py"):
            source = (CORE / name).read_text()
            assert "nterstitial" not in source, name
            assert "arrivals" not in source, name
