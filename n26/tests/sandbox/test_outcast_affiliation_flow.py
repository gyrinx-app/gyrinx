"""The Outcast affiliation, chosen through the pages a player clicks.

The 2026 Outcast gang list: at creation the gang chooses one of four
affiliations — Clanless, Clan House, Mutant, Aranthian — and exactly one;
a Clan House gang then chooses which of the six Houses it affiliates
with, and that second question exists only because of the first pick.
Each affiliation's benefit is list access scoped by rank.

test_outcast_gang.py proves the structures; this file proves the flow as
clicked: the gang sheet offers the choice, the picker page lists exactly
the right options at each step and nothing else, one click chooses, and
changing the choice replaces it — with everything the old pick caused
retired along with it.

What the rules say that this deliberately does not model: Clanless TP
grants (the Trade Point budget design is parked), and the Mutant
per-rank purchase counts (two for Leaders and Champions, one for
Gangers) — access is granted and counting is a player matter until a
carry-limit design exists.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.owned import thing_key
from n26.core.render import render_gang
from n26.library.models import Affiliation
from n26.tests.sandbox.actions import (
    adds,
    create_affiliation,
    create_collection,
    create_default_set,
    create_gang_type,
    create_hidden,
    create_profile,
    create_subtype,
    create_wargear,
    found_gang,
    has_subtypes,
    hire_with_option,
    modifier,
    offers_choice,
    section_of,
    targets_every_model,
    targets_gang,
)

pytestmark = pytest.mark.django_db

HOUSES = ("Cawdor", "Delaque", "Escher", "Goliath", "Van Saar", "Orlock")
AFFILIATIONS = ("Clanless", "Clan House", "Mutant", "Aranthian")


@pytest.fixture
def subtypes(db):
    return {
        "leader": create_subtype("Outcast Leader"),
        "champion": create_subtype("Outcast Champion"),
        "ganger": create_subtype("Outcast Ganger"),
    }


@pytest.fixture
def house_lists(db):
    """Six lists, one per House. Escher's holds a pet, because the rule
    says the access includes Pets and a pet is just wargear on the list."""
    return {
        house: create_collection(
            f"House {house} Equipment List",
            entries=[(create_wargear(f"{house} blade"), {})]
            + ([(create_wargear("Phelynx"), {})] if house == "Escher" else []),
        )
        for house in HOUSES
    }


@pytest.fixture
def affiliations(subtypes, house_lists):
    """The four top-level affiliations, each with its printed benefit.

    Clanless is a bare token: its benefit is Trade Points, which the app
    does not budget yet, so choosing it grants nothing and says nothing.
    """
    leaders_and_champions = [subtypes["leader"], subtypes["champion"]]

    houses = {
        house: create_affiliation(
            f"House {house}",
            effects=[
                (
                    targets_every_model(has_subtypes(*leaders_and_champions)),
                    adds(house_list),
                )
            ],
        )
        for house, house_list in house_lists.items()
    }
    house_picks = create_collection(
        "Clan Houses", entries=[(houses[h], {}) for h in HOUSES]
    )
    house_section = section_of(house_picks, "Clan Houses", 0, is_default=True)

    mutations = create_collection(
        "Mutations", entries=[(create_wargear("Extra Arm", price=30), {})]
    )
    top = {
        "Clanless": create_affiliation("Clanless Outcast"),
        "Clan House": create_affiliation("Clan House Outcast"),
        "Mutant": create_affiliation(
            "Mutant Outcast",
            effects=[(targets_every_model(), adds(mutations))],
        ),
        "Aranthian": create_affiliation(
            "Aranthian Outcast",
            effects=[
                (
                    targets_every_model(has_subtypes(*leaders_and_champions)),
                    adds(create_collection("Aranthian Equipment List")),
                )
            ],
        ),
    }
    # The chained pick rides the Clan House pick, so the "which House?"
    # question exists exactly while that affiliation is the chosen one.
    modifier(
        "Clan House: choose one of the six Houses",
        targets_gang(),
        offers_choice(Affiliation, from_section=house_section, label="clan house"),
        carried_by=top["Clan House"],
    )
    return top, houses


@pytest.fixture
def outcasts(affiliations):
    """The gang type: a hidden carrier in its built-ins asks the
    affiliation question from the moment of founding."""
    top, _ = affiliations
    picks = create_collection(
        "Affiliations", entries=[(top[name], {}) for name in AFFILIATIONS]
    )
    picks_section = section_of(picks, "Affiliations", 0, is_default=True)

    slot = create_hidden("Affiliation")
    modifier(
        "Outcasts: the Leader chooses an Affiliation",
        targets_gang(),
        offers_choice(Affiliation, from_section=picks_section, label="affiliation"),
        carried_by=slot,
    )
    gang_type = create_gang_type("Outcasts")
    gang_type.built_ins = create_default_set("Outcast built-ins", members=[slot])
    gang_type.save()
    return gang_type


@pytest.fixture
def owner(db):
    return User.objects.create_user("outcast-player")


@pytest.fixture
def gang(outcasts, owner):
    return found_gang("The Unmade", outcasts, owner=owner)


@pytest.fixture
def crew(gang, subtypes, person_type):
    made = {}
    for rank, name, price in [
        ("leader", "Outcast Leader", 100),
        ("champion", "Outcast Champion", 80),
        ("ganger", "Outcast Ganger", 30),
    ]:
        profile = create_profile(name, person_type, gang.gang_type, price=price)
        profile.built_ins = create_default_set(
            f"{name} built-ins", members=[subtypes[rank]]
        )
        profile.save()
        made[rank] = hire_with_option(gang, profile, rank.title())
    return made


def slot_line(gang, kind_label):
    """The slot as the gang sheet draws it, or None once it is gone."""
    return next(
        (line for line in render_gang(gang).choices if line.kind_label == kind_label),
        None,
    )


def picker_url(gang, kind_label):
    return reverse("n26-choose", args=[gang.pk, slot_line(gang, kind_label).key])


def pick(client, gang, kind_label, affiliation):
    return client.post(picker_url(gang, kind_label), {"thing": thing_key(affiliation)})


def top_level_rows(gang):
    return [
        a
        for a in gang.assignments.filter(archived=False)
        if isinstance(a.assignable, Affiliation)
    ]


class TestAnAnswerArrivingTwice:
    """A question taking one answer holds one answer, however the second
    arrives.

    Answering replaces what stands, so the two acts — take back, write —
    have to be one act. The gang is held for the length of it and the
    card is computed inside that hold, so a second answer waits for the
    first and then reads what the first wrote. Two clicks land one row,
    whether they arrive one after the other or together.
    """

    def test_a_second_answer_replaces_the_first(
        self, client, owner, gang, affiliations
    ):
        top, _ = affiliations
        client.force_login(owner)
        url = picker_url(gang, "Affiliation")

        client.post(url, {"thing": thing_key(top["Clanless"])})
        client.post(url, {"thing": thing_key(top["Mutant"])})

        assert [str(row.assignable) for row in top_level_rows(gang)] == [
            "Mutant Outcast"
        ]

    @pytest.mark.django_db(transaction=True)
    def test_two_answers_at_once_still_leave_one(
        self, monkeypatch, owner, gang, affiliations
    ):
        """The double click, as it happens.

        Both requests are made to read the open question before either is
        allowed to write, which is the ordering that used to produce two
        rows: each looked, each saw nothing standing, and each wrote. The
        reading is synchronised rather than merely the posting, so the
        race is forced rather than hoped for.
        """
        import threading
        from importlib import import_module

        from django.db import connections
        from django.test import Client

        top, _ = affiliations
        url = picker_url(gang, "Affiliation")
        payload = {"thing": thing_key(top["Clanless"])}
        both_have_read = threading.Barrier(2, timeout=30)
        guard = threading.Lock()
        has_read = set()
        picker = import_module("n26.core.views.choose")
        read_slot = picker._find_slot
        went_wrong = []
        landed = []

        def read_then_wait(gang, key):
            """Hold each request at its first look, so neither writes
            until both have seen the question open."""
            found = read_slot(gang, key)
            with guard:
                first_look = threading.current_thread().ident not in has_read
                has_read.add(threading.current_thread().ident)
            if first_look:
                both_have_read.wait()
            return found

        monkeypatch.setattr(picker, "_find_slot", read_then_wait)

        def answer():
            try:
                each = Client()
                each.force_login(owner)
                landed.append(each.post(url, payload))
            except Exception as bad:  # noqa: BLE001 — reported, not raised
                went_wrong.append(repr(bad))
                both_have_read.abort()
            finally:
                connections.close_all()

        clicks = [threading.Thread(target=answer) for _ in range(2)]
        for click in clicks:
            click.start()
        for click in clicks:
            click.join(timeout=60)

        # A thread still running is a request that never came back —
        # a deadlock or a stall, which a row count alone would not show.
        assert [click.is_alive() for click in clicks] == [False, False]
        assert went_wrong == []
        # Both clicks were taken. One row because the second replaced the
        # first, not because a click was turned away — a refusal comes
        # back to the picker rather than to the gang.
        gang_page = reverse("n26-gang", args=[gang.pk])
        assert [(r.status_code, r["Location"]) for r in landed] == [
            (302, gang_page),
            (302, gang_page),
        ]
        assert len(top_level_rows(gang)) == 1


class TestTheAffiliationPicker:
    """The first question: four things on offer, and only those."""

    def test_the_gang_sheet_offers_the_choice_from_founding(self, client, owner, gang):
        line = slot_line(gang, "Affiliation")
        assert line is not None and line.chosen is None

        client.force_login(owner)
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
        assert "Affiliation" in body
        assert picker_url(gang, "Affiliation") in body

    def test_the_picker_lists_the_four_and_none_of_the_houses(
        self, client, owner, gang, affiliations
    ):
        client.force_login(owner)
        body = client.get(picker_url(gang, "Affiliation")).content.decode()

        for name in (
            "Clanless Outcast",
            "Clan House Outcast",
            "Mutant Outcast",
            "Aranthian Outcast",
        ):
            assert name in body, name
        for house in HOUSES:
            assert f"House {house}" not in body, house

    def test_one_click_settles_it(self, client, owner, gang, affiliations):
        top, _ = affiliations
        client.force_login(owner)
        response = pick(client, gang, "Affiliation", top["Clan House"])
        assert response.status_code == 302

        assert slot_line(gang, "Affiliation").chosen == "Clan House Outcast"
        assert [str(row.assignable) for row in top_level_rows(gang)] == [
            "Clan House Outcast"
        ]


class TestOnlyOneAffiliation:
    """One question, one pick: picking again replaces, never stacks."""

    def test_changing_the_pick_replaces_it(self, client, owner, gang, affiliations):
        top, _ = affiliations
        client.force_login(owner)
        pick(client, gang, "Affiliation", top["Clanless"])
        pick(client, gang, "Affiliation", top["Mutant"])

        assert [str(row.assignable) for row in top_level_rows(gang)] == [
            "Mutant Outcast"
        ]
        assert slot_line(gang, "Affiliation").chosen == "Mutant Outcast"


class TestTheChainedHousePick:
    """The second question exists exactly while Clan House is chosen."""

    def test_no_house_question_until_clan_house_is_chosen(
        self, client, owner, gang, affiliations
    ):
        top, _ = affiliations
        assert slot_line(gang, "Clan house") is None

        client.force_login(owner)
        pick(client, gang, "Affiliation", top["Clan House"])
        line = slot_line(gang, "Clan house")
        assert line is not None and line.chosen is None

    def test_its_picker_lists_the_six_houses_and_none_of_the_four(
        self, client, owner, gang, affiliations
    ):
        top, _ = affiliations
        client.force_login(owner)
        pick(client, gang, "Affiliation", top["Clan House"])

        body = client.get(picker_url(gang, "Clan house")).content.decode()
        for house in HOUSES:
            assert f"House {house}" in body, house
        for name in ("Clanless Outcast", "Mutant Outcast", "Aranthian Outcast"):
            assert name not in body, name

    def test_the_house_lands_and_opens_its_list_to_the_right_ranks(
        self, client, owner, gang, crew, affiliations
    ):
        from n26.core.card import build_card, build_modifier_index
        from n26.core.effects import compute

        top, houses = affiliations
        client.force_login(owner)
        pick(client, gang, "Affiliation", top["Clan House"])
        pick(client, gang, "Clan house", houses["Escher"])

        def lists_of(member):
            card = build_card(member)
            index = build_modifier_index([n.assignable for n in card.all_nodes()])
            return [c.name for c in compute(card, index).collections]

        assert "House Escher Equipment List" in lists_of(crew["leader"])
        assert "House Escher Equipment List" in lists_of(crew["champion"])
        assert "House Escher Equipment List" not in lists_of(crew["ganger"])

    def test_changing_the_affiliation_retires_the_house_pick_too(
        self, client, owner, gang, affiliations
    ):
        """The House pick is caused by the Clan House pick, so
        replacing the affiliation must not leave a stray House behind —
        a Mutant gang affiliated with Escher is not a thing the rules
        can express."""
        top, houses = affiliations
        client.force_login(owner)
        pick(client, gang, "Affiliation", top["Clan House"])
        pick(client, gang, "Clan house", houses["Escher"])
        pick(client, gang, "Affiliation", top["Mutant"])

        assert [str(row.assignable) for row in top_level_rows(gang)] == [
            "Mutant Outcast"
        ]
        assert slot_line(gang, "Clan house") is None


class TestWhatEachAffiliationOpens:
    """The printed benefit of each pick, read off a member's card."""

    def test_mutants_open_the_mutation_list_to_every_rank(
        self, client, owner, gang, crew, affiliations
    ):
        from n26.core.card import build_card, build_modifier_index
        from n26.core.effects import compute

        top, _ = affiliations
        client.force_login(owner)
        pick(client, gang, "Affiliation", top["Mutant"])

        for member in crew.values():
            card = build_card(member)
            index = build_modifier_index([n.assignable for n in card.all_nodes()])
            assert "Mutations" in [c.name for c in compute(card, index).collections]

    def test_aranthians_open_their_list_to_leaders_and_champions(
        self, client, owner, gang, crew, affiliations
    ):
        from n26.core.card import build_card, build_modifier_index
        from n26.core.effects import compute

        top, _ = affiliations
        client.force_login(owner)
        pick(client, gang, "Affiliation", top["Aranthian"])

        def lists_of(member):
            card = build_card(member)
            index = build_modifier_index([n.assignable for n in card.all_nodes()])
            return [c.name for c in compute(card, index).collections]

        assert "Aranthian Equipment List" in lists_of(crew["leader"])
        assert "Aranthian Equipment List" not in lists_of(crew["ganger"])

    def test_clanless_grants_nothing_the_cards_can_show(
        self, client, owner, gang, crew, affiliations
    ):
        from n26.core.card import build_card, build_modifier_index
        from n26.core.effects import compute

        top, _ = affiliations
        client.force_login(owner)
        pick(client, gang, "Affiliation", top["Clanless"])

        card = build_card(crew["leader"])
        index = build_modifier_index([n.assignable for n in card.all_nodes()])
        assert [c.name for c in compute(card, index).collections] == []
