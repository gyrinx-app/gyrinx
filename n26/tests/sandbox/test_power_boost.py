"""Suit Evolution: a Spyrer spends Kill Count and rolls on the Power Boost
table.

The table is standard content, seeded the way the lasting-effect tables
are: a slot type of its own, a D6 band table, a standing choice. Each
result carries what it adds to the model's rating — the figure the book
prints beside it — and the pick carries that rating without anything
being paid.

What an author finishes by hand, this file does with the verbs, as the
cookbook says to: the four characteristic results get a modifier that
improves the characteristic; every result gets one that moves the Kill
Count down by four when the pick lands; and the Spyre Hunters gang type
gives every Spyrer the choice. The choice is never narrowed by the count.
A pick whose choice has gone is discarded as an orphan, so a choice that
came and went with the Kill Count would take every boost already taken
with it the moment the count fell below four. Inform, never police: the
line is always there, and the count is the player's to read.
"""

import re

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.card import build_card, build_modifier_index
from n26.core.effects import compute
from n26.core.models import Assignment, LedgerEvent
from n26.core.operations import operation
from n26.core.reconcile import assert_reconciled
from n26.core.render import build_model_card
from n26.library.models import Picklist, Slot
from n26.library.standard_content import POWER_BOOST_TABLE, STANDARD_CONTENT
from n26.tests.sandbox.actions import (
    add_built_in,
    changes_stat,
    create_counter,
    create_profile,
    create_subtype,
    ef_adds,
    found_gang,
    has_subtypes,
    hire,
    modifier,
    op_changes_counter,
    remove,
    set_statline,
    tally,
    targets_every_model,
    targets_model,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner(db):
    return User.objects.create_user("player")


@pytest.fixture
def boost(default_pack):
    """The shipped table and its choice."""
    STANDARD_CONTENT["power-boost-table"].create()
    return {
        "table": Picklist.objects.get(name="Power Boost Table"),
        "slot": Slot.objects.get(name="Power Boost"),
    }


@pytest.fixture
def kill_count(default_pack):
    return create_counter("Kill Count")


@pytest.fixture
def spyrer_subtype(default_pack):
    return create_subtype("Spyrer")


def result_named(table, name, annotation=""):
    return next(
        m.pickable
        for m in table.members.all()
        if m.pickable.name == name and m.pickable.annotation == annotation
    )


@pytest.fixture
def finished_results(boost, kill_count, fighter_stats):
    """What an author attaches by hand: what each result does, and the
    spend every result carries."""
    table = boost["table"]
    raises = {
        ("Combat Neuroware", "WS"): "WS",
        ("Combat Neuroware", "BS"): "BS",
        ("Heightened Reactions", ""): "I",
        ("Improved Motive Power", ""): "M",
        ("Thickened Armour", ""): "Sv",
    }
    for member in table.members.all():
        result = member.pickable
        stat = raises.get((result.name, result.annotation))
        if stat is not None:
            modifier(
                f"{result}: raises {stat}",
                targets_model(),
                changes_stat(fighter_stats[stat], mode="improve", amount=1),
                carried_by=result,
            )
        modifier(
            f"{result}: spends four Kill Count",
            targets_model(),
            op_changes_counter(kill_count, mode="subtract", amount=4),
            carried_by=result,
        )
    return table


@pytest.fixture
def gang(gang_type, owner, boost, spyrer_subtype, finished_results):
    """The gang type gives every Spyrer the choice, narrowed by the
    subtype and never by the Kill Count."""
    modifier(
        "Spyrers carry Power Boost",
        targets_every_model(has_subtypes(spyrer_subtype)),
        ef_adds(boost["slot"]),
        carried_by=gang_type,
    )
    return found_gang("The Descent", gang_type, owner=owner, budget=2000)


@pytest.fixture
def spyrer(fighter_type, gang_type, spyrer_subtype, kill_count):
    profile = create_profile("Orrus Spyre Hunter", fighter_type, gang_type, price=300)
    set_statline(
        profile,
        movement=5,
        weapon_skill=4,
        ballistic_skill=3,
        strength=4,
        toughness=4,
        wounds=2,
        initiative=4,
        attacks=2,
        save=4,
        leadership=6,
        cool=6,
        willpower=6,
        intelligence=6,
    )
    add_built_in(profile, spyrer_subtype)
    add_built_in(profile, kill_count, amount=0)
    return profile


@pytest.fixture
def orrus(gang, spyrer):
    """Hired, and six kills in."""
    model = hire(gang, spyrer, "Orrus", paid=300)
    tally(kill_row(model), +6)
    return model


def kill_row(miniature):
    return Assignment.objects.get(miniature=miniature, counter__name="Kill Count")


def kills_of(miniature):
    return kill_row(miniature).counter_value.value


def card_for(miniature):
    card = build_card(miniature, with_statlines=True)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    computed = compute(card, index)
    return build_model_card(miniature, card=card, computed=computed), computed


def stat_of(miniature, short_name):
    drawn, _ = card_for(miniature)
    return drawn.statline.get(short_name).value


def choice_of(miniature, label="Power Boost"):
    _, computed = card_for(miniature)
    return next((c for c in computed.choices if c.kind_label == label), None)


def roll_for(miniature, rolled):
    """A roll made at the table and entered — the number is the test's."""
    choice = choice_of(miniature)
    gang = miniature.membership.gang
    with operation(gang, actor=gang.owner) as op:
        return op.roll(choice.slot, miniature=miniature, rolled=rolled)


def take(miniature, result, roll=None):
    choice = choice_of(miniature)
    gang = miniature.membership.gang
    with operation(gang, actor=gang.owner) as op:
        return op.choose(
            choice.anchor.assignment,
            result,
            slot=choice.slot,
            miniature=miniature,
            roll=roll,
        )


class TestTheTableIsStandardContent:
    """One click on Foundations, and the table stands as the book prints
    it: six results, two of them on the first band, each carrying what it
    adds to the model's rating."""

    def test_the_results_and_their_ratings_are_pinned(self, boost):
        """Pinned as literals, so the seed changes deliberately."""
        rows = [
            (
                m.roll_low,
                m.roll_high,
                str(m.pickable),
                m.pickable.qualifier,
                m.pickable.rating_contribution,
            )
            for m in boost["table"].members.order_by("position")
        ]
        assert rows == [
            (1, 1, "Combat Neuroware (WS)", "WS", 20),
            (1, 1, "Combat Neuroware (BS)", "BS", 20),
            (2, 2, "Heightened Reactions", "", 10),
            (3, 3, "Improved Motive Power", "", 10),
            (4, 4, "Thickened Armour", "", 15),
            (5, 6, "Hunting Rig Augmentation", "", 20),
        ]
        assert len(rows) == len(POWER_BOOST_TABLE)

    def test_a_reworded_annotation_keeps_its_row_on_a_second_click(self, boost):
        """An author may reword what a result prints. The seed matches its
        rows by qualifier, so a second click adopts the reworded row
        rather than refusing or creating a twin."""
        from n26.library.models import Pickable

        ws = Pickable.objects.get(name="Combat Neuroware", qualifier="WS")
        ws.annotation = "Weapon Skill"
        ws.save()

        STANDARD_CONTENT["power-boost-table"].create()

        assert Pickable.objects.filter(name="Combat Neuroware").count() == 2
        assert boost["table"].members.count() == 6
        assert STANDARD_CONTENT["power-boost-table"].status() == "complete"

    def test_a_homebrew_result_of_the_same_name_is_not_in_the_way(
        self, boost, homebrew
    ):
        """Names are unique per pack. A homebrew pack's own Thickened
        Armour is a different thing, and the Foundations click must not
        refuse over it."""
        from n26.library.models import Pickable, SlotType

        Pickable.objects.create(
            name="Thickened Armour",
            slot_type=SlotType.objects.get(name="Power Boost"),
            pack=homebrew,
        )

        STANDARD_CONTENT["power-boost-table"].create()

        assert boost["table"].members.count() == 6

    def test_a_one_lands_on_both_neuroware_results(self, boost):
        assert [str(m.pickable) for m in boost["table"].landing(1)] == [
            "Combat Neuroware (WS)",
            "Combat Neuroware (BS)",
        ]

    def test_every_other_roll_lands_on_one(self, boost):
        for roll in (2, 3, 4, 5, 6):
            assert len(boost["table"].landing(roll)) == 1

    def test_the_choice_repeats_across_a_campaign(self, boost):
        slot = boost["slot"]
        assert (slot.min_picks, slot.max_picks) == (0, 20)
        assert slot.slot_type.allows_repeats


class TestSpendingKillCount:
    """A result picked is four Kill Count gone, a characteristic raised
    where the result says, and the model worth more by the printed figure
    — with nothing paid, so nothing to refund."""

    def test_the_spyrer_carries_the_choice_and_a_ganger_does_not(
        self, gang, orrus, fighter_type, gang_type
    ):
        ganger = hire(
            gang,
            create_profile("Ganger", fighter_type, gang_type, price=50),
            "Krago",
            paid=50,
        )

        assert choice_of(orrus) is not None
        assert choice_of(ganger) is None
        assert_reconciled(gang)

    def test_neuroware_raises_weapon_skill_and_spends_four(self, gang, orrus, boost):
        gang.refresh_from_db()
        rating_before = gang.rating
        assert stat_of(orrus, "WS") == "4+"

        roll = roll_for(orrus, 1)
        pick = take(
            orrus, result_named(boost["table"], "Combat Neuroware", "WS"), roll=roll
        )

        assert stat_of(orrus, "WS") == "3+"
        assert stat_of(orrus, "BS") == "3+"
        assert kills_of(orrus) == 2
        orrus.refresh_from_db()
        gang.refresh_from_db()
        assert orrus.rating == 320
        assert gang.rating == rating_before + 20
        entry = pick.ledger_entry
        assert (entry.paid, entry.rating_contribution) == (0, 20)
        assert_reconciled(gang)

    def test_each_result_raises_its_own_characteristic(self, gang, orrus, boost):
        table = boost["table"]
        before = {short: stat_of(orrus, short) for short in ("I", "M", "Sv")}
        assert before == {"I": "4", "M": '5"', "Sv": "4+"}

        take(orrus, result_named(table, "Heightened Reactions"))
        take(orrus, result_named(table, "Improved Motive Power"))
        take(orrus, result_named(table, "Thickened Armour"))

        assert stat_of(orrus, "I") == "5"
        assert stat_of(orrus, "M") == '6"'
        assert stat_of(orrus, "Sv") == "3+"
        orrus.refresh_from_db()
        assert orrus.rating == 300 + 10 + 10 + 15
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_augmentation_changes_no_number_but_counts_twenty(self, gang, orrus, boost):
        before = {s: stat_of(orrus, s) for s in ("WS", "BS", "I", "M", "Sv")}

        roll = roll_for(orrus, 6)
        take(orrus, result_named(boost["table"], "Hunting Rig Augmentation"), roll=roll)

        assert {s: stat_of(orrus, s) for s in ("WS", "BS", "I", "M", "Sv")} == before
        assert kills_of(orrus) == 2
        orrus.refresh_from_db()
        assert orrus.rating == 320
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_a_capped_result_is_substituted_by_the_player(self, gang, orrus, boost):
        """The rules read a characteristic already at its best as Hunting
        Rig Augmentation. The roll does not decide the pick, so the player
        takes that result against a roll of one."""
        roll = roll_for(orrus, 1)
        pick = take(
            orrus, result_named(boost["table"], "Hunting Rig Augmentation"), roll=roll
        )

        assert pick.roll == roll
        assert stat_of(orrus, "WS") == "4+"
        assert kills_of(orrus) == 2
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_the_choice_stays_when_the_count_falls_below_four(self, gang, orrus, boost):
        """Nothing gates the line on the count. Below four it is still
        there, and so is everything already picked for it."""
        take(orrus, result_named(boost["table"], "Thickened Armour"))
        assert kills_of(orrus) == 2

        choice = choice_of(orrus)
        assert choice is not None
        assert [node.name for node in choice.picks] == ["Thickened Armour"]
        assert stat_of(orrus, "Sv") == "3+"

        take(orrus, result_named(boost["table"], "Heightened Reactions"))
        assert kills_of(orrus) == 0
        assert len(choice_of(orrus).picks) == 2
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_taking_a_result_back_drops_its_rating_and_keeps_the_spend(
        self, gang, orrus, boost
    ):
        """The four Kill Count were spent when the pick landed; taking the
        result back is a removal, and a removal moves no counter and no
        credits. The rating stops counting because the pick is archived."""
        pick = take(orrus, result_named(boost["table"], "Thickened Armour"))
        gang.refresh_from_db()
        credits_before = gang.credits

        remove(pick)

        assert kills_of(orrus) == 2
        assert stat_of(orrus, "Sv") == "4+"
        orrus.refresh_from_db()
        gang.refresh_from_db()
        assert orrus.rating == 300
        assert gang.credits == credits_before
        assert_reconciled(gang)


class TestThePickScreen:
    """The page the player rolls on: a one lifts both Combat Neuroware
    rows and offers each, so the choice of Weapon Skill or Ballistic
    Skill needs no machinery of its own."""

    @pytest.fixture
    def address(self, gang, orrus):
        choice = choice_of(orrus)
        key = f"{orrus.pk}:{choice.anchor.assignment.pk}:{choice.identity.pk}"
        return reverse("n26-choose", args=[gang.pk, key])

    def test_a_one_lifts_both_neuroware_rows(self, client, owner, address):
        client.force_login(owner)
        client.post(address, {"act": "enter", "rolled": "1"})
        event = LedgerEvent.objects.get(kind=LedgerEvent.Kind.ROLLED)

        page = client.get(f"{address}?roll={event.pk}").content.decode()

        assert "Rolled 1" in page
        assert re.search(
            r"Landed on <strong[^>]*>Combat Neuroware \(WS\)</strong>, "
            r"<strong[^>]*>Combat Neuroware \(BS\)</strong>\.",
            page,
        )
        assert 'aria-label="Add Combat Neuroware (WS)"' in page
        assert 'aria-label="Add Combat Neuroware (BS)"' in page

    def test_a_six_lifts_the_augmentation(self, client, owner, address):
        client.force_login(owner)
        client.post(address, {"act": "enter", "rolled": "6"})
        event = LedgerEvent.objects.get(kind=LedgerEvent.Kind.ROLLED)

        page = client.get(f"{address}?roll={event.pk}").content.decode()

        assert re.search(
            r"Landed on <strong[^>]*>Hunting Rig Augmentation</strong>\.", page
        )
        assert 'aria-label="Add Hunting Rig Augmentation"' in page
