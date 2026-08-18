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


@pytest.fixture(autouse=True)
def the_books_stay_honest(yolanda):
    """Every test here ends with the gang reconciled — edits must never
    move the books, whatever the test did on the way.

    Fetched fresh: the check compares the instance it is handed, and
    operations repin through instances of their own, so a cached one
    would report a drift that is only staleness.
    """
    yield
    from n26.core.models import Gang
    from n26.core.reconcile import assert_reconciled

    assert_reconciled(Gang.objects.get(pk=yolanda.membership.gang_id))


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


class TestTheEditPage:
    """The Subtypes & Rules box on the model's edit page, end to end."""

    def _page(self, client, miniature):
        from django.urls import reverse

        return client.get(reverse("n26-edit-fighter", args=[miniature.pk]))

    def _post(self, client, miniature, data):
        from django.urls import reverse

        return client.post(reverse("n26-edit-fighter", args=[miniature.pk]), data)

    def _held(self, page, key):
        """The section's held options, keyed. None where nothing is."""
        offer = page.context[key]
        return (
            {}
            if offer is None
            else {
                option.key: option for group in offer.groups for option in group.options
            }
        )

    def _addable(self, page, key):
        return {option.key: option for option in page.context[key]}

    def test_what_is_held_is_a_box_and_the_rest_is_the_panel(self, client, yolanda):
        """Two halves: what the card shows is a box to clear, and the
        rest of the library is what the search panel offers."""
        mounted = create_subtype("Mounted")
        gaunt = create_rule("Gaunt")
        assign(gaunt, miniature=yolanda, paid=0)
        client.force_login(yolanda.membership.gang.owner)
        page = self._page(client, yolanda)

        assert self._held(page, "rule_edits")[f"library.rule:{gaunt.pk}"].is_current
        assert f"library.subtype:{mounted.pk}" in self._addable(page, "subtype_more")
        assert f"library.subtype:{mounted.pk}" not in self._held(page, "subtype_edits")

    def test_every_option_is_a_box_in_the_page_so_no_script_can_add(
        self, client, yolanda
    ):
        """The panel only ticks boxes that are already there, so every
        addable thing is a box in the HTML — which is also the whole of
        the fallback for a reader with no script."""
        mounted = create_subtype("Mounted")
        gaunt = create_rule("Gaunt")
        assign(gaunt, miniature=yolanda, paid=0)
        client.force_login(yolanda.membership.gang.owner)
        body = self._page(client, yolanda).content.decode()
        assert "Subtypes &amp; Rules" in body
        # A box carries the key, never the name: a rule's identity takes
        # in its annotation, and two Leashes differ by nothing else.
        assert f'value="library.subtype:{mounted.pk}"' in body
        assert f'value="library.rule:{gaunt.pk}"' in body
        # The panel's own row reports that same key rather than the words.
        assert f"isPicked('library.subtype:{mounted.pk}')" in body

    def test_ticking_a_subtype_from_the_list_adds_it(self, client, yolanda):
        mounted = create_subtype("Mounted")
        client.force_login(yolanda.membership.gang.owner)
        self._post(
            client,
            yolanda,
            {"act": "subtypes", "subtypes": [f"library.subtype:{mounted.pk}"]},
        )
        assert card_for(yolanda).type_line == "Fighter (Mounted)"

    def test_ticking_a_subtype_adds_it_in_the_owners_name(self, client, yolanda):
        mounted = create_subtype("Mounted")
        client.force_login(yolanda.membership.gang.owner)
        self._post(
            client,
            yolanda,
            {"act": "subtypes", "subtypes": [f"library.subtype:{mounted.pk}"]},
        )
        assert card_for(yolanda).type_line == "Fighter (Mounted)"
        added = Assignment.objects.get(
            miniature_root=yolanda, subtype=mounted, archived=False
        )
        assert added.ledger_entry.reason == Reason.EDITED

    def test_clearing_a_granted_subtype_stores_a_removal(self, client, yolanda):
        mounted = create_subtype("Mounted")
        cutter = create_wargear("Cutter")
        modifier(
            "Cutter grants Mounted", targets_model(), adds(mounted), carried_by=cutter
        )
        assign(cutter, miniature=yolanda, paid=75)
        assert card_for(yolanda).type_line == "Fighter (Mounted)"
        client.force_login(yolanda.membership.gang.owner)
        self._post(client, yolanda, {"act": "subtypes"})
        assert card_for(yolanda).type_line == "Fighter"
        assert Assignment.objects.filter(
            miniature_root=yolanda, subtype=mounted, removes=True, archived=False
        ).exists()

    def test_ticking_a_taken_away_thing_restores_it(self, client, yolanda):
        gaunt = create_rule("Gaunt")
        add_built_in(yolanda.membership.profile, gaunt)
        rehired = hire(
            yolanda.membership.gang, yolanda.membership.profile, "Sump-Sister", paid=55
        )
        client.force_login(rehired.membership.gang.owner)
        self._post(client, rehired, {"act": "rules"})
        assert [line.name for line in card_for(rehired).rules] == []
        self._post(
            client, rehired, {"act": "rules", "rules": [f"library.rule:{gaunt.pk}"]}
        )
        assert [line.name for line in card_for(rehired).rules] == ["Gaunt"]

    def test_a_gang_held_rule_says_it_comes_from_the_gang(self, client, yolanda):
        """A rule assigned straight to the gang rides every member's card
        as a broadcast row — the box must say where it came from, not
        read as if the owner ticked it themselves."""
        gaunt = create_rule("Gaunt")
        assign(gaunt, gang=yolanda.membership.gang)
        client.force_login(yolanda.membership.gang.owner)
        page = self._page(client, yolanda)

        option = self._held(page, "rule_edits")[f"library.rule:{gaunt.pk}"]
        assert option.is_current
        assert option.detail == "from the gang"

    def test_a_paid_for_thing_is_not_offered_to_be_taken_away(self, client, yolanda):
        """A removal could not shift it, so its box is fixed and says
        why. Offering the act and then refusing it wrote a removal that
        changed nothing and reported a loss the card denied."""
        mounted = create_subtype("Mounted")
        assign(mounted, miniature=yolanda, paid=75)
        client.force_login(yolanda.membership.gang.owner)
        page = self._page(client, yolanda)
        option = self._held(page, "subtype_edits")[f"library.subtype:{mounted.pk}"]
        assert option.is_current
        assert option.fixed_because
        assert "sell" in option.fixed_because
        # Drawn disabled, so the browser never submits it.
        body = page.content.decode()
        box = body.split(f'value="library.subtype:{mounted.pk}"')[1][:200]
        assert "disabled" in box

    def test_a_fixed_box_submitting_nothing_is_not_read_as_a_clearing(
        self, client, yolanda
    ):
        """A disabled box posts nothing, and its silence must not be
        taken for a clearing — the whole reason granted things are left
        out of the difference too."""
        mounted = create_subtype("Mounted")
        assign(mounted, miniature=yolanda, paid=75)
        client.force_login(yolanda.membership.gang.owner)
        response = self._post(client, yolanda, {"act": "subtypes"})

        assert card_for(yolanda).type_line == "Fighter (Mounted)"
        assert not Assignment.objects.filter(
            miniature_root=yolanda, subtype=mounted, removes=True
        ).exists()
        body = client.get(response.url).content.decode()
        assert "lost Mounted" not in body
        # Nothing moved, so the page says exactly that.
        assert "Saved." in body

    def test_clearing_a_thing_both_added_and_granted_takes_it_fully_away(
        self, client, yolanda
    ):
        """Clearing means gone by every route: archiving the owner's own
        addition alone would leave a standing grant re-ticking the box."""
        mounted = create_subtype("Mounted")
        client.force_login(yolanda.membership.gang.owner)
        self._post(
            client,
            yolanda,
            {"act": "subtypes", "subtypes": [f"library.subtype:{mounted.pk}"]},
        )
        cutter = create_wargear("Cutter")
        modifier(
            "Cutter grants Mounted", targets_model(), adds(mounted), carried_by=cutter
        )
        assign(cutter, miniature=yolanda, paid=75)
        assert card_for(yolanda).type_line == "Fighter (Mounted)"

        self._post(client, yolanda, {"act": "subtypes"})

        assert card_for(yolanda).type_line == "Fighter"

    def test_reset_posts_per_section(self, client, yolanda):
        mounted = create_subtype("Mounted")
        keeled = create_rule("Keeled")
        client.force_login(yolanda.membership.gang.owner)
        self._post(
            client,
            yolanda,
            {"act": "subtypes", "subtypes": [f"library.subtype:{mounted.pk}"]},
        )
        self._post(
            client, yolanda, {"act": "rules", "rules": [f"library.rule:{keeled.pk}"]}
        )
        self._post(client, yolanda, {"act": "reset-edits", "kind": "subtype"})
        card = card_for(yolanda)
        assert card.type_line == "Fighter"
        assert [line.name for line in card.rules] == ["Keeled"]

    def test_a_stranger_cannot_post_edits(self, client, yolanda):
        mounted = create_subtype("Mounted")
        stranger = User.objects.create_user("stranger")
        client.force_login(stranger)
        response = self._post(
            client,
            yolanda,
            {"act": "subtypes", "subtypes": [f"library.subtype:{mounted.pk}"]},
        )
        assert response.status_code == 404
        assert card_for(yolanda).type_line == "Fighter"


class TestTheBooksStayHonest:
    """Edits price nothing, move nothing, and reconcile stays clean."""

    def test_reconcile_is_clean_after_the_lot(self, yolanda):
        from n26.core.reconcile import assert_reconciled

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
        assert_reconciled(gang)

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
