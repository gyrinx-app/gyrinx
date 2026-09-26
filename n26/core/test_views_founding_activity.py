"""The Spend built-in TP action: opened at founding, closed by hand.

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
from n26.core.models import Activity, Gang, LedgerEvent
from n26.core.operations import Refusal, operation
from n26.tests.fixtures import admit_to_founding

pytestmark = pytest.mark.django_db

FOUNDING = Activity.Kind.FOUNDING

#: The colour <c-n26.founding-mark> paints itself. One component draws the
#: mark, so finding this on a page is finding the mark; change it there and
#: change it here.
MARK = "text-violet-600"

#: What the tooltip says where a visit cannot be started yet.
ONE_AT_A_TIME = "You can have only one of these actions open at a time."


@pytest.fixture
def tester(db):
    """The signed-in person these tests look at the app as."""
    # On the founding flag's allowlist, because the square and its address
    # reach the owners it admits; the owner it does not has tests of their own.
    person = User.objects.create_user("player")
    admit_to_founding(person)
    return person


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
        op.open_activity(Activity.Kind.FOUNDING)
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


class TestStartingTheAction:
    """Most gangs never spend built-in Trade Points, so founding a gang
    opens nothing. The owner starts the action from the Actions square and
    closes it when they are done."""

    def test_founding_a_gang_opens_nothing(self, tester, gang_type):
        fresh = Gang.objects.create(
            name="The Quiet Ones",
            owner=tester,
            gang_type=gang_type,
            starting_credits=1000,
            credits=1000,
        )
        with operation(fresh, actor=tester) as op:
            op.found(gang_type)

        assert fresh.open_activity(FOUNDING) is None
        assert not Activity.objects.filter(gang=fresh).exists()

    def test_starting_it_opens_the_action(self, gang):
        open_now = gang.open_activity(FOUNDING)
        assert open_now is not None
        assert open_now.kind == FOUNDING
        assert open_now.is_open

    def test_the_opening_event_is_what_the_row_points_at(self, gang):
        open_now = gang.open_activity(FOUNDING)
        assert open_now.opened.kind == LedgerEvent.Kind.ACTION_OPENED
        assert open_now.opened.gang_id == gang.pk
        assert open_now.opened.note == FOUNDING

    def test_it_brings_no_trade_points(self, gang):
        """Founding hands out nothing of its own — a visit is the kind
        that does."""
        assert gang.open_activity(FOUNDING).trade_points is None

    def test_a_gang_type_corrected_keeps_the_action_it_has(
        self, gang, tester, gang_type
    ):
        """Founding again is how a gang whose founding assignment had gone
        gets its type back. The action it already has stands."""
        with operation(gang, actor=tester) as op:
            op.found(gang_type)

        assert Activity.objects.filter(gang=gang, kind=FOUNDING).count() == 1


class TestOneAtATime:
    def test_a_second_open_of_the_same_kind_is_refused(self, gang, tester):
        with pytest.raises(Refusal) as refused:
            with operation(gang, actor=tester) as op:
                op.open_activity(FOUNDING)

        assert "Spend built-in TP" in str(refused.value)

    def test_the_refusal_leaves_nothing_behind(self, gang, tester):
        """It is raised inside the operation, so the event it would have
        written unwinds with everything else."""
        before = LedgerEvent.objects.filter(gang=gang).count()
        with pytest.raises(Refusal):
            with operation(gang, actor=tester) as op:
                op.open_activity(FOUNDING)

        assert LedgerEvent.objects.filter(gang=gang).count() == before

    def test_the_database_holds_the_same_line(self, gang):
        """The refusal is a sentence for the player; the constraint is what
        makes two open actions impossible however they were written."""
        open_now = gang.open_activity(FOUNDING)
        with pytest.raises(IntegrityError), transaction.atomic():
            Activity.objects.create(gang=gang, kind=FOUNDING, opened=open_now.opened)

    def test_another_kind_may_be_open_beside_it(self, gang, tester):
        with operation(gang, actor=tester) as op:
            op.open_activity(Activity.Kind.TRADING_POST_VISIT, trade_points=3)

        assert gang.open_activity(FOUNDING) is not None
        assert gang.open_activity(Activity.Kind.TRADING_POST_VISIT).trade_points == 3


class TestClosingAndStartingAgain:
    def test_closing_names_the_event_that_closed_it(self, gang, tester):
        open_now = gang.open_activity(FOUNDING)
        with operation(gang, actor=tester) as op:
            op.close_activity(open_now)

        open_now.refresh_from_db()
        assert open_now.closed.kind == LedgerEvent.Kind.ACTION_CLOSED
        assert not open_now.is_open
        assert gang.open_activity(FOUNDING) is None

    def test_closing_one_already_closed_writes_nothing(self, gang, tester):
        """Two clicks on one button arrive together often enough. The
        second holds a copy read before the gang's line was taken and
        still says open, so the act reads the row again and stands down."""
        stale = gang.open_activity(FOUNDING)
        with operation(gang, actor=tester) as op:
            op.close_activity(stale)
        before = LedgerEvent.objects.filter(gang=gang).count()

        with operation(gang, actor=tester) as op:
            assert op.close_activity(stale) is None

        assert LedgerEvent.objects.filter(gang=gang).count() == before

    def test_another_gangs_action_is_not_this_operations_to_close(
        self, gang, tester, gang_type
    ):
        """An operation is opened on one gang and writes that gang's
        history. Handed an action belonging to another, it closes
        nothing rather than ending their act and filing the ending under
        the wrong name."""
        theirs = Gang.objects.create(
            name="The Rust Sermon",
            owner=tester,
            gang_type=gang_type,
            starting_credits=1000,
            credits=1000,
        )
        with operation(theirs, actor=tester) as op:
            op.found(gang_type)
            op.open_activity(FOUNDING)
        open_now = theirs.open_activity(FOUNDING)
        before = LedgerEvent.objects.filter(gang=theirs).count()

        with operation(gang, actor=tester) as op:
            assert op.close_activity(open_now) is None

        open_now.refresh_from_db()
        assert open_now.is_open
        assert theirs.open_activity(FOUNDING) is not None
        assert LedgerEvent.objects.filter(gang=theirs).count() == before
        assert not LedgerEvent.objects.filter(
            gang=gang, kind=LedgerEvent.Kind.ACTION_CLOSED
        ).exists()

    def test_a_closed_action_may_be_started_again(self, gang, tester):
        with operation(gang, actor=tester) as op:
            op.close_activity(gang.open_activity(FOUNDING))
        with operation(gang, actor=tester) as op:
            op.open_activity(FOUNDING)

        assert gang.open_activity(FOUNDING) is not None
        assert Activity.objects.filter(gang=gang, kind=FOUNDING).count() == 2


class TestTheHistoryReadsIt:
    def test_both_events_reach_the_history_as_sentences(self, gang, tester):
        with operation(gang, actor=tester) as op:
            op.close_activity(gang.open_activity(FOUNDING))

        lines = told(gang)
        assert "started the Spend built-in TP action" in lines
        assert "completed the Spend built-in TP action" in lines

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
            op.close_activity(gang.open_activity(FOUNDING))

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
            op.close_activity(gang.open_activity(FOUNDING))
        with operation(gang, actor=tester) as op:
            op.open_activity(FOUNDING)

        entries = list(LedgerEntry.objects.filter(assignment__gang_root=gang))
        assert entries
        assert [problem for entry in entries for problem in check_entry(entry)] == []

    def test_the_gang_still_has_every_credit_it_was_founded_with(self, gang, tester):
        with operation(gang, actor=tester) as op:
            op.close_activity(gang.open_activity(FOUNDING))

        gang.refresh_from_db()
        assert gang.credits == 1000


class TestTheSquareOnTheGangPage:
    """The Actions square: what the gang has open, in the first square of
    the roster grid, and the plain control that starts something."""

    @pytest.fixture(autouse=True)
    def signed_in(self, client, tester):
        client.force_login(tester)

    def test_an_open_activity_is_drawn_with_a_way_to_complete_it(self, client, gang):
        body = client.get(sheet(gang)).content.decode()
        assert "Spend built-in TP" in body
        assert "Complete action" in body
        assert "Click when you have finished hiring and equipping the gang." in body
        assert f'action="{act_page(gang)}"' in body

    def test_the_action_is_marked(self, client, gang):
        """The founding mark stands beside the title — the same mark the
        model cards and the allowance block carry, so a reader meets one
        feature rather than three unrelated screens."""
        body = client.get(sheet(gang)).content.decode()
        title = body.index("Spend built-in TP")

        assert MARK in body[body.rindex("<h3", 0, title) : title]

    def test_the_title_is_followed_by_what_the_action_allows(self, client, gang):
        body = client.get(sheet(gang)).content.decode()

        assert (
            "While this action is open, fighters with founding Trade Points can "
            "spend them at the Trading Post." in body
        )

    def test_the_start_button_names_what_it_lets_you_do(self, client, gang, tester):
        """Nobody sets out to open an action; they set out to equip the
        gang. The mark ties the control to the figures it brings."""
        with operation(gang, actor=tester) as op:
            op.close_activity(gang.open_activity(FOUNDING))

        body = client.get(sheet(gang)).content.decode()
        label = body.index("Spend built-in TP")

        assert MARK in body[body.rindex("<button", 0, label) : label]
        assert body.index("Equip the gang using founding Trade Points.") < label

    def test_the_open_activity_is_badged_as_the_current_one(self, client, gang):
        body = client.get(sheet(gang)).content.decode()
        assert "Current action" in body

    def test_the_header_holds_the_title_alone(self, client, gang):
        """No menu in the header: the square's header stays the height of
        the stash card's beside it."""
        body = client.get(sheet(gang)).content.decode()
        assert "More actions" not in body[body.index(">Actions<") :][:600]

    def test_the_start_control_goes_while_one_is_open(self, client, gang):
        """A gang performs one of each action at a time, so a control that
        would be refused is a control that should not be there."""
        body = client.get(sheet(gang)).content.decode()
        assert "Equip the gang using founding Trade Points" not in body

    def test_a_completed_action_leaves_the_way_to_start_another(
        self, client, gang, tester
    ):
        with operation(gang, actor=tester) as op:
            op.close_activity(gang.open_activity(FOUNDING))

        body = client.get(sheet(gang)).content.decode()
        assert "No action is open." in body
        assert "Equip the gang using founding Trade Points" in body
        assert "Complete action" not in body

    def test_the_start_row_posts_rather_than_links(self, client, gang, tester):
        """A link is followed by anything that follows links, and a reload
        would start the action again."""
        with operation(gang, actor=tester) as op:
            op.close_activity(gang.open_activity(FOUNDING))

        body = client.get(sheet(gang)).content.decode()
        start = body.index("Spend built-in TP")
        form = body.rindex("<form", 0, start)
        assert 'method="post"' in body[form:start]
        assert f'action="{act_page(gang)}"' in body[form:start]

    def plain_start_form(self, body, after):
        """The start form drawn in the square's body, following ``after``."""
        start = body.index('value="start"', body.index(after))
        return body[body.rindex("<form", 0, start) : start]

    def test_an_empty_square_starts_one_without_scripting(self, client, gang, tester):
        """The start control is a plain form in the square's body. One
        form, one act."""
        with operation(gang, actor=tester) as op:
            op.close_activity(gang.open_activity(FOUNDING))

        body = client.get(sheet(gang)).content.decode()
        form = self.plain_start_form(body, "No action is open.")
        assert 'method="post"' in form
        assert f'action="{act_page(gang)}"' in form
        assert body.count('value="start"') == 1

    def test_a_visit_open_does_not_take_that_control_away(self, client, gang, tester):
        """The plain control is drawn whenever the founding action is not
        open, whatever else the gang has going on. A visit is not the
        founding action."""
        with operation(gang, actor=tester) as op:
            op.close_activity(gang.open_activity(FOUNDING))
        with operation(gang, actor=tester) as op:
            op.visit_trading_post(brought=3)

        body = client.get(sheet(gang)).content.decode()
        assert "Trading Post visit open" in body
        assert "No action is open." not in body
        form = self.plain_start_form(body, "Trading Post visit open")
        assert 'method="post"' in form
        assert f'action="{act_page(gang)}"' in form
        assert body.count('value="start"') == 1

    def test_an_open_founding_action_takes_the_control_away(self, client, gang):
        """Nothing offers an act that would be refused: one of each kind
        at a time, so the start button is not there."""
        body = client.get(sheet(gang)).content.decode()
        assert "Equip the gang using founding Trade Points" not in body
        assert 'value="start"' not in body

    def test_the_square_leads_the_grid(self, client, gang):
        body = client.get(sheet(gang)).content.decode()
        assert body.index("Spend built-in TP") < body.index("Nothing in the stash")

    def test_a_reader_who_does_not_own_it_gets_no_square(self, client, gang):
        """The roster is theirs to read; the gang's actions are not."""
        client.force_login(User.objects.create_user("stranger"))
        body = client.get(sheet(gang)).content.decode()
        assert "Spend built-in TP" not in body
        assert "Complete action" not in body

    def test_the_flag_open_to_everyone_admits_no_reader_but_the_owner(
        self, client, gang
    ):
        """Opening the flag widens who among owners sees their own square;
        it never puts another gang's actions in front of a reader."""
        from gyrinx.site.models import Availability, FeatureFlag

        FeatureFlag.objects.filter(slug="founding").update(
            availability=Availability.EVERYONE
        )
        client.force_login(User.objects.create_user("stranger"))
        body = client.get(sheet(gang)).content.decode()
        assert "Spend built-in TP" not in body
        assert 'value="start"' not in body
        assert "No action is open." not in body

    def test_an_owner_the_flag_does_not_admit_gets_no_square(self, client, gang):
        """Outside the founding flag's allowlist the owner reads the gang
        page as it was before the square, and the open action stays open
        behind it."""
        plain = User.objects.create_user("plain-player")
        gang.owner = plain
        gang.save(update_fields=["owner"])
        client.force_login(plain)
        body = client.get(sheet(gang)).content.decode()
        assert "Spend built-in TP" not in body
        assert "No action is open." not in body
        assert 'value="start"' not in body
        assert "Nothing in the stash" in body
        assert gang.open_activity(FOUNDING) is not None

    def test_the_stash_card_cannot_start_a_visit_beside_it(self, client, gang):
        """A gang holds one action of each kind. The stash card's way into
        a Trading Post visit is drawn dead, with the reason, rather than
        leading to a page that would refuse."""
        body = client.get(sheet(gang)).content.decode()
        label = body.index("Set up Trading Post visit")
        control = body[body.rindex("<", 0, body.rindex("<", 0, label)) : label]

        assert "disabled" in control
        assert ONE_AT_A_TIME in body
        assert "Set up TP visit" not in body

    def test_the_dead_button_lets_the_pointer_reach_its_tooltip(self, client, gang):
        """A disabled control emits no mouse events, so left bare it would
        be the pointer's target and the tooltip around it would never
        open. The button is drawn inert inside a span, and the span is
        what the pointer hits. The tooltip's own words are in the page
        either way, so nothing else here can catch this."""
        body = client.get(sheet(gang)).content.decode()
        label = body.index("Set up Trading Post visit")
        control = body[body.rindex("<", 0, body.rindex("<", 0, label)) : label]

        assert "pointer-events-none" in control
        assert control.lstrip().startswith("<span")
        assert "cursor-not-allowed" in control
        # The reason again, off screen: a tooltip that only opens
        # under a pointer leaves everybody else a dead button.
        assert 'aria-describedby="n26-visit-shut-stash"' in control

    def test_completing_the_founding_opens_the_way_to_a_visit(
        self, client, gang, tester
    ):
        with operation(gang, actor=tester) as op:
            op.close_activity(gang.open_activity(FOUNDING))

        body = client.get(sheet(gang)).content.decode()
        label = body.index("Set up Trading Post visit")
        control = body[body.rindex("<", 0, body.rindex("<", 0, label)) : label]

        assert "disabled" not in control
        assert reverse("n26-gang-trade-points", args=[gang.pk]) in control
        assert ONE_AT_A_TIME not in body

    def test_an_owner_the_founding_does_not_reach_keeps_the_way_in(self, client, gang):
        """Every gang carries an open founding action, and an owner the
        feature has not reached is given no way to close one — so shutting
        the button for them would take visits away with nothing offered in
        their place."""
        plain = User.objects.create_user("plain-player")
        gang.owner = plain
        gang.save(update_fields=["owner"])
        client.force_login(plain)

        body = client.get(sheet(gang)).content.decode()
        label = body.index("Set up Trading Post visit")
        control = body[body.rindex("<", 0, body.rindex("<", 0, label)) : label]

        assert "disabled" not in control
        assert reverse("n26-gang-trade-points", args=[gang.pk]) in control
        assert ONE_AT_A_TIME not in body

    def test_the_square_costs_the_page_nothing_per_fighter(
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


class TestTheStoryUnderIt:
    """The square links to the gang's history and does not list acts.

    What has been done is on the history page. The square is for what
    is open and what is waiting.
    """

    @pytest.fixture(autouse=True)
    def signed_in(self, client, tester):
        client.force_login(tester)

    def panel(self, client, gang):
        from bs4 import BeautifulSoup

        document = BeautifulSoup(client.get(sheet(gang)).content, "html.parser")
        return document.select_one('[role="region"][aria-label="Actions"]')

    def test_the_sheet_does_not_list_acts(self, client, gang):
        panel = self.panel(client, gang)
        text = panel.get_text()
        assert "Recent history" not in text
        assert "started the Spend built-in TP action" not in text
        assert "created the gang" not in text

    def test_hires_are_not_listed_on_the_square(
        self, client, gang, tester, make_profile, make_statline
    ):
        """A long story stays on the history page. Listing it here would
        push the roster off the screen."""
        profile = make_profile("Ganger", price=10)
        make_statline(profile)
        for name in ("Ain", "Bex", "Cor", "Dax", "Eth", "Fen"):
            with operation(gang, actor=tester) as op:
                op.hire(profile, name)

        text = self.panel(client, gang).get_text()
        assert "hired " not in text

    def test_the_way_through_to_the_whole_story_is_there(self, client, gang):
        link = self.panel(client, gang).find(
            "a", href=reverse("n26-gang-history", args=[gang.pk])
        )
        assert link.get_text(strip=True) == "History"

    def test_a_gang_nothing_has_been_done_to_still_links(
        self, client, tester, gang_type
    ):
        """A row written with no operation behind it still has the way
        through. The history page is where an empty story is said."""
        bare = Gang.objects.create(
            name="The Rust Sermon",
            owner=tester,
            gang_type=gang_type,
            starting_credits=1000,
            credits=1000,
        )

        panel = self.panel(client, bare)
        assert "No history for this gang yet." not in panel.get_text()
        assert panel.find("a", href=reverse("n26-gang-history", args=[bare.pk]))

    def test_a_reader_who_does_not_own_it_gets_none_of_it(self, client, gang):
        client.force_login(User.objects.create_user("stranger"))
        body = client.get(sheet(gang)).content.decode()
        assert self.panel(client, gang) is None
        assert reverse("n26-gang-history", args=[gang.pk]) not in body
        assert "started the Spend built-in TP action" not in body


class TestWhatTheSquareCosts:
    """The square is a fixed number of reads, whatever the gang.

    A page's query count is an invariant here: neither a roster that grew
    nor a story that got longer may add one.
    """

    def test_it_is_pinned_at_one_read(self, gang, django_assert_num_queries):
        """Which actions the gang has open.

        The sheet is built first, from a row of its own, so its reads are
        not counted here — a gang holds what it read about its own open
        actions, and one already asked would hide a read this makes.
        The history page is a link, so the square does not read the story.
        """
        from n26.core.activities import activities_square
        from n26.core.render import render_gang

        sheet_of = render_gang(Gang.objects.get(pk=gang.pk))
        fresh = Gang.objects.get(pk=gang.pk)

        with django_assert_num_queries(1):
            activities_square(
                fresh,
                sheet_of,
                founding_at=act_page(fresh),
                visit_at="/visit",
                history_at="/history",
            )

    def test_a_longer_story_costs_the_page_nothing_more(
        self, client, gang, tester, make_profile, make_statline
    ):
        """The square does not read the story, so a gang played for a
        season draws its page for what a new one pays."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        client.force_login(tester)
        profile = make_profile("Ganger", price=1)
        make_statline(profile)
        with operation(gang, actor=tester) as op:
            model = op.hire(profile, "Vex")

        def measure():
            with CaptureQueriesContext(connection) as captured:
                assert client.get(sheet(gang)).status_code == 200
            return len(captured.captured_queries)

        measure()
        short = measure()
        for number in range(60):
            with operation(gang, actor=tester) as op:
                op.rename(model, f"Vex {number}")

        assert measure() == short


class TestTheActsBehindIt:
    @pytest.fixture(autouse=True)
    def signed_in(self, client, tester):
        client.force_login(tester)

    def test_completing_it_closes_the_action(self, client, gang):
        answer = client.post(act_page(gang), {"act": "finish"}, follow=True)

        assert gang.open_activity(FOUNDING) is None
        lines = [str(m) for m in answer.context["messages"]]
        assert "Completed the Spend built-in TP action." in lines

    def test_a_gang_past_its_budget_is_told_so_rather_than_broken(
        self, client, gang, tester, make_profile, make_statline
    ):
        """Every operation ends by rewriting the gang's credits, and a
        gang whose budget was lowered under what it had already spent is
        refused there — even by an act that moves no money. The reader
        gets the sentence and the page back."""
        profile = make_profile("Ganger", price=500)
        make_statline(profile)
        with operation(gang, actor=tester) as op:
            op.hire(profile, "Vex")
        # Written straight to the column, as the admin writes it: the
        # operation that would lower the budget is refused by the same
        # rule this is about.
        Gang.objects.filter(pk=gang.pk).update(starting_credits=100)

        answer = client.post(act_page(gang), {"act": "finish"}, follow=True)

        assert answer.status_code == 200
        assert answer.redirect_chain == [(sheet(gang), 302)]
        assert gang.open_activity(FOUNDING) is not None
        lines = [str(m) for m in answer.context["messages"]]
        assert any("Not enough credits" in line for line in lines)

    def test_starting_one_opens_it_again(self, client, gang, tester):
        with operation(gang, actor=tester) as op:
            op.close_activity(gang.open_activity(FOUNDING))

        answer = client.post(act_page(gang), {"act": "start"}, follow=True)

        assert gang.open_activity(FOUNDING) is not None
        lines = [str(m) for m in answer.context["messages"]]
        assert "Started the Spend built-in TP action." in lines

    def test_starting_one_while_one_is_open_is_told_no(self, client, gang):
        """The card offers the other control, so this is a stale page
        rather than an intention — and it changes nothing."""
        opened = gang.open_activity(FOUNDING)
        answer = client.post(act_page(gang), {"act": "start"}, follow=True)

        assert gang.open_activity(FOUNDING).pk == opened.pk
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
        assert gang.open_activity(FOUNDING) is not None

    def test_somebody_elses_gang_is_not_theirs_to_act_on(self, client, gang):
        client.force_login(User.objects.create_user("stranger"))
        assert client.post(act_page(gang), {"act": "finish"}).status_code == 404

    def test_an_owner_the_flag_does_not_admit_cannot_reach_the_address(
        self, client, gang
    ):
        plain = User.objects.create_user("plain-player")
        gang.owner = plain
        gang.save(update_fields=["owner"])
        client.force_login(plain)
        assert client.post(act_page(gang), {"act": "finish"}).status_code == 404
        assert gang.open_activity(FOUNDING) is not None

    def test_signing_in_is_required(self, client, gang):
        client.logout()
        assert client.post(act_page(gang), {"act": "finish"}).status_code == 302
