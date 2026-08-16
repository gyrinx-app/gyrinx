"""The owner edits what a model is: its subtypes and its rules.

An owner may add a subtype or rule by hand, and take one away — whatever
route it arrived by. Both are stored as assignments (reason ``edited``),
so the history keeps them; what a removal cancels is suppressed at read
time, never written to, so archiving the owner's edits gives the content's
own answer back. An added thing has teeth: rules that match on the
subtype reach the model exactly as if the content had granted it.
"""

import pytest
from django.contrib.auth.models import User

from n26.core.card import build_card, build_modifier_index
from n26.core.effects import compute
from n26.core.models import Assignment, LedgerEvent, Reason
from n26.core.operations import operation
from n26.core.render import build_model_card
from n26.library.models import Profile, ProfileType, StatlineType, StatlineTypeStat
from n26.tests.sandbox.actions import (
    add_built_in,
    adds,
    assign,
    create_rule,
    create_skill,
    create_stat,
    create_subtype,
    create_wargear,
    found_gang,
    has_subtypes,
    hire,
    modifier,
    set_statline,
    targets_every_model,
    targets_model,
)
from n26.tests.sandbox.test_render import FIGHTER_STATS

pytestmark = pytest.mark.django_db


@pytest.fixture
def stats(db):
    return {
        full: create_stat(short, full, **flags)
        for short, full, flags, _, _ in FIGHTER_STATS
    }


@pytest.fixture
def fighter_type(stats):
    shape = StatlineType.objects.create(name="Fighter")
    for position, (_, full, _flags, first, highlighted) in enumerate(FIGHTER_STATS):
        StatlineTypeStat.objects.create(
            statline_type=shape,
            stat=stats[full],
            position=position,
            is_first_of_group=first,
            is_highlighted=highlighted,
        )
    return ProfileType.objects.create(name="Fighter", statline_type=shape)


@pytest.fixture
def ganger_profile(fighter_type, gang_type):
    profile = Profile.objects.create(
        name="Escher Ganger", profile_type=fighter_type, gang_type=gang_type, price=55
    )
    set_statline(
        profile,
        movement=5,
        weapon_skill=4,
        ballistic_skill=4,
        strength=3,
        toughness=3,
        wounds=1,
        initiative=4,
        attacks=1,
        save=6,
        leadership=6,
        cool=6,
        willpower=6,
        intelligence=6,
    )
    return profile


@pytest.fixture
def yolanda(ganger_profile, gang_type):
    player = User.objects.create_user("player")
    gang = found_gang("The Bad Girls", gang_type, owner=player, budget=1000)
    return hire(gang, ganger_profile, "Yolanda", paid=55)


def card_for(miniature):
    card = build_card(miniature, with_statlines=True)
    index = build_modifier_index([n.assignable for n in card.all_nodes()])
    return build_model_card(miniature, card=card, computed=compute(card, index))


def edit(miniature):
    """Open an operation on the model's gang, as the edit page would."""
    gang = miniature.membership.gang
    return operation(gang, actor=gang.owner)


class TestAddingBySayingSo:
    """An added subtype is an ordinary free assignment, and it has teeth."""

    def test_the_card_shows_what_the_owner_added(self, yolanda):
        mounted = create_subtype("Mounted")
        with edit(yolanda) as op:
            op.assign(mounted, miniature=yolanda, paid=0, reason=Reason.EDITED)
        card = card_for(yolanda)
        assert card.type_line == "Fighter (Mounted)"

    def test_rules_that_match_the_subtype_reach_the_model(self, yolanda):
        """A gang rule for Mounted models cannot tell an owner's Mounted
        from a content-granted one."""
        mounted = create_subtype("Mounted")
        modifier(
            "Mounted models gain Hit & Run",
            targets_every_model(has_subtypes(mounted)),
            adds(create_skill("Hit & Run")),
            carried_by=yolanda.membership.gang.gang_type,
        )
        assert [s.name for s in card_for(yolanda).skills] == []
        with edit(yolanda) as op:
            op.assign(mounted, miniature=yolanda, paid=0, reason=Reason.EDITED)
        assert [s.name for s in card_for(yolanda).skills] == ["Hit & Run"]

    def test_the_history_says_the_owner_did_it(self, yolanda):
        mounted = create_subtype("Mounted")
        with edit(yolanda) as op:
            added = op.assign(mounted, miniature=yolanda, paid=0, reason=Reason.EDITED)
        assert added.ledger_entry.reason == Reason.EDITED
        assert added.ledger_entry.paid == 0
        assert added.ledger_events.get().actor == yolanda.membership.gang.owner


class TestTakingAway:
    """A removal is stored, compiled at read time, and reversible."""

    def test_a_built_in_rule_goes_quiet_and_stays_in_the_database(self, yolanda):
        gaunt = create_rule("Gaunt")
        add_built_in(yolanda.membership.profile, gaunt)
        rehired = hire(
            yolanda.membership.gang, yolanda.membership.profile, "Sump-Sister", paid=55
        )
        assert [line.name for line in card_for(rehired).rules] == ["Gaunt"]

        with edit(rehired) as op:
            op.take_away(rehired, gaunt)

        assert [line.name for line in card_for(rehired).rules] == []
        # Suppressed, not written to: the built-in assignment stands.
        assert Assignment.objects.filter(
            miniature_root=rehired, rule=gaunt, removes=False, archived=False
        ).exists()

    def test_the_removal_reaches_what_the_thing_was_granting(self, yolanda):
        """Cutter grants Mounted grants a skill; taking Mounted away
        takes the skill with it, down the chain."""
        mounted = create_subtype("Mounted")
        modifier(
            "Mounted grants Hit & Run",
            targets_model(),
            adds(create_skill("Hit & Run")),
            carried_by=mounted,
        )
        cutter = create_wargear("Cutter")
        modifier(
            "Cutter grants Mounted", targets_model(), adds(mounted), carried_by=cutter
        )
        assign(cutter, miniature=yolanda, paid=75)
        assert card_for(yolanda).type_line == "Fighter (Mounted)"
        assert [s.name for s in card_for(yolanda).skills] == ["Hit & Run"]

        with edit(yolanda) as op:
            op.take_away(yolanda, mounted)

        card = card_for(yolanda)
        assert card.type_line == "Fighter"
        assert card.skills == []

    def test_rules_matching_the_removed_subtype_no_longer_reach(self, yolanda):
        """The removal settles with round 0, so a conditional rule asks
        its question of a world where the subtype is already gone."""
        mounted = create_subtype("Mounted")
        modifier(
            "Mounted models gain Hit & Run",
            targets_every_model(has_subtypes(mounted)),
            adds(create_skill("Hit & Run")),
            carried_by=yolanda.membership.gang.gang_type,
        )
        assign(mounted, miniature=yolanda, paid=0)
        assert [s.name for s in card_for(yolanda).skills] == ["Hit & Run"]

        with edit(yolanda) as op:
            op.take_away(yolanda, mounted)

        assert [s.name for s in card_for(yolanda).skills] == []

    def test_a_paid_for_subtype_is_never_hidden(self, yolanda):
        """Money stands behind it, so the removal is refused and the
        card goes on showing it — said in the plan, never silently."""
        mounted = create_subtype("Mounted")
        assign(mounted, miniature=yolanda, paid=75)
        with edit(yolanda) as op:
            op.take_away(yolanda, mounted)

        raw = build_card(yolanda, with_statlines=True)
        index = build_modifier_index([n.assignable for n in raw.all_nodes()])
        computed = compute(raw, index)
        assert (
            build_model_card(yolanda, card=raw, computed=computed).type_line
            == "Fighter (Mounted)"
        )
        refused = [step for step in computed.plan if step.refused]
        assert refused and "Mounted" in refused[0].refused

    def test_the_take_away_is_in_the_history_by_its_own_name(self, yolanda):
        mounted = create_subtype("Mounted")
        with edit(yolanda) as op:
            removal = op.take_away(yolanda, mounted)
        event = removal.ledger_events.get()
        assert event.kind == LedgerEvent.Kind.TOOK_AWAY
        assert str(event) == "Took away: Mounted"

    def test_a_removal_is_never_a_line(self, yolanda):
        mounted = create_subtype("Mounted")
        with edit(yolanda) as op:
            op.take_away(yolanda, mounted)
        card = card_for(yolanda)
        # Nothing of that name was ever held, and the standing removal
        # draws nothing either.
        assert card.type_line == "Fighter"
        assert [line.name for line in card.subtypes] == []


class TestReset:
    """One act returns a section to what the content says."""

    def test_reset_archives_the_edits_and_the_content_answer_returns(self, yolanda):
        gaunt = create_rule("Gaunt")
        add_built_in(yolanda.membership.profile, gaunt)
        rehired = hire(
            yolanda.membership.gang, yolanda.membership.profile, "Sump-Sister", paid=55
        )
        keeled = create_rule("Keeled")
        with edit(rehired) as op:
            op.assign(keeled, miniature=rehired, paid=0, reason=Reason.EDITED)
            op.take_away(rehired, gaunt)
        assert [line.name for line in card_for(rehired).rules] == ["Keeled"]

        with edit(rehired) as op:
            undone = op.reset_edits(rehired, "rule")

        assert len(undone) == 2
        assert [line.name for line in card_for(rehired).rules] == ["Gaunt"]

    def test_reset_is_per_section(self, yolanda):
        mounted = create_subtype("Mounted")
        keeled = create_rule("Keeled")
        with edit(yolanda) as op:
            op.assign(mounted, miniature=yolanda, paid=0, reason=Reason.EDITED)
            op.assign(keeled, miniature=yolanda, paid=0, reason=Reason.EDITED)
        with edit(yolanda) as op:
            op.reset_edits(yolanda, "subtype")
        card = card_for(yolanda)
        assert card.type_line == "Fighter"
        assert [line.name for line in card.rules] == ["Keeled"]

    def test_reset_lands_in_the_history(self, yolanda):
        mounted = create_subtype("Mounted")
        with edit(yolanda) as op:
            op.assign(mounted, miniature=yolanda, paid=0, reason=Reason.EDITED)
        with edit(yolanda) as op:
            op.reset_edits(yolanda, "subtype")
        removed = LedgerEvent.objects.filter(
            gang=yolanda.membership.gang, kind=LedgerEvent.Kind.REMOVED, note="reset"
        )
        assert removed.count() == 1


class TestTheBooksStayHonest:
    """Edits price nothing, move nothing, and reconcile stays clean."""

    def test_reconcile_is_clean_after_the_lot(self, yolanda):
        from n26.core import reconcile

        gang = yolanda.membership.gang
        rating_before = gang.rating
        mounted = create_subtype("Mounted")
        keeled = create_rule("Keeled")
        with edit(yolanda) as op:
            op.assign(mounted, miniature=yolanda, paid=0, reason=Reason.EDITED)
            op.take_away(yolanda, keeled)
        with edit(yolanda) as op:
            op.reset_edits(yolanda, "subtype")

        gang.refresh_from_db()
        assert gang.rating == rating_before
        assert reconcile.check_gang(gang) == []

    def test_computing_the_card_twice_is_identical(self, yolanda):
        mounted = create_subtype("Mounted")
        modifier(
            "Mounted grants Hit & Run",
            targets_model(),
            adds(create_skill("Hit & Run")),
            carried_by=mounted,
        )
        assign(mounted, miniature=yolanda, paid=0)
        with edit(yolanda) as op:
            op.take_away(yolanda, mounted)
        card = build_card(yolanda, with_statlines=True)
        index = build_modifier_index([n.assignable for n in card.all_nodes()])
        first = compute(card, index)
        again = compute(card, index)
        assert [c.name for c in first.subtypes] == [c.name for c in again.subtypes]
        assert [c.name for c in first.skills] == [c.name for c in again.skills]
