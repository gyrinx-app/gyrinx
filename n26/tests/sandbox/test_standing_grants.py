"""A default declared on the gang type, reaching every model of one Type.

A gang type carries modifiers that every member's card can find. One
that targets every model whose Type is Fighter and gives a slot puts
that slot's choice on every fighter in every gang of the type — the
moment the modifier is attached, on gangs founded long before it, and
off again when it is detached. No profile carries the slot as a
built-in, so nothing is written per model and nothing needs propagating.

The pick a player makes on such a slot anchors on the gang's founding
assignment, the line the grant stands on. Detaching the grant takes the
choice off every card but leaves the picks where they are, as plain
lines: a modifier detached by mistake must not eat a gang's history.
"""

import pytest

from n26.core.card import build_card, build_modifier_index
from n26.core.effects import compute
from n26.core.models import Assignment
from n26.core.reconcile import assert_reconciled
from n26.library.authoring import detach_modifier
from n26.tests.sandbox.actions import (
    add_picklist_member,
    choose,
    create_pickable,
    create_picklist,
    create_profile,
    create_slot,
    create_slot_type,
    ef_adds,
    found_gang,
    hire,
    is_profile_type,
    modifier,
    targets_every_model,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def injuries(default_pack):
    """A slot that takes several picks and repeats, as the tables do."""
    slot_type = create_slot_type(
        "Lasting Injury", plural_name="Lasting Injuries", allows_repeats=True
    )
    table = create_picklist("Lasting Injury Table", slot_type)
    eye = create_pickable("Eye Injury", slot_type)
    add_picklist_member(table, eye)
    add_picklist_member(table, create_pickable("Out Cold", slot_type))
    slot = create_slot(
        "Lasting Injury",
        slot_type,
        table,
        label="Lasting Injuries",
        min_picks=0,
        max_picks=20,
    )
    return {"slot": slot, "eye": eye}


@pytest.fixture
def gang(gang_type, db):
    from django.contrib.auth.models import User

    owner = User.objects.create_user("player")
    return found_gang("The Scar Crossing", gang_type, owner=owner, budget=1000)


@pytest.fixture
def yolanda(gang, gang_type, fighter_type):
    profile = create_profile("Ganger", fighter_type, gang_type, price=50)
    return hire(gang, profile, "Yolanda", paid=50)


@pytest.fixture
def rig(gang, gang_type, vehicle_type):
    profile = create_profile("Cargo Rig", vehicle_type, gang_type, price=100)
    return hire(gang, profile, "The Rig", paid=100)


def grant(gang_type, slot, profile_type, negate=False):
    return modifier(
        f"{profile_type.name}s carry {slot.label}",
        targets_every_model(is_profile_type(profile_type, negate=negate)),
        ef_adds(slot),
        carried_by=gang_type,
    )


def computed_for(miniature):
    card = build_card(miniature, with_statlines=True)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    return compute(card, index)


def choice_of(miniature, label):
    return next(
        (s for s in computed_for(miniature).choices if s.kind_label == label), None
    )


class TestAGrantOnTheGangType:
    def test_every_fighter_carries_the_choice_and_no_vehicle_does(
        self, gang_type, injuries, fighter_type, yolanda, rig
    ):
        grant(gang_type, injuries["slot"], fighter_type)
        assert choice_of(yolanda, "Lasting Injuries") is not None
        assert choice_of(rig, "Lasting Injuries") is None

    def test_negated_it_reaches_the_other_type(
        self, gang_type, injuries, fighter_type, yolanda, rig
    ):
        grant(gang_type, injuries["slot"], fighter_type, negate=True)
        assert choice_of(yolanda, "Lasting Injuries") is None
        assert choice_of(rig, "Lasting Injuries") is not None

    def test_a_gang_founded_before_the_grant_has_it_at_once(
        self, gang, gang_type, injuries, fighter_type, yolanda
    ):
        """The point of a standing grant: nothing is written per model,
        so there is nothing to propagate to gangs that already exist."""
        assert choice_of(yolanda, "Lasting Injuries") is None
        before = Assignment.objects.count()
        grant(gang_type, injuries["slot"], fighter_type)
        assert Assignment.objects.count() == before
        assert choice_of(yolanda, "Lasting Injuries") is not None
        assert_reconciled(gang)


class TestPickingOnAGrantedSlot:
    def test_the_pick_lands_on_the_model_and_stacks(
        self, gang, gang_type, injuries, fighter_type, yolanda
    ):
        grant(gang_type, injuries["slot"], fighter_type)
        for _ in range(2):
            slot = choice_of(yolanda, "Lasting Injuries")
            choose(
                slot.anchor.assignment,
                injuries["eye"],
                slot=slot.slot,
                miniature=yolanda,
            )

        slot = choice_of(yolanda, "Lasting Injuries")
        assert [p.assignable.name for p in slot.picks] == ["Eye Injury"] * 2
        assert_reconciled(gang)

    def test_a_pick_stays_with_the_model_that_made_it(
        self, gang, gang_type, injuries, fighter_type, yolanda
    ):
        """The anchor is the gang's founding line, so without a host
        named the pick would land on the gang and ride every fighter's
        card. The choose page names the model it was made from."""
        grant(gang_type, injuries["slot"], fighter_type)
        other = hire(
            gang,
            create_profile("Juve", fighter_type, gang_type, price=25),
            "Wren",
            paid=25,
        )
        slot = choice_of(yolanda, "Lasting Injuries")
        choose(
            slot.anchor.assignment, injuries["eye"], slot=slot.slot, miniature=yolanda
        )

        assert Assignment.objects.get(pickable=injuries["eye"]).miniature == yolanda
        assert choice_of(other, "Lasting Injuries").picks == []
        assert_reconciled(gang)

    def test_detaching_the_grant_takes_the_choice_off_but_keeps_the_picks(
        self, gang, gang_type, injuries, fighter_type, yolanda
    ):
        standing = grant(gang_type, injuries["slot"], fighter_type)
        slot = choice_of(yolanda, "Lasting Injuries")
        choose(
            slot.anchor.assignment, injuries["eye"], slot=slot.slot, miniature=yolanda
        )
        pick = Assignment.objects.get(pickable=injuries["eye"])

        detach_modifier(gang_type, standing)

        assert choice_of(yolanda, "Lasting Injuries") is None
        pick.refresh_from_db()
        assert not pick.archived
        assert_reconciled(gang)
