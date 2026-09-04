"""The gang's history page — the ledger's events told plainly.

The page turns the journal into acts a player can read: a hire is one
line with what came with it folded beneath, an undoing reads as an
undoing, and none of the machinery underneath is ever named. The page
itself is the owner's, because the history says things the roster does
not — when notes were edited, what a model was renamed from.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core import history
from n26.core.models import Gang, Reason
from n26.core.operations import operation
from n26.library.authoring import (
    add_built_in,
    create_rule,
    create_subtype,
    create_weapon,
)
from n26.tests.sandbox.actions import found_gang, hire, refund

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner(db):
    return User.objects.create_user("the-owner")


@pytest.fixture
def ganger(make_profile, make_statline):
    profile = make_profile("Ganger", price=55)
    make_statline(profile, movement=5, weapon_skill=4, toughness=3)
    add_built_in(profile, create_subtype("Loner"))
    add_built_in(profile, create_rule("Grit"))
    return profile


@pytest.fixture
def gang(gang_type, owner):
    return found_gang("The Ashen Choir", gang_type, owner=owner, budget=1000)


@pytest.fixture
def vex(gang, ganger, owner):
    return hire(gang, ganger, "Vex", paid=55, actor=owner)


def sentences(gang, viewer=None):
    acts = history.build(Gang.objects.get(pk=gang.pk), viewer=viewer)
    return ["".join(s.text for s in a.spans) for a in acts]


def act_saying(gang, fragment, viewer=None):
    acts = history.build(Gang.objects.get(pk=gang.pk), viewer=viewer)
    for act in acts:
        if fragment in "".join(s.text for s in act.spans):
            return act
    raise AssertionError(
        f"No act says {fragment!r}; the story reads: {sentences(gang)}"
    )


def edit(gang):
    return operation(gang, actor=gang.owner)


@pytest.fixture(autouse=True)
def the_books_stay_honest(gang):
    """Telling the story reads the ledger and must never move it.

    Fetched fresh: operations repin through instances of their own, so
    a cached one would report a drift that is only staleness.
    """
    yield
    from n26.core.reconcile import assert_reconciled

    assert_reconciled(Gang.objects.get(pk=gang.pk))


class TestTheStoryReadsPlainly:
    """Each act is one sentence in the player's words, with what rode
    along folded beneath it."""

    def test_a_hire_is_one_line_with_what_came_with_it_beneath(self, gang, vex):
        act = act_saying(gang, "hired Vex, a Ganger")
        assert {sub.name for sub in act.subs} == {"Loner", "Grit"}
        told = sentences(gang)
        assert not any("Loner" in line or "Grit" in line for line in told)

    def test_the_money_reads_as_the_player_counts_it(self, gang, vex):
        act = act_saying(gang, "hired Vex")
        assert act.credits == -55
        assert act.rating == 55

    def test_a_refund_reads_as_money_coming_back(self, gang, vex):
        refund(vex.membership, actor=gang.owner)
        act = act_saying(gang, "returned Ganger for a refund")
        assert act.credits == 55

    def test_what_went_with_a_refund_folds_beneath_it(self, gang, vex):
        """Refunding the fighter takes his built-ins with him — one
        line, not one per thing that rode along."""
        refund(vex.membership, actor=gang.owner)
        act = act_saying(gang, "returned Ganger for a refund")
        assert {sub.name for sub in act.subs} == {"Loner", "Grit"}
        assert not any("removed Loner" in line for line in sentences(gang))

    def test_a_paid_firing_line_leaves_in_the_story_too(self, gang, vex):
        """A free firing line is the weapon's own and never a line; a
        bought one is money in the books, so it is named when it goes."""
        from n26.library.authoring import add_weapon_profile
        from n26.tests.sandbox.actions import buy_weapon_profile, sell

        weapon = create_weapon("Autogun", profiles=[("Rapid fire", 0)], price=30)
        blaze = add_weapon_profile(weapon, "Blaze rounds", price=15)
        with edit(gang) as op:
            held = op.assign(weapon, miniature=vex, paid=30)
        buy_weapon_profile(held, blaze, actor=gang.owner)
        act_saying(gang, "bought Blaze rounds")
        sell(held, actor=gang.owner)
        sold = act_saying(gang, "sold Autogun")
        names = {sub.name for sub in sold.subs}
        assert any("Blaze rounds" in name for name in names)
        assert not any("Rapid fire" in name for name in names)

    def test_the_founding_folds_what_the_gang_type_brings(self, gang_type, owner):
        add_built_in(gang_type, create_rule("Law of the Blade"))
        gang = found_gang("The Blades", gang_type, owner=owner)
        act = act_saying(gang, "created the gang")
        assert {sub.name for sub in act.subs} == {"Law of the Blade"}

    def test_a_weapons_own_firing_line_earns_no_line(self, gang, vex):
        weapon = create_weapon("Autogun", profiles=[("Rapid fire", 0)], price=30)
        with edit(gang) as op:
            op.assign(weapon, miniature=vex, paid=30)
        act_saying(gang, "bought Autogun")
        acts = history.build(Gang.objects.get(pk=gang.pk))
        told = " ".join(
            "".join(s.text for s in a.spans) + " ".join(sub.name for sub in a.subs)
            for a in acts
        )
        assert "Rapid fire" not in told

    def test_nothing_says_the_machinery_underneath(self, gang, vex):
        with edit(gang) as op:
            op.take_away(vex, create_subtype("Mounted"))
            op.rename(vex, "Vex the Bold")
        told = " ".join(sentences(gang)).casefold()
        for word in ("assignment", "batch", "modifier", "archived"):
            assert word not in told


class TestUndoingReadsAsUndoing:
    """Archiving a taken-away thing restores it, and the story says so —
    the plain record would read as the opposite of what happened."""

    def test_taking_away_and_resetting_read_as_opposites(self, gang, vex):
        mounted = create_subtype("Mounted")
        with edit(gang) as op:
            op.take_away(vex, mounted)
        act_saying(gang, "took Mounted away from Vex")
        with edit(gang) as op:
            op.reset_edits(vex, "subtype")
        act = act_saying(gang, "put Mounted back on Vex")
        assert act.category == "model"

    def test_one_save_of_several_changes_is_one_line(self, gang, vex):
        with edit(gang) as op:
            op.assign(
                create_subtype("Agile"),
                miniature=vex,
                paid=0,
                reason=Reason.EDITED,
            )
            op.assign(
                create_subtype("Wyrd"),
                miniature=vex,
                paid=0,
                reason=Reason.EDITED,
            )
            op.take_away(vex, create_subtype("Mounted"))
        act = act_saying(gang, "changed what Vex is")
        turns = {sub.name: sub.note for sub in act.subs}
        assert turns == {
            "Agile": "added",
            "Wyrd": "added",
            "Mounted": "taken away",
        }

    def test_a_reset_of_several_edits_is_one_line_saying_reset(self, gang, vex):
        with edit(gang) as op:
            op.assign(
                create_subtype("Agile"),
                miniature=vex,
                paid=0,
                reason=Reason.EDITED,
            )
            op.take_away(vex, create_subtype("Mounted"))
        with edit(gang) as op:
            op.reset_edits(vex, "subtype")
        act = act_saying(gang, "reset what Vex is")
        turns = {sub.name: sub.note for sub in act.subs}
        assert turns == {"Agile": "removed", "Mounted": "back"}


class TestWhenAGrantArrivesLater:
    """A grant folds under its own act, never a different day's."""

    def test_a_grant_in_a_later_act_is_its_own_line(self, gang, vex):
        """Settled weeks after the hire, it belongs to its own date —
        not folded back under the hire as if it had always been there."""
        skill = create_rule("Ferocity")
        with edit(gang) as op:
            op.assign(
                skill,
                miniature=vex,
                caused_by=vex.membership,
                kind=history.Kind.GRANTED,
            )
        act = act_saying(gang, "gained Ferocity on Vex")
        hired = act_saying(gang, "hired Vex")
        assert "Ferocity" not in {sub.name for sub in hired.subs}
        assert act.when > hired.when

    def test_an_unmarked_grant_still_folds_through_its_cause(self, gang, vex):
        """Records from before acts carried a mark: the recorded cause
        is all there is, and it is enough."""
        from n26.core.models import LedgerEvent

        skill = create_rule("Ferocity")
        with edit(gang) as op:
            op.assign(
                skill,
                miniature=vex,
                caused_by=vex.membership,
                kind=history.Kind.GRANTED,
            )
        LedgerEvent.objects.update(batch=None)
        hired = act_saying(gang, "hired Vex")
        assert "Ferocity" in {sub.name for sub in hired.subs}


class TestWhatAnActSaysAboutItself:
    """Who did it, what it was called before, which cell moved."""

    def test_the_viewer_reads_their_own_acts_as_you(self, gang, vex):
        acts = history.build(gang, viewer=gang.owner)
        assert all(a.actor == "You" for a in acts)
        acts = history.build(gang)
        assert all(a.actor == "the-owner" for a in acts)

    def test_a_rename_keeps_both_names(self, gang, vex):
        with edit(gang) as op:
            op.rename(vex, "Vex the Bold")
        act = act_saying(gang, "renamed Vex to Vex the Bold")
        assert act.note == "Vex → Vex the Bold"

    def test_a_characteristic_says_which_and_to_what(self, gang, vex):
        from n26.core.forms import statline_override_form_for

        form_class = statline_override_form_for(vex.membership.profile)
        form = form_class.opened_on(vex, {"statline-weapon_skill": "2+"})
        assert form.is_valid(), form.errors
        with edit(gang) as op:
            op.set_stats(vex, form.changes())
        act = act_saying(gang, "set Vex's WS to 2+")
        assert "2+" in act.note

    def test_a_cleared_characteristic_says_which(self, gang, vex):
        from n26.core.forms import statline_override_form_for

        form_class = statline_override_form_for(vex.membership.profile)
        form = form_class.opened_on(vex, {"statline-weapon_skill": "2+"})
        assert form.is_valid(), form.errors
        with edit(gang) as op:
            op.set_stats(vex, form.changes())
        form = form_class.opened_on(vex, {"statline-weapon_skill": ""})
        assert form.is_valid(), form.errors
        with edit(gang) as op:
            op.set_stats(vex, form.changes())
        act = act_saying(gang, "cleared Vex's WS")
        assert "prints again" in act.note


class TestTheGangsOwnFacts:
    """Changing what the gang is called or may spend is part of its
    story; how it is drawn is not."""

    def test_the_budget_change_is_in_the_history(self, gang, vex):
        with edit(gang) as op:
            op.set_budget(1500)
        act = act_saying(gang, "set the budget to 1500¢")
        assert act.note == "1000¢ → 1500¢"
        assert act.category == "money"

    def test_lifting_the_budget_says_the_gang_spends_freely(self, gang):
        with edit(gang) as op:
            op.set_budget(None)
        act = act_saying(gang, "lifted the budget")
        assert act.note == "1000¢ → unlimited"

    def test_renaming_the_gang_keeps_both_names(self, gang):
        with edit(gang) as op:
            op.rename_gang("The Ashen Few")
        act = act_saying(gang, "renamed the gang The Ashen Choir to The Ashen Few")
        assert act.category == "gang"

    def test_a_budget_that_did_not_move_says_nothing(self, gang):
        before = len(sentences(gang))
        with edit(gang) as op:
            op.set_budget(gang.starting_credits)
            op.rename_gang(gang.name)
        assert len(sentences(gang)) == before

    def test_a_refused_budget_leaves_the_page_stating_what_is_stored(
        self, client, gang, vex
    ):
        """A budget the spending cannot fit is refused and rolled back,
        so the screen must not show the figures it rejected."""
        client.force_login(gang.owner)
        response = client.post(
            reverse("n26-edit-gang", args=[gang.pk]),
            {"name": "The Ashen Few", "starting_credits": "10", "colour": "red"},
        )
        assert response.status_code == 200
        assert response.context["gang"].name == "The Ashen Choir"
        assert response.context["gang"].starting_credits == 1000
        assert "budget" not in " ".join(sentences(gang))

    def test_the_edit_page_records_what_it_changed(self, client, gang):
        """The screen an owner really uses, not the verb underneath."""
        client.force_login(gang.owner)
        response = client.post(
            reverse("n26-edit-gang", args=[gang.pk]),
            {"name": "The Ashen Few", "starting_credits": "1500", "colour": "red"},
        )
        assert response.status_code == 302
        told = " ".join(sentences(gang))
        assert "renamed the gang The Ashen Choir to The Ashen Few" in told
        assert "set the budget to 1500¢" in told


class TestTheCostDoesNotFollowTheLength:
    """Telling a long story costs the same queries as a short one.

    The reads are fixed by design — the events, the records they name,
    who is still on the roster — and none of them is per act. A gang
    played for a season would otherwise pay a query a line.
    """

    def _lengthen(self, gang, vex, acts):
        for number in range(acts):
            with edit(gang) as op:
                op.rename(vex, f"Vex {number}")

    def test_the_queries_stay_flat_as_the_history_grows(
        self, gang, vex, django_assert_num_queries
    ):
        self._lengthen(gang, vex, 5)
        short = Gang.objects.get(pk=gang.pk)
        with django_assert_num_queries(3):
            history.build(short, viewer=gang.owner)
        self._lengthen(gang, vex, 60)
        long = Gang.objects.get(pk=gang.pk)
        with django_assert_num_queries(3):
            history.build(long, viewer=gang.owner)


class TestASnapshotOfTheStory:
    """A screen wanting the last few acts reads the last stretch of
    events, never the whole story: a gang played for a season would
    otherwise pay for every act it ever did to print five lines.

    The sentences are the history page's own, so the two cannot describe
    one act differently.
    """

    def _lengthen(self, gang, vex, acts):
        for number in range(acts):
            with edit(gang) as op:
                op.rename(vex, f"Vex {number}")

    def told(self, acts):
        return ["".join(span.text for span in act.spans) for act in acts]

    def test_the_newest_act_comes_first(self, gang, vex):
        latest = history.latest(Gang.objects.get(pk=gang.pk), viewer=gang.owner)

        assert self.told(latest)[0].startswith("hired Vex")

    def test_it_gives_back_no_more_than_it_was_asked_for(self, gang, vex):
        self._lengthen(gang, vex, 8)
        latest = history.latest(Gang.objects.get(pk=gang.pk), limit=3)

        assert len(latest) == 3

    def test_they_are_the_acts_the_page_would_print_first(self, gang, vex):
        self._lengthen(gang, vex, 4)
        whole = Gang.objects.get(pk=gang.pk)
        page = list(reversed(history.build(whole, viewer=gang.owner)))[:5]
        latest = history.latest(whole, viewer=gang.owner)

        assert self.told(latest) == self.told(page)

    def test_a_gang_nothing_has_been_done_to_has_nothing_to_tell(
        self, gang_type, owner
    ):
        """A row written without an operation behind it — the state a
        screen has to draw something for rather than a heading over
        nothing."""
        bare = Gang.objects.create(
            name="The Rust Sermon", owner=owner, gang_type=gang_type
        )

        assert history.latest(bare) == []

    def test_models_are_named_rather_than_linked(self, gang, vex):
        """The way through to a model is the roster, and the way through
        to the whole story is the history page: knowing which models are
        still on the roster is a query a snapshot need not spend."""
        latest = history.latest(Gang.objects.get(pk=gang.pk), viewer=gang.owner)

        assert any("Vex" in line for line in self.told(latest))
        assert not any(span.href for act in latest for span in act.spans)

    def test_the_cost_does_not_follow_the_length(
        self, gang, vex, django_assert_num_queries
    ):
        """Two reads whatever the gang's age: the last stretch of events,
        and the records those events name."""
        self._lengthen(gang, vex, 5)
        short = Gang.objects.get(pk=gang.pk)
        with django_assert_num_queries(2):
            history.latest(short, viewer=gang.owner)
        self._lengthen(gang, vex, 60)
        long = Gang.objects.get(pk=gang.pk)
        with django_assert_num_queries(2):
            history.latest(long, viewer=gang.owner)

    def test_it_reads_only_the_last_stretch_of_events(self, gang, vex):
        """The window is counted in events because acts are made of them.
        Asked for more acts than the stretch holds, it gives what the
        stretch tells and no more — where the whole story has them all."""
        self._lengthen(gang, vex, history.SNAPSHOT_WINDOW + 20)
        whole = Gang.objects.get(pk=gang.pk)

        snapshot = history.latest(whole, limit=1000, viewer=gang.owner)
        assert len(snapshot) <= history.SNAPSHOT_WINDOW
        assert len(history.build(whole, viewer=gang.owner)) > len(snapshot)


class TestThePageIsTheOwners:
    """The history says things the roster does not, so only the owner
    reads it — and every narrowing is an address."""

    def test_the_owner_reads_it(self, client, gang, vex):
        client.force_login(gang.owner)
        response = client.get(reverse("n26-gang-history", args=[gang.pk]))
        assert response.status_code == 200
        page = response.content.decode()
        assert "hired" in page
        assert "Vex" in page

    def test_a_stranger_is_told_nothing_is_here(self, client, gang):
        client.force_login(User.objects.create_user("a-stranger"))
        response = client.get(reverse("n26-gang-history", args=[gang.pk]))
        assert response.status_code == 404

    def test_a_signed_out_reader_is_sent_to_sign_in(self, client, gang):
        response = client.get(reverse("n26-gang-history", args=[gang.pk]))
        assert response.status_code == 302

    def test_a_long_story_is_read_a_page_at_a_time(self, client, gang, vex):
        """A gang played for a season has more acts than a screen holds,
        and the pager keeps whatever question the reader asked."""
        from n26.core.views.history import PER_PAGE

        for number in range(PER_PAGE + 2):
            with edit(gang) as op:
                op.rename(vex, f"Vex {number}")
        client.force_login(gang.owner)
        at = reverse("n26-gang-history", args=[gang.pk])
        first = client.get(at)
        assert first.context["shown"] == PER_PAGE
        assert first.context["pages"]["of"] == 2
        # The pager is really drawn, not merely computed — and the end
        # it cannot go to is dead rather than a live link to nowhere.
        drawn = first.content.decode()
        assert "page=2" in drawn
        back = drawn[drawn.index('aria-label="Previous page"') - 200 :][:400]
        assert "pointer-events-none" in back
        second = client.get(at, {"page": 2, "q": "renamed"})
        assert second.status_code == 200
        assert "q=renamed" in second.context["pages"]["previous"]
        assert "Page 2 of 2" in second.content.decode()

    def test_the_filters_narrow_and_the_address_says_how(self, client, gang, vex):
        with edit(gang) as op:
            op.rename(vex, "Vex the Bold")
        client.force_login(gang.owner)
        at = reverse("n26-gang-history", args=[gang.pk])
        money = client.get(at, {"kind": "money"}).content.decode()
        assert "hired" in money
        assert "renamed" not in money
        searched = client.get(at, {"q": "renamed"}).content.decode()
        assert "renamed" in searched
        assert "hired" not in searched
        # Enter in this box commits the GET search. A live filter would
        # swallow it; this bar is the form's own field.
        page = client.get(at).content.decode()
        assert 'role="search"' in page
        assert "@keydown.enter.prevent" not in page
