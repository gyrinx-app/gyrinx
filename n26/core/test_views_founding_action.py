"""The Found and equip gang action: opened at founding, closed by hand.

An action is a thing a gang is part-way through, and this is the first of
them. Founding opens one; the card on the gang page completes it; the same
card starts another once it is done. What these pin is that the state is
the database's rather than any screen's, that the two events reach the
history as sentences, and that neither event touches the money the ledger
is checked by.
"""

import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.urls import reverse

from n26.core import history
from n26.core.models import Action, Gang, LedgerEvent
from n26.core.operations import Refusal, operation

pytestmark = pytest.mark.django_db

FOUNDING = Action.Kind.FOUNDING


@pytest.fixture
def tester(db):
    """The signed-in person these tests look at the app as."""
    return User.objects.create_user("player")


@pytest.fixture
def gang(tester, gang_type):
    gang = Gang.objects.create(
        name="The Ashen Choir",
        owner=tester,
        gang_type=gang_type,
        starting_credits=1000,
        credits=1000,
    )
    with operation(gang, actor=tester) as op:
        op.found(gang_type)
    gang.refresh_from_db()
    return gang


def act_page(gang):
    return reverse("n26-gang-founding-action", args=[gang.pk])


def sheet(gang):
    return reverse("n26-gang", args=[gang.pk])


def told(gang, viewer=None):
    """Every act in the gang's history, as the sentences a reader gets."""
    return [
        "".join(span.text for span in act.spans) for act in history.build(gang, viewer)
    ]


class TestFoundingOpensOne:
    """Founding and equipping a gang is performed over many clicks, so the
    act that founds it opens the action the owner closes when they are
    done."""

    def test_founding_a_gang_opens_the_action(self, gang):
        open_now = gang.open_action(FOUNDING)
        assert open_now is not None
        assert open_now.kind == FOUNDING
        assert open_now.is_open

    def test_the_opening_event_is_what_the_row_points_at(self, gang):
        open_now = gang.open_action(FOUNDING)
        assert open_now.opened.kind == LedgerEvent.Kind.ACTION_OPENED
        assert open_now.opened.gang_id == gang.pk
        assert open_now.opened.note == FOUNDING

    def test_it_brings_no_trade_points(self, gang):
        """Founding hands out nothing of its own — a visit is the kind
        that does."""
        assert gang.open_action(FOUNDING).trade_points is None

    def test_a_gang_type_corrected_keeps_the_action_it_has(
        self, gang, tester, gang_type
    ):
        """Founding again is how a gang whose founding assignment had gone
        gets its type back. The action it already has stands."""
        with operation(gang, actor=tester) as op:
            op.found(gang_type)

        assert Action.objects.filter(gang=gang, kind=FOUNDING).count() == 1


class TestOneAtATime:
    def test_a_second_open_of_the_same_kind_is_refused(self, gang, tester):
        with pytest.raises(Refusal) as refused:
            with operation(gang, actor=tester) as op:
                op.open_action(FOUNDING)

        assert "Found and equip gang" in str(refused.value)

    def test_the_refusal_leaves_nothing_behind(self, gang, tester):
        """It is raised inside the operation, so the event it would have
        written unwinds with everything else."""
        before = LedgerEvent.objects.filter(gang=gang).count()
        with pytest.raises(Refusal):
            with operation(gang, actor=tester) as op:
                op.open_action(FOUNDING)

        assert LedgerEvent.objects.filter(gang=gang).count() == before

    def test_the_database_holds_the_same_line(self, gang):
        """The refusal is a sentence for the player; the constraint is what
        makes two open actions impossible however they were written."""
        open_now = gang.open_action(FOUNDING)
        with pytest.raises(IntegrityError), transaction.atomic():
            Action.objects.create(gang=gang, kind=FOUNDING, opened=open_now.opened)

    def test_another_kind_may_be_open_beside_it(self, gang, tester):
        with operation(gang, actor=tester) as op:
            op.open_action(Action.Kind.TRADING_POST_VISIT, trade_points=3)

        assert gang.open_action(FOUNDING) is not None
        assert gang.open_action(Action.Kind.TRADING_POST_VISIT).trade_points == 3


class TestClosingAndStartingAgain:
    def test_closing_names_the_event_that_closed_it(self, gang, tester):
        open_now = gang.open_action(FOUNDING)
        with operation(gang, actor=tester) as op:
            op.close_action(open_now)

        open_now.refresh_from_db()
        assert open_now.closed.kind == LedgerEvent.Kind.ACTION_CLOSED
        assert not open_now.is_open
        assert gang.open_action(FOUNDING) is None

    def test_closing_one_already_closed_writes_nothing(self, gang, tester):
        """Two clicks on one button arrive together often enough. The
        second holds a copy read before the gang's line was taken and
        still says open, so the act reads the row again and stands down."""
        stale = gang.open_action(FOUNDING)
        with operation(gang, actor=tester) as op:
            op.close_action(stale)
        before = LedgerEvent.objects.filter(gang=gang).count()

        with operation(gang, actor=tester) as op:
            assert op.close_action(stale) is None

        assert LedgerEvent.objects.filter(gang=gang).count() == before

    def test_a_closed_action_may_be_started_again(self, gang, tester):
        with operation(gang, actor=tester) as op:
            op.close_action(gang.open_action(FOUNDING))
        with operation(gang, actor=tester) as op:
            op.open_action(FOUNDING)

        assert gang.open_action(FOUNDING) is not None
        assert Action.objects.filter(gang=gang, kind=FOUNDING).count() == 2


class TestTheHistoryReadsIt:
    def test_both_events_reach_the_history_as_sentences(self, gang, tester):
        with operation(gang, actor=tester) as op:
            op.close_action(gang.open_action(FOUNDING))

        lines = told(gang)
        assert "started the Found and equip gang action" in lines
        assert "completed the Found and equip gang action" in lines

    def test_the_kind_it_holds_is_never_printed_as_a_note(self, gang):
        """The note is a record for the code — the sentence has already
        said which action it was."""
        opened = next(
            act for act in history.build(gang) if "started the" in act.spans[0].text
        )
        assert opened.note == ""
        assert opened.category == "gang"

    def test_it_moves_no_money(self, gang, tester):
        with operation(gang, actor=tester) as op:
            op.close_action(gang.open_action(FOUNDING))

        marks = [LedgerEvent.Kind.ACTION_OPENED, LedgerEvent.Kind.ACTION_CLOSED]
        events = list(LedgerEvent.objects.filter(gang=gang, kind__in=marks))
        assert len(events) == 2
        for event in events:
            assert event.assignment_id is None
            assert event.miniature_id is None
            assert (
                event.credits_delta,
                event.trade_points_delta,
                event.rating_delta,
            ) == (0, 0, 0)


class TestTheLedgerIsUnaffected:
    def test_folding_every_entry_still_reproduces_it(self, gang, tester):
        """The two events are about the gang rather than an assignment, so
        the money invariant never sees them."""
        from n26.core.models import LedgerEntry
        from n26.core.reconcile import check_entry

        with operation(gang, actor=tester) as op:
            op.close_action(gang.open_action(FOUNDING))
        with operation(gang, actor=tester) as op:
            op.open_action(FOUNDING)

        entries = list(LedgerEntry.objects.filter(assignment__gang_root=gang))
        assert entries
        assert [problem for entry in entries for problem in check_entry(entry)] == []

    def test_the_gang_still_has_every_credit_it_was_founded_with(self, gang, tester):
        with operation(gang, actor=tester) as op:
            op.close_action(gang.open_action(FOUNDING))

        gang.refresh_from_db()
        assert gang.credits == 1000


class TestTheCardOnTheGangPage:
    @pytest.fixture(autouse=True)
    def signed_in(self, client, tester):
        client.force_login(tester)

    def test_an_open_action_is_a_card_with_a_way_to_complete_it(self, client, gang):
        body = client.get(sheet(gang)).content.decode()
        assert "Found and equip gang" in body
        assert "Complete action" in body
        assert "Click when you have finished hiring and equipping the gang." in body
        assert f'action="{act_page(gang)}"' in body

    def test_a_completed_action_leaves_the_way_to_start_another(
        self, client, gang, tester
    ):
        with operation(gang, actor=tester) as op:
            op.close_action(gang.open_action(FOUNDING))

        body = client.get(sheet(gang)).content.decode()
        assert "Start the Found and equip gang action" in body
        assert "Complete action" not in body

    def test_a_reader_who_does_not_own_it_gets_neither(self, client, gang):
        """The roster is theirs to read; the gang's actions are not."""
        client.force_login(User.objects.create_user("stranger"))
        body = client.get(sheet(gang)).content.decode()
        assert "Found and equip gang" not in body
        assert "Complete action" not in body

    def test_the_card_costs_the_page_nothing_per_fighter(
        self, client, gang, tester, make_profile, make_statline
    ):
        """The page asks the gang for its open action once, whatever the
        roster: the count is the same for one fighter and for four.

        Measured after a first request rather than on it, because the
        session's own bookkeeping is written on the way in and the count
        being pinned here is the page's.
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        profile = make_profile("Ganger", price=50)
        make_statline(profile)

        def hire(name):
            with operation(gang, actor=tester) as op:
                op.hire(profile, name)

        def measure():
            with CaptureQueriesContext(connection) as captured:
                assert client.get(sheet(gang)).status_code == 200
            return len(captured.captured_queries)

        hire("Vex")
        measure()
        few = measure()
        for name in ("Sull", "Nix", "Sura"):
            hire(name)
        assert measure() == few


class TestTheActsBehindIt:
    @pytest.fixture(autouse=True)
    def signed_in(self, client, tester):
        client.force_login(tester)

    def test_completing_it_closes_the_action(self, client, gang):
        answer = client.post(act_page(gang), {"act": "finish"}, follow=True)

        assert gang.open_action(FOUNDING) is None
        lines = [str(m) for m in answer.context["messages"]]
        assert "Completed the Found and equip gang action." in lines

    def test_starting_one_opens_it_again(self, client, gang, tester):
        with operation(gang, actor=tester) as op:
            op.close_action(gang.open_action(FOUNDING))

        answer = client.post(act_page(gang), {"act": "start"}, follow=True)

        assert gang.open_action(FOUNDING) is not None
        lines = [str(m) for m in answer.context["messages"]]
        assert "Started the Found and equip gang action." in lines

    def test_starting_one_while_one_is_open_is_told_no(self, client, gang):
        """The card offers the other control, so this is a stale page
        rather than an intention — and it changes nothing."""
        opened = gang.open_action(FOUNDING)
        answer = client.post(act_page(gang), {"act": "start"}, follow=True)

        assert gang.open_action(FOUNDING).pk == opened.pk
        lines = [str(m) for m in answer.context["messages"]]
        assert any("Complete the open" in line for line in lines)

    def test_completing_one_that_is_already_done_changes_nothing(self, client, gang):
        client.post(act_page(gang), {"act": "finish"})
        before = LedgerEvent.objects.filter(gang=gang).count()

        client.post(act_page(gang), {"act": "finish"})

        assert LedgerEvent.objects.filter(gang=gang).count() == before

    def test_following_a_link_here_acts_on_nothing(self, client, gang):
        answer = client.get(act_page(gang))

        assert answer.status_code == 302
        assert answer["Location"] == sheet(gang)
        assert gang.open_action(FOUNDING) is not None

    def test_somebody_elses_gang_is_not_theirs_to_act_on(self, client, gang):
        client.force_login(User.objects.create_user("stranger"))
        assert client.post(act_page(gang), {"act": "finish"}).status_code == 404

    def test_signing_in_is_required(self, client, gang):
        client.logout()
        assert client.post(act_page(gang), {"act": "finish"}).status_code == 302
