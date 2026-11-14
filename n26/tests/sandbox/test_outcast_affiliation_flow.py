"""Choose and replace an Outcast affiliation through player pages, including the dependent
Clan House choice and rank-scoped equipment access. This fixture omits Clanless Trade
Point grants and Mutant purchase-count rules.
"""

from uuid import uuid4

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.owned import thing_key
from n26.core.reconcile import assert_reconciled
from n26.core.render import render_gang
from n26.library.models import Affiliation, Pickable
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
    """Six House lists; Escher includes wargear representing a pet."""
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
    """Four affiliations with rank-scoped collection access. Clanless has no modifiers in
    this fixture.
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
    # The Clan House affiliation carries the dependent House question.
    modifier(
        "Clan House: choose one of the six Houses",
        targets_gang(),
        offers_choice(Affiliation, from_section=house_section, label="clan house"),
        carried_by=top["Clan House"],
    )
    return top, houses


@pytest.fixture
def outcasts(affiliations):
    """Build a hidden affiliation offer, then convert it to a gang-level slot before
    founding.
    """
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
    from n26.library.conversion import apply, plan_outcast_affiliation

    apply(plan_outcast_affiliation())
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
    """Find the gang-sheet choice row by kind label, or return None."""
    return next(
        (line for line in render_gang(gang).choices if line.kind_label == kind_label),
        None,
    )


def picker_url(gang, kind_label):
    return reverse("n26-choose", args=[gang.pk, slot_line(gang, kind_label).key])


def as_pickable(chosen, kind_label="Affiliation"):
    """Find the converted pickable matching the original affiliation and the choice’s slot
    type.
    """
    if isinstance(chosen, Pickable):
        return chosen
    slot_type = "Clan House" if kind_label == "Clan house" else kind_label
    return Pickable.objects.get(name=chosen.name, slot_type__name=slot_type)


def pick(client, gang, kind_label, affiliation):
    return client.post(
        picker_url(gang, kind_label),
        {
            "request_key": str(uuid4()),
            "thing": thing_key(as_pickable(affiliation, kind_label)),
        },
    )


def top_level_rows(gang):
    return [
        a
        for a in gang.assignments.filter(archived=False)
        if isinstance(a.assignable, Pickable)
        and a.chosen_for_slot_id
        and a.chosen_for_slot.name == "Affiliation"
    ]


class TestAnAnswerArrivingTwice:
    """Concurrent answers to a single-pick question must leave one live answer."""

    @pytest.mark.django_db(transaction=True)
    def test_two_answers_at_once_still_leave_one(
        self, monkeypatch, owner, gang, affiliations
    ):
        """Start two deliberate commands together and retain one live selection."""
        import threading
        from importlib import import_module

        from django.db import connections
        from django.test import Client

        top, _ = affiliations
        url = picker_url(gang, "Affiliation")
        payload = {"thing": thing_key(as_pickable(top["Clanless"]))}
        both_have_read = threading.Barrier(2, timeout=30)
        picker = import_module("n26.core.choice_workflow")
        apply_choice = picker.change
        went_wrong = []
        landed = []

        def start_together(*args, **kwargs):
            both_have_read.wait()
            return apply_choice(*args, **kwargs)

        monkeypatch.setattr(picker, "change", start_together)

        def answer():
            try:
                each = Client()
                each.force_login(owner)
                landed.append(each.post(url, {**payload, "request_key": str(uuid4())}))
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

        # A live thread after the timeout indicates a stalled request.
        assert [click.is_alive() for click in clicks] == [False, False]
        assert went_wrong == []
        # Both requests must succeed; a refusal would redirect to the picker instead of
        # the gang.
        gang_page = reverse("n26-gang", args=[gang.pk])
        assert [(r.status_code, r["Location"]) for r in landed] == [
            (302, gang_page),
            (302, gang_page),
        ]
        assert len(top_level_rows(gang)) == 1
        assert_reconciled(gang)


class TestTheAffiliationPicker:
    """The top-level picker offers only the four affiliations."""

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
    """Choosing again replaces the previous affiliation."""

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
    """The House question exists only while Clan House is chosen."""

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
        """Replacing Clan House removes its dependent House choice and answer."""
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
    """Each affiliation grants the collections authored for its target ranks."""

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
