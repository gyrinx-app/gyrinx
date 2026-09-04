"""Rolling on a roll table, and the record it leaves.

A choice whose list is a roll table is rolled for on its own pick
screen. The roll goes on the gang's history the moment it is made —
before anything is picked for it, whether or not anything ever is — and
the pick that follows names the roll, so the history reads "rolled 24"
with "Out Cold" beneath it, and a roll nothing followed stands alone,
which is what a second roll looks like to whoever reads it.

Two ways to the same record: the die rolled here, or a roll made at the
table and entered. Both are checked against the die, both are applied
once, and neither decides what may be picked — the rules substitute
results, so every row stays on offer and the record shows the roll
beside whatever was picked.
"""

import random
import re

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core import history
from n26.core.card import build_card, build_modifier_index
from n26.core.effects import compute
from n26.core.models import Assignment, LedgerEvent
from n26.core.operations import Refusal, operation
from n26.core.reconcile import assert_reconciled
from n26.core.render import build_choice_offer, lift_landing, option_key
from n26.library.models import Dice, Picklist, Slot
from n26.library.standard_content import STANDARD_CONTENT
from n26.tests.sandbox.actions import (
    add_picklist_member,
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
def owner(db):
    return User.objects.create_user("roller")


@pytest.fixture
def injuries(default_pack):
    """The shipped injury table: a D66 band table with a standing choice."""
    STANDARD_CONTENT["lasting-effect-tables"].create()
    return {
        "table": Picklist.objects.get(name="Lasting Injury Table"),
        "slot": Slot.objects.get(name="Lasting Injury"),
    }


@pytest.fixture
def gang(gang_type, owner, fighter_type, injuries):
    modifier(
        "Fighters carry Lasting Injury",
        targets_every_model(is_profile_type(fighter_type)),
        ef_adds(injuries["slot"]),
        carried_by=gang_type,
    )
    return found_gang("The Dice Cutters", gang_type, owner=owner, budget=1000)


@pytest.fixture
def krago(gang, gang_type, fighter_type):
    profile = create_profile("Ganger", fighter_type, gang_type, price=50)
    return hire(gang, profile, "Krago", paid=50)


def computed_for(miniature):
    card = build_card(miniature, with_statlines=True)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    return compute(card, index)


def choice_of(miniature, label):
    return next(
        (s for s in computed_for(miniature).choices if s.kind_label == label), None
    )


def result_named(table, name):
    return next(m.pickable for m in table.members.all() if m.pickable.name == name)


def roll_for(miniature, label, **kwargs):
    slot = choice_of(miniature, label)
    gang = miniature.membership.gang
    with operation(gang, actor=gang.owner) as op:
        return op.roll(slot.slot, miniature=miniature, **kwargs)


def pick(miniature, label, pickable, roll=None):
    slot = choice_of(miniature, label)
    gang = miniature.membership.gang
    with operation(gang, actor=gang.owner) as op:
        return op.choose(
            slot.anchor.assignment,
            pickable,
            slot=slot.slot,
            miniature=miniature,
            roll=roll,
        )


def sentences(gang, viewer=None):
    return [
        "".join(span.text for span in act.spans)
        for act in history.build(gang, viewer=viewer)
    ]


def act_saying(gang, fragment):
    return next(
        act
        for act in history.build(gang)
        if fragment in "".join(span.text for span in act.spans)
    )


class TestTheDice:
    """Each die rolls what its table can be read by, and nothing else."""

    @pytest.mark.parametrize("dice", list(Dice))
    def test_every_roll_is_one_the_table_can_hold(self, dice):
        rolls = set(Dice.rolls(dice))
        rng = random.Random(7)
        assert all(Dice.roll(dice, rng) in rolls for _ in range(500))

    def test_a_d66_is_tens_and_units_not_a_sum(self):
        # Every D66 roll across a seeded run reads as two faces.
        rng = random.Random(1)
        for _ in range(200):
            rolled = Dice.roll(Dice.D66, rng)
            assert 1 <= rolled // 10 <= 6 and 1 <= rolled % 10 <= 6

    def test_the_faces_are_read_back_where_the_total_says_which(self):
        assert Dice.faces(Dice.D66, 24) == (2, 4)
        assert Dice.faces(Dice.D6, 5) == (5,)
        assert Dice.faces(Dice.TWO_D6, 8) == ()
        assert Dice.faces(Dice.D3, 2) == ()


class TestWhereARollLands:
    @pytest.fixture
    def threshold(self, default_pack):
        kind = create_slot_type("Advancement")
        table = create_picklist(
            "Advancement Table", kind, dice="2d6", roll_selects="threshold"
        )
        for low, name in ((2, "Toughness"), (5, "Leadership"), (9, "Wounds")):
            add_picklist_member(table, create_pickable(name, kind), roll_low=low)
        return table

    def test_a_band_table_gives_the_one_row_holding_the_roll(self, injuries):
        landed = injuries["table"].landing(24)
        assert [m.pickable.name for m in landed] == ["Out Cold"]

    def test_a_roll_nothing_claims_lands_nowhere(self, default_pack):
        kind = create_slot_type("Sparse")
        table = create_picklist("Sparse Table", kind, dice="d6", roll_selects="band")
        add_picklist_member(table, create_pickable("Only one", kind), roll_low=1)
        assert table.landing(4) == []

    def test_a_threshold_table_opens_every_row_at_or_below(self, threshold):
        assert [m.pickable.name for m in threshold.landing(6)] == [
            "Toughness",
            "Leadership",
        ]
        assert [m.pickable.name for m in threshold.landing(12)] == [
            "Toughness",
            "Leadership",
            "Wounds",
        ]

    def test_a_list_that_is_not_a_roll_table_lands_nothing(self, default_pack):
        kind = create_slot_type("Legacy")
        plain = create_picklist("Legacies", kind)
        add_picklist_member(plain, create_pickable("Cawdor", kind))
        assert plain.landing(1) == []


class TestARollGoesOnTheRecord:
    def test_the_roll_is_written_before_anything_is_picked(self, gang, krago):
        event = roll_for(krago, "Lasting Injuries", rng=random.Random(3))

        assert event.kind == LedgerEvent.Kind.ROLLED
        assert event.roll in Dice.rolls(Dice.D66)
        assert event.dice == "d66"
        assert event.slot.name == "Lasting Injury"
        assert event.miniature == krago
        assert event.gang == gang
        assert event.actor == gang.owner
        assert not Assignment.objects.filter(roll=event).exists()
        assert_reconciled(gang)

    def test_a_roll_made_at_the_table_is_entered_and_says_so(self, gang, krago):
        event = roll_for(krago, "Lasting Injuries", rolled=24)
        assert event.roll == 24
        assert event.note == "Rolled at the table and entered here."

    def test_a_number_the_die_cannot_make_is_refused_in_words(self, gang, krago):
        with pytest.raises(Refusal, match="You cannot roll 37 on a D66"):
            roll_for(krago, "Lasting Injuries", rolled=37)
        assert not LedgerEvent.objects.filter(kind=LedgerEvent.Kind.ROLLED).exists()

    def test_a_choice_with_no_dice_behind_it_cannot_be_rolled(self, gang, default_pack):
        kind = create_slot_type("Legacy")
        plain = create_picklist("Legacies", kind)

        slot = create_slot("Gang Legacy", kind, plain)
        with operation(gang, actor=gang.owner) as op:
            with pytest.raises(ValueError, match="not rolled for"):
                op.roll(slot)


class TestThePickNamesItsRoll:
    def test_the_pick_points_at_the_roll_and_the_gang_reconciles(
        self, gang, krago, injuries
    ):
        event = roll_for(krago, "Lasting Injuries", rolled=24)
        out_cold = result_named(injuries["table"], "Out Cold")

        made = pick(krago, "Lasting Injuries", out_cold, roll=event)

        assert made.roll == event
        assert list(event.picks.all()) == [made]
        slot = choice_of(krago, "Lasting Injuries")
        assert [p.assignable.name for p in slot.picks] == ["Out Cold"]
        assert_reconciled(gang)

    def test_a_roll_is_applied_once(self, gang, krago, injuries):
        event = roll_for(krago, "Lasting Injuries", rolled=24)
        out_cold = result_named(injuries["table"], "Out Cold")
        pick(krago, "Lasting Injuries", out_cold, roll=event)

        with pytest.raises(Refusal, match="roll of 24 has already been applied"):
            pick(krago, "Lasting Injuries", out_cold, roll=event)
        assert Assignment.objects.filter(roll=event).count() == 1

    def test_a_pick_taken_back_frees_its_roll(self, gang, krago, injuries):
        """Removing what was picked is how a mistake is undone, and the
        roll it came from is still the roll that was made."""
        from n26.tests.sandbox.actions import remove

        event = roll_for(krago, "Lasting Injuries", rolled=24)
        out_cold = result_named(injuries["table"], "Out Cold")
        first = pick(krago, "Lasting Injuries", out_cold, roll=event)
        remove(first)

        second = pick(krago, "Lasting Injuries", out_cold, roll=event)
        assert second.roll == event
        assert first.roll == event
        assert_reconciled(gang)

    def test_a_roll_is_refused_on_a_choice_that_is_not_a_slots(self, gang, krago):
        """An offer has no dice; a roll handed to one is a caller's mistake."""
        from n26.library.models.modifier import OffersChoice

        event = roll_for(krago, "Lasting Injuries", rolled=24)
        slot = choice_of(krago, "Lasting Injuries")
        with operation(gang, actor=gang.owner) as op:
            with pytest.raises(ValueError, match="backed by a slot"):
                op.choose(
                    slot.anchor.assignment,
                    result_named(
                        Picklist.objects.get(name="Lasting Injury Table"), "Out Cold"
                    ),
                    offer=OffersChoice(),
                    roll=event,
                    miniature=krago,
                )

    def test_the_landing_row_is_not_enforced(self, gang, krago, injuries):
        """The rules substitute results — "counts as Out Cold" — so the
        roll does not fence what is picked; the record shows both."""
        event = roll_for(krago, "Lasting Injuries", rolled=51)
        out_cold = result_named(injuries["table"], "Out Cold")
        made = pick(krago, "Lasting Injuries", out_cold, roll=event)
        assert made.roll.roll == 51

    def test_a_roll_for_another_choice_is_refused(self, gang, krago, injuries):
        """A roll made for the vehicle table cannot be spent on the
        fighter's choice, however the post was assembled."""
        damage = Slot.objects.get(name="Lasting Damage")
        with operation(gang, actor=gang.owner) as op:
            stray = op.roll(damage, miniature=krago, rolled=24)
        out_cold = result_named(injuries["table"], "Out Cold")
        with pytest.raises(Refusal, match="not made for Lasting Injuries"):
            pick(krago, "Lasting Injuries", out_cold, roll=stray)

    def test_a_roll_made_on_another_fighters_card_is_refused(
        self, gang, gang_type, fighter_type, krago, injuries
    ):
        """The operation holds the card scoping too, so no caller — not
        only the page — can hand one fighter's roll to another's pick."""
        profile = create_profile("Second Ganger", fighter_type, gang_type, price=50)
        other = hire(gang, profile, "Nix", paid=50)
        theirs = roll_for(other, "Lasting Injuries", rolled=24)
        out_cold = result_named(injuries["table"], "Out Cold")
        with pytest.raises(Refusal, match="different card"):
            pick(krago, "Lasting Injuries", out_cold, roll=theirs)
        assert not Assignment.objects.filter(roll=theirs).exists()

    def test_a_pick_made_without_rolling_names_no_roll(self, gang, krago, injuries):
        made = pick(
            krago, "Lasting Injuries", result_named(injuries["table"], "Out Cold")
        )
        assert made.roll is None


class TestTheHistoryTellsTheRoll:
    def test_a_roll_and_its_pick_read_as_one_act(self, gang, krago, injuries):
        event = roll_for(krago, "Lasting Injuries", rolled=24)
        pick(
            krago,
            "Lasting Injuries",
            result_named(injuries["table"], "Out Cold"),
            roll=event,
        )

        act = act_saying(gang, "rolled 24 on a D66 for Krago — Lasting Injuries")
        assert [(sub.name, sub.kind) for sub in act.subs] == [
            ("Out Cold", "lasting injury")
        ]
        assert act.note == "Rolled at the table and entered here."
        assert not any("gained Out Cold" in said for said in sentences(gang))

    def test_a_roll_nothing_followed_stands_alone(self, gang, krago):
        roll_for(krago, "Lasting Injuries", rolled=24)
        roll_for(krago, "Lasting Injuries", rolled=55)

        told = [said for said in sentences(gang) if "rolled" in said]
        assert told == [
            "rolled 24 on a D66 for Krago — Lasting Injuries",
            "rolled 55 on a D66 for Krago — Lasting Injuries",
        ]
        assert all(
            not act.subs
            for act in history.build(gang)
            if "rolled" in "".join(s.text for s in act.spans)
        )

    def test_a_pick_made_days_after_its_roll_stands_on_its_own_day(
        self, gang, krago, injuries
    ):
        from datetime import timedelta

        event = roll_for(krago, "Lasting Injuries", rolled=24)
        LedgerEvent.objects.filter(pk=event.pk).update(
            created=event.created - timedelta(days=3)
        )
        pick(
            krago,
            "Lasting Injuries",
            result_named(injuries["table"], "Out Cold"),
            roll=event,
        )

        rolled = act_saying(gang, "rolled 24")
        assert rolled.subs == []
        assert any(
            said == "gained Out Cold on Krago, rolled 24" for said in sentences(gang)
        )

    def test_a_pick_whose_roll_is_outside_the_window_folds_under_nothing(
        self, gang, krago, injuries, campaign_type
    ):
        """A campaign log cut to its newest acts may hold the pick and
        not the roll it came from; the pick then stands on its own and
        names the roll, rather than folding under whatever act happens
        to be there."""
        from n26.tests.sandbox.actions import found_campaign, join_campaign

        campaign = found_campaign("The Cut", campaign_type, owner=gang.owner)
        join_campaign(gang, campaign)
        event = roll_for(krago, "Lasting Injuries", rolled=24)
        pick(
            krago,
            "Lasting Injuries",
            result_named(injuries["table"], "Out Cold"),
            roll=event,
        )
        told = [
            "".join(span.text for span in act.spans)
            for act in history.campaign_history(campaign, limit=1)
        ]
        assert told == ["gained Out Cold on Krago, rolled 24"]

    def test_a_generated_roll_carries_no_note(self, gang, krago):
        roll_for(krago, "Lasting Injuries", rng=random.Random(5))
        act = act_saying(gang, "rolled")
        assert act.note == ""

    def test_the_roll_is_a_fact_about_the_model(self, gang, krago):
        roll_for(krago, "Lasting Injuries", rolled=24)
        act = act_saying(gang, "rolled 24")
        assert act.category == "model"
        assert act.miniature_name == "Krago"

    def test_the_gangs_own_roll_is_a_fact_about_the_gang(self, gang, injuries):
        with operation(gang, actor=gang.owner) as op:
            op.roll(injuries["slot"], rolled=24)
        act = act_saying(gang, "rolled 24")
        assert act.category == "gang"
        assert act.miniature_name == ""


class TestThePickScreen:
    """The choose page rolls, shows the roll, and posts picks against it."""

    @pytest.fixture
    def address(self, gang, krago):
        slot = choice_of(krago, "Lasting Injuries")
        key = f"{krago.pk}:{slot.anchor.assignment.pk}:{slot.identity.pk}"
        return reverse("n26-choose", args=[gang.pk, key])

    def test_a_roll_table_offers_to_roll(self, client, owner, address):
        client.force_login(owner)
        page = client.get(address).content.decode()
        assert "Roll a D66" in page
        # Enter in the field must reach the Enter act, not Roll: the first
        # submit button in the form decides, so an unseen one comes first.
        assert page.index('value="enter"') < page.index('value="roll"')
        assert 'min="' not in page.split("Your roll from the table")[0][-600:]
        assert "The number you rolled at the table" in page
        assert "or add a result by hand" in page
        assert 'name="rolled"' in page
        # The range is a hint in the field, never a browser constraint —
        # one bounded field would stop every other button on the form.
        assert "(11–66)" in page
        assert 'min="11"' not in page

    def test_a_choice_with_no_dice_offers_no_roll(
        self, client, owner, gang, gang_type, fighter_type, default_pack
    ):
        kind = create_slot_type("Legacy")
        plain = create_picklist("Legacies", kind)
        add_picklist_member(plain, create_pickable("Cawdor", kind))

        legacy = create_slot("Gang Legacy", kind, plain)
        modifier(
            "Fighters carry a legacy",
            targets_every_model(is_profile_type(fighter_type)),
            ef_adds(legacy),
            carried_by=gang_type,
        )
        profile = create_profile("Juve", fighter_type, gang_type, price=20)
        juve = hire(gang, profile, "Nix", paid=20)
        slot = choice_of(juve, "Gang Legacy")
        key = f"{juve.pk}:{slot.anchor.assignment.pk}:{slot.identity.pk}"
        client.force_login(owner)
        page = client.get(reverse("n26-choose", args=[gang.pk, key])).content.decode()
        assert "Roll a" not in page
        assert 'name="rolled"' not in page

    def test_clicking_roll_writes_the_roll_and_comes_back_at_it(
        self, client, owner, gang, address
    ):
        client.force_login(owner)
        reply = client.post(address, {"act": "roll"})

        event = LedgerEvent.objects.get(kind=LedgerEvent.Kind.ROLLED)
        assert reply.status_code == 302
        assert reply.url == f"{address}?roll={event.pk}"
        assert event.roll in Dice.rolls(Dice.D66)
        assert event.actor == owner

    def test_the_page_at_a_roll_lifts_where_it_landed(
        self, client, owner, gang, krago, address, injuries
    ):
        client.force_login(owner)
        client.post(address, {"act": "enter", "rolled": "24"})
        event = LedgerEvent.objects.get(kind=LedgerEvent.Kind.ROLLED)

        page = client.get(f"{address}?roll={event.pk}").content.decode()
        assert "Rolled 24" in page
        assert re.search(r"Landed on <strong[^>]*>Out Cold</strong>\.", page)
        assert "Rolled at the table and entered here." in page
        assert 'aria-label="A die showing 2"' in page
        assert 'aria-label="A die showing 4"' in page
        # One result: the panel carries its Add as the main act, and the
        # table below stays whole rather than lifting a "Landed on" group.
        assert 'aria-label="Add Out Cold"' in page
        assert page.index('aria-label="Add Out Cold"') < page.index("or add a result")
        assert "The rest of the table" not in page
        assert f'name="roll" value="{event.pk}"' in page
        assert "Roll again" in page
        # The plain Roll controls give way to the result.
        assert "Roll a D66" not in page

    def test_a_threshold_roll_lifts_every_result_it_opened(
        self, client, owner, gang, gang_type, fighter_type, default_pack
    ):
        kind = create_slot_type("Advancement")
        table = create_picklist(
            "Advancement Table", kind, dice="2d6", roll_selects="threshold"
        )
        for low, name in ((2, "Toughness"), (5, "Leadership"), (9, "Wounds")):
            add_picklist_member(table, create_pickable(name, kind), roll_low=low)
        advancement = create_slot("Advancement", kind, table, max_picks=5)
        modifier(
            "Fighters advance",
            targets_every_model(is_profile_type(fighter_type)),
            ef_adds(advancement),
            carried_by=gang_type,
        )
        profile = create_profile("Juve", fighter_type, gang_type, price=20)
        juve = hire(gang, profile, "Nix", paid=20)
        slot = choice_of(juve, "Advancement")
        address = reverse(
            "n26-choose",
            args=[gang.pk, f"{juve.pk}:{slot.anchor.assignment.pk}:{slot.identity.pk}"],
        )
        client.force_login(owner)
        client.post(address, {"act": "enter", "rolled": "6"})
        event = LedgerEvent.objects.get(kind=LedgerEvent.Kind.ROLLED)

        page = client.get(f"{address}?roll={event.pk}").content.decode()
        assert re.search(
            r"High enough for <strong[^>]*>Toughness</strong>, <strong[^>]*>Leadership</strong>\.",
            page,
        )
        assert "Rolled high enough for" in page
        assert "Above the roll" in page
        # Several results open: no single Add in the panel, so the lifted
        # group's own Adds are the main act.
        assert page.index("Rolled high enough for") < page.index(
            'aria-label="Add Toughness"'
        )
        assert 'aria-label="Add Wounds"' in page

    def test_entering_a_roll_the_die_cannot_make_is_refused(
        self, client, owner, gang, address
    ):
        client.force_login(owner)
        reply = client.post(address, {"act": "enter", "rolled": "37"}, follow=True)
        assert "You cannot roll 37 on a D66." in reply.content.decode()
        assert not LedgerEvent.objects.filter(kind=LedgerEvent.Kind.ROLLED).exists()

    def test_entering_nothing_asks_for_the_number(self, client, owner, gang, address):
        client.force_login(owner)
        reply = client.post(address, {"act": "enter", "rolled": ""}, follow=True)
        assert "Enter the number you rolled." in reply.content.decode()

    def test_a_pick_posted_from_the_roll_names_it(
        self, client, owner, gang, krago, address, injuries
    ):
        client.force_login(owner)
        client.post(address, {"act": "enter", "rolled": "24"})
        event = LedgerEvent.objects.get(kind=LedgerEvent.Kind.ROLLED)
        out_cold = result_named(injuries["table"], "Out Cold")

        client.post(address, {"thing": option_key(out_cold), "roll": str(event.pk)})

        made = Assignment.objects.get(roll=event)
        assert made.assignable == out_cold
        assert made.miniature == krago
        assert_reconciled(gang)

    def test_a_full_choice_offers_no_roll(
        self, client, owner, gang, gang_type, fighter_type, default_pack
    ):
        """A roll for a choice that takes no more picks would be one the
        next Add refuses, so the controls are not drawn."""
        kind = create_slot_type("Scar")
        table = create_picklist("Scar Table", kind, dice="d6", roll_selects="band")
        scar = create_pickable("Scar", kind)
        add_picklist_member(table, scar, roll_low=1, roll_high=6)
        one = create_slot("Scars", kind, table, max_picks=1)
        modifier(
            "Fighters scar",
            targets_every_model(is_profile_type(fighter_type)),
            ef_adds(one),
            carried_by=gang_type,
        )
        profile = create_profile("Juve", fighter_type, gang_type, price=20)
        juve = hire(gang, profile, "Nix", paid=20)
        slot = choice_of(juve, "Scars")
        address = reverse(
            "n26-choose",
            args=[gang.pk, f"{juve.pk}:{slot.anchor.assignment.pk}:{slot.identity.pk}"],
        )
        client.force_login(owner)
        assert "Roll a D6" in client.get(address).content.decode()
        pick(juve, "Scars", scar)
        assert "Roll a D6" not in client.get(address).content.decode()

    def test_rolling_for_a_choice_filled_meanwhile_is_refused(
        self, client, owner, gang, gang_type, fighter_type, default_pack
    ):
        kind = create_slot_type("Scar")
        table = create_picklist("Scar Table", kind, dice="d6", roll_selects="band")
        scar = create_pickable("Scar", kind)
        add_picklist_member(table, scar, roll_low=1, roll_high=6)
        one = create_slot("Scars", kind, table, max_picks=1)
        modifier(
            "Fighters scar",
            targets_every_model(is_profile_type(fighter_type)),
            ef_adds(one),
            carried_by=gang_type,
        )
        profile = create_profile("Juve", fighter_type, gang_type, price=20)
        juve = hire(gang, profile, "Nix", paid=20)
        slot = choice_of(juve, "Scars")
        address = reverse(
            "n26-choose",
            args=[gang.pk, f"{juve.pk}:{slot.anchor.assignment.pk}:{slot.identity.pk}"],
        )
        client.force_login(owner)
        # The page was drawn with room; the pick lands before the Roll click.
        pick(juve, "Scars", scar)
        reply = client.post(address, {"act": "roll"}, follow=True)
        assert "Take one back before rolling." in reply.content.decode()
        assert not LedgerEvent.objects.filter(kind=LedgerEvent.Kind.ROLLED).exists()

    def test_a_choice_of_one_lifts_the_row_rather_than_adding_from_the_panel(
        self, client, owner, gang, gang_type, fighter_type, default_pack
    ):
        """Radios post under the name a panel button would, so a choice of
        one is settled from the lifted row and its Save, never a second
        control with the same name."""
        kind = create_slot_type("Fate")
        table = create_picklist("Fate Table", kind, dice="d6", roll_selects="band")
        for low, name in ((1, "Doomed"), (4, "Blessed")):
            add_picklist_member(
                table, create_pickable(name, kind), roll_low=low, roll_high=low + 2
            )
        one = create_slot("Fate", kind, table, min_picks=0, max_picks=1)
        modifier(
            "Fighters have a fate",
            targets_every_model(is_profile_type(fighter_type)),
            ef_adds(one),
            carried_by=gang_type,
        )
        profile = create_profile("Juve", fighter_type, gang_type, price=20)
        juve = hire(gang, profile, "Nix", paid=20)
        slot = choice_of(juve, "Fate")
        address = reverse(
            "n26-choose",
            args=[gang.pk, f"{juve.pk}:{slot.anchor.assignment.pk}:{slot.identity.pk}"],
        )
        client.force_login(owner)
        client.post(address, {"act": "enter", "rolled": "5"})
        event = LedgerEvent.objects.get(kind=LedgerEvent.Kind.ROLLED)
        page = client.get(f"{address}?roll={event.pk}").content.decode()
        assert "Landed on" in page
        assert 'aria-label="Add Blessed"' not in page
        assert page.count('name="thing"') >= 2  # the radios, not a button

    def test_a_spent_roll_is_shown_as_spent_and_not_offered_again(
        self, client, owner, gang, krago, address, injuries
    ):
        client.force_login(owner)
        client.post(address, {"act": "enter", "rolled": "24"})
        event = LedgerEvent.objects.get(kind=LedgerEvent.Kind.ROLLED)
        out_cold = result_named(injuries["table"], "Out Cold")
        client.post(address, {"thing": option_key(out_cold), "roll": str(event.pk)})

        page = client.get(f"{address}?roll={event.pk}").content.decode()
        assert "Already applied: Out Cold." in page
        assert f'name="roll" value="{event.pk}"' not in page
        # The Roll controls come back, since this roll is done with — and
        # the panel offers nothing of its own, so there is one Roll.
        assert "Roll a D66" in page
        assert page.count('value="roll"') == 1

        reply = client.post(
            address,
            {"thing": option_key(out_cold), "roll": str(event.pk)},
            follow=True,
        )
        assert "already been applied" in reply.content.decode()
        assert Assignment.objects.filter(roll=event).count() == 1

    def test_a_roll_made_for_another_gang_is_no_such_roll(
        self, client, owner, gang, gang_type, fighter_type, address, injuries
    ):
        other_owner = User.objects.create_user("other")
        other = found_gang("The Others", gang_type, owner=other_owner, budget=1000)
        profile = create_profile("Their Ganger", fighter_type, gang_type, price=50)
        theirs = hire(other, profile, "Theirs", paid=50)
        stray = roll_for(theirs, "Lasting Injuries", rolled=24)

        client.force_login(owner)
        assert client.get(f"{address}?roll={stray.pk}").status_code == 404
        reply = client.post(
            address,
            {
                "thing": option_key(result_named(injuries["table"], "Out Cold")),
                "roll": str(stray.pk),
            },
        )
        assert reply.status_code == 404
        assert not Assignment.objects.filter(roll=stray).exists()

    def test_a_roll_made_for_another_fighter_is_no_such_roll(
        self, client, owner, gang, gang_type, fighter_type, krago, address, injuries
    ):
        """One Slot row serves every fighter, so the slot alone would let
        Krago's roll be drawn on, and spent from, another fighter's page."""
        profile = create_profile("Second Ganger", fighter_type, gang_type, price=50)
        other = hire(gang, profile, "Nix", paid=50)
        theirs = roll_for(other, "Lasting Injuries", rolled=24)

        client.force_login(owner)
        assert client.get(f"{address}?roll={theirs.pk}").status_code == 404
        reply = client.post(
            address,
            {
                "thing": option_key(result_named(injuries["table"], "Out Cold")),
                "roll": str(theirs.pk),
            },
        )
        assert reply.status_code == 404
        assert not Assignment.objects.filter(roll=theirs).exists()

    def test_a_roll_key_that_is_no_key_is_no_such_roll(self, client, owner, address):
        client.force_login(owner)
        assert client.get(f"{address}?roll=junk").status_code == 404

    def test_rolling_again_leaves_the_first_roll_on_the_record(
        self, client, owner, gang, address
    ):
        client.force_login(owner)
        client.post(address, {"act": "roll"})
        client.post(address, {"act": "roll"})
        assert LedgerEvent.objects.filter(kind=LedgerEvent.Kind.ROLLED).count() == 2
        assert len([s for s in sentences(gang) if "rolled" in s]) == 2


class TestLiftingTheLanding:
    def test_the_landed_rows_come_first_under_their_own_heading(self, gang, krago):
        slot = choice_of(krago, "Lasting Injuries")
        offer = build_choice_offer(slot, computed_for(krago))
        landed = {
            option.key
            for group in offer.groups
            for option in group.options
            if option.name == "Out Cold"
        }
        lifted = lift_landing(offer, landed)
        assert [group.name for group in lifted.groups] == [
            "Landed on",
            "The rest of the table",
        ]
        assert [option.name for option in lifted.groups[0].options] == ["Out Cold"]
        assert lifted.takes_several == offer.takes_several

    def test_a_threshold_says_so_in_its_headings(self, gang, krago):
        slot = choice_of(krago, "Lasting Injuries")
        offer = build_choice_offer(slot, computed_for(krago))
        first = offer.groups[0].options[0].key
        lifted = lift_landing(offer, {first}, threshold=True)
        assert [group.name for group in lifted.groups] == [
            "Rolled high enough for",
            "Above the roll",
        ]

    def test_nothing_landed_leaves_the_offer_as_it_was(self, gang, krago):
        slot = choice_of(krago, "Lasting Injuries")
        offer = build_choice_offer(slot, computed_for(krago))
        assert lift_landing(offer, set()) is offer
