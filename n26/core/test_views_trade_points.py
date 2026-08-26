"""The Visit Trading Post action: the open one, and starting another.

Two posts and no query string. Starting names the fighters who perform
the action and takes what they bring; finishing shuts the post and loses
whatever is left, which is the book's rule rather than this screen's
idea. What the page must get right is that neither is a GET — following
a link must not open or close an action — and that the receipt is read
from the ledger rather than kept as a second copy of it.
"""

import re

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.models import Gang, LedgerEvent
from n26.core.operations import operation
from n26.library.models import Subtype

pytestmark = pytest.mark.django_db


@pytest.fixture
def tester(db):
    return User.objects.create_user("player")


@pytest.fixture
def gang(tester, gang_type):
    return Gang.objects.create(
        name="The Ashen Choir",
        owner=tester,
        gang_type=gang_type,
        starting_credits=1000,
        credits=1000,
    )


@pytest.fixture
def ranks(db):
    """The two ranks the book gives Trade Points to."""
    return {name: Subtype.objects.create(name=name) for name in ("Leader", "Champion")}


@pytest.fixture
def roster(tester, gang, ranks, make_profile, make_statline):
    """A Leader, a Champion and a Ganger, who brings nothing but may go."""
    made = {}
    for name, rank in [("Vex", "Leader"), ("Sura", "Champion"), ("Nix", None)]:
        profile = make_profile(f"{name} entry", price=50)
        make_statline(profile)
        with operation(gang, actor=tester) as op:
            model = op.hire(profile, name)
            if rank:
                op.assign(ranks[rank], miniature=model)
        made[name] = model
    gang.refresh_from_db()
    return made


def page(gang):
    return reverse("n26-gang-trade-points", args=[gang.pk])


def start(client, gang, *models, brought=None, opened=None):
    """Perform the action, as the form posts it.

    ``opened`` is the figure the box was drawn with; ``brought`` is what
    was typed over it. Left alone by a caller, neither is sent — which is
    a form submitted with the box untouched and empty of overrides.
    """
    data = {"visiting": [str(m.pk) for m in models]}
    if opened is not None:
        data["brought_default"] = str(opened)
    if brought is not None:
        data["brought"] = str(brought)
    return client.post(page(gang), data)


#: The `disabled` attribute itself, never the `disabled:` styling classes
#: the button component carries whatever its state.
_SHUT = re.compile(r"\bdisabled(?![:\w-])")


def shut_boxes(body):
    """The visiting tick boxes that are shut, as their own tags."""
    return [
        tag
        for tag in re.findall(r'<input[^>]*name="visiting"[^>]*>', body)
        if _SHUT.search(tag)
    ]


def submit_buttons(body):
    return re.findall(r'<button[^>]*type="submit"[^>]*>', body)


def unrendered(body):
    """Template tags that reached the page as text.

    Cotton does not read a template tag written among a component's
    attributes. It emits it verbatim, so the page carries the source and
    the attribute never applies — a control that draws shut and works.
    Nothing in a rendered page should hold a tag delimiter.
    """
    return re.findall(r"\{%[^%]*%\}", body)


class TestTheWayIn:
    def test_it_is_a_tab_on_the_gangs_edit_screen(self, client, tester, gang):
        client.force_login(tester)
        body = client.get(reverse("n26-edit-gang", args=[gang.pk])).content.decode()
        assert page(gang) in body

    def test_somebody_elses_gang_is_not_theirs_to_visit(self, client, gang):
        client.force_login(User.objects.create_user("stranger"))
        assert client.get(page(gang)).status_code == 404

    def test_signing_in_is_required(self, client, gang):
        assert client.get(page(gang)).status_code == 302


class TestTheFigureThatLeadsHere:
    """The Trade Points figure in the wealth strip is the way in from the
    screens where they are spent. It leads somewhere only for the reader
    who may act on it: a roster opens for whoever holds its address, and
    offering a stranger a door they would be refused at is worse than
    offering none."""

    def test_the_owners_stash_screen_links_the_figure(self, client, tester, gang):
        client.force_login(tester)
        body = client.get(reverse("n26-equip-gang", args=[gang.pk])).content.decode()
        assert f'href="{page(gang)}"' in body

    def test_the_owners_gang_sheet_links_it_too(self, client, tester, gang):
        client.force_login(tester)
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
        assert f'href="{page(gang)}"' in body

    def test_a_stranger_reading_the_roster_gets_a_number(self, client, gang):
        """They still see the figure — the sheet is theirs to read — but it
        is not a link, because the page behind it is not theirs to open."""
        client.force_login(User.objects.create_user("stranger"))
        answer = client.get(reverse("n26-gang", args=[gang.pk]))
        assert answer.status_code == 200
        assert f'href="{page(gang)}"' not in answer.content.decode()

    def test_a_signed_out_reader_gets_a_number(self, client, gang):
        answer = client.get(reverse("n26-gang", args=[gang.pk]))
        assert answer.status_code == 200
        assert f'href="{page(gang)}"' not in answer.content.decode()


class TestTheCallToAction:
    """Under the figures on both buying screens, a way to start tracking
    what gets spent — but only while there is nothing to track, since an
    open action already puts a number there that leads to the same page."""

    def equip_screens(self, gang, fighter):
        return [
            reverse("n26-equip-gang", args=[gang.pk]),
            reverse("n26-equip", args=[fighter.pk]),
        ]

    def test_both_buying_screens_offer_it(self, client, tester, roster, gang):
        client.force_login(tester)
        for at in self.equip_screens(gang, roster["Vex"]):
            body = client.get(at).content.decode()
            assert "Track TP spend by starting an action" in body, at

    def test_it_goes_once_an_action_is_open(self, client, tester, roster, gang):
        client.force_login(tester)
        start(client, gang, roster["Vex"])

        for at in self.equip_screens(gang, roster["Vex"]):
            body = client.get(at).content.decode()
            assert "Track TP spend by starting an action" not in body, at

    def test_a_stranger_is_not_offered_it(self, client, roster, gang):
        """It leads where they cannot go, so they are not sent."""
        client.force_login(User.objects.create_user("stranger"))
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
        assert "Track TP spend by starting an action" not in body


class TestTheStashCard:
    """The gang sheet's stash is where buying is read from, so it says
    where the Trading Post stands — both states, since "three left" and
    "no action" are equally worth knowing before buying anything."""

    def sheet(self, client, gang):
        return client.get(reverse("n26-gang", args=[gang.pk])).content.decode()

    def test_it_offers_a_way_to_start_one(self, client, tester, gang):
        client.force_login(tester)
        body = self.sheet(client, gang)
        assert "Not tracking TP" in body
        assert "Set up TP visit" in body

    def test_it_says_what_an_open_action_has_left(self, client, tester, roster, gang):
        client.force_login(tester)
        start(client, gang, roster["Vex"])

        body = self.sheet(client, gang)
        assert "Trading Post visit open" in body
        assert "Manage visit" in body
        assert "Not tracking TP" not in body

    def test_a_stranger_is_told_none_of_it(self, client, gang):
        """The stash is theirs to read; what to do about it is not."""
        client.force_login(User.objects.create_user("stranger"))
        body = self.sheet(client, gang)
        assert "Not tracking TP" not in body
        assert "Set up TP visit" not in body


class TestWhoIsOffered:
    def test_only_the_ranks_that_bring_something_are_offered(
        self, client, tester, roster, gang
    ):
        """Picking a fighter who brings nothing is a choice with no
        consequence, so the form asks one question rather than listing a
        roster to say no to most of it."""
        client.force_login(tester)
        boxes = re.findall(
            r'<input[^>]*name="visiting"[^>]*value="([^"]+)"',
            client.get(page(gang)).content.decode(),
        )
        assert set(boxes) == {str(roster["Vex"].pk), str(roster["Sura"].pk)}

    def test_they_open_ticked(self, client, tester, roster, gang):
        client.force_login(tester)
        body = client.get(page(gang)).content.decode()
        for name in ("Vex", "Sura"):
            box = body[body.index(f'value="{roster[name].pk}"') :][:200]
            assert "checked" in box

    def test_each_rank_says_what_it_brings(self, client, tester, roster, gang):
        client.force_login(tester)
        body = client.get(page(gang)).content.decode()
        assert "2 Trade Points each" in body
        assert "1 Trade Point each" in body

    def test_a_gang_with_nobody_says_so(self, client, tester, gang):
        """The page names the ranks it wanted, not a bare roster.

        A gang can be full of Gangers and still have nobody who brings
        anything, so "nobody to send" would read as a lie.
        """
        client.force_login(tester)
        body = client.get(page(gang)).content.decode()
        assert "no Leader or Champion to send" in body

    def test_a_rank_taken_away_is_not_one_held(
        self, client, tester, roster, gang, ranks
    ):
        """A removal is machinery, not a line: reading the assignments
        straight from the database has to cancel the pair itself, or a
        Leader the owner took away goes on bringing two points."""
        with operation(gang, actor=tester) as op:
            op.assign(ranks["Leader"], miniature=roster["Vex"], removes=True)

        client.force_login(tester)
        start(client, gang, roster["Vex"], roster["Sura"])

        gang.refresh_from_db()
        assert gang.starting_trade_points == 1


class TestStartingTheAction:
    @pytest.fixture(autouse=True)
    def signed_in(self, client, tester):
        client.force_login(tester)

    def test_it_takes_what_the_visitors_bring(self, client, roster, gang):
        start(client, gang, roster["Vex"], roster["Sura"])

        gang.refresh_from_db()
        assert gang.visiting_trading_post is True
        assert gang.starting_trade_points == 3
        assert gang.trade_points_left == 3

    def test_a_fighter_who_brings_nothing_is_not_a_visitor(self, client, roster, gang):
        """They are not offered, so a post naming one names nobody the
        form could have named — and a visit nobody performed is not one."""
        answer = client.post(
            page(gang), {"visiting": [str(roster["Nix"].pk)]}, follow=True
        )

        gang.refresh_from_db()
        assert gang.visiting_trading_post is False
        told = [str(m) for m in answer.context["messages"]]
        assert any("at least one fighter" in line for line in told)

    def test_sending_nobody_is_refused(self, client, roster, gang):
        """The rules want a fighter to perform the action; a visit nobody
        performed is not one."""
        answer = client.post(page(gang), {}, follow=True)

        gang.refresh_from_db()
        assert gang.visiting_trading_post is False
        told = [str(m) for m in answer.context["messages"]]
        assert any("at least one fighter" in line for line in told)

    def test_it_records_who_went(self, client, roster, gang):
        start(client, gang, roster["Vex"])

        went = LedgerEvent.objects.filter(
            gang=gang, kind=LedgerEvent.Kind.VISITED_TRADING_POST
        )
        assert [event.miniature.name for event in went] == ["Vex"]
        assert [event.note for event in went] == ["Leader"]

    def test_a_second_action_is_refused_while_one_is_open(self, client, roster, gang):
        """A gang performs one at a time. The form is shut while one is
        open, so a start arriving anyway is a stale page — and it would
        silently discard what the open action has left."""
        start(client, gang, roster["Vex"], roster["Sura"])

        answer = client.post(
            page(gang), {"visiting": [str(roster["Sura"].pk)]}, follow=True
        )

        gang.refresh_from_db()
        assert gang.starting_trade_points == 3
        told = [str(m) for m in answer.context["messages"]]
        assert any("Finish the open" in line for line in told)

    def test_it_moves_no_money(self, client, roster, gang):
        before = Gang.objects.get(pk=gang.pk).credits

        start(client, gang, roster["Vex"])

        gang.refresh_from_db()
        assert gang.credits == before

    def test_a_ticked_box_naming_nothing_on_this_roster_sends_nobody(
        self, client, roster, gang
    ):
        answer = client.post(page(gang), {"visiting": ["not-a-model"]}, follow=True)

        gang.refresh_from_db()
        assert gang.visiting_trading_post is False
        assert answer.status_code == 200

    def test_it_lands_back_on_the_action(self, client, roster, gang):
        answer = start(client, gang, roster["Vex"])
        assert answer.status_code == 302
        assert answer["Location"] == page(gang)


class TestATypedFigure:
    """The box opens on what the ticked fighters bring. Left alone the
    ticks decide; changed, the typed figure wins — a territory that adds
    a point, or an arbitrator's own number."""

    @pytest.fixture(autouse=True)
    def signed_in(self, client, tester):
        client.force_login(tester)

    def test_the_box_opens_on_what_the_ticked_fighters_bring(
        self, client, roster, gang
    ):
        body = client.get(page(gang)).content.decode()
        # A Leader and a Champion open ticked, so three.
        assert 'name="brought_default" value="3"' in body
        assert 'value="3"' in body

    def test_left_alone_the_ticks_decide(self, client, roster, gang):
        """Re-ticking without touching the box does what a reader expects,
        which no client-side arithmetic could promise with scripting off."""
        start(client, gang, roster["Vex"], opened=3, brought=3)

        gang.refresh_from_db()
        assert gang.starting_trade_points == 2

    def test_a_typed_figure_wins(self, client, roster, gang):
        start(client, gang, roster["Vex"], opened=3, brought=7)

        gang.refresh_from_db()
        assert gang.starting_trade_points == 7

    def test_a_typed_nought_wins_too(self, client, roster, gang):
        """Nought is a figure somebody meant, not an empty box."""
        start(client, gang, roster["Vex"], roster["Sura"], opened=3, brought=0)

        gang.refresh_from_db()
        assert gang.visiting_trading_post is True
        assert gang.starting_trade_points == 0

    def test_an_empty_box_falls_back_to_the_ticks(self, client, roster, gang):
        start(client, gang, roster["Vex"], opened=3, brought="")

        gang.refresh_from_db()
        assert gang.starting_trade_points == 2

    def test_a_figure_that_is_not_a_whole_number_is_refused(self, client, roster, gang):
        answer = client.post(
            page(gang),
            {
                "visiting": [str(roster["Vex"].pk)],
                "brought_default": "3",
                "brought": "-4",
            },
            follow=True,
        )

        gang.refresh_from_db()
        assert gang.visiting_trading_post is False
        told = [str(m) for m in answer.context["messages"]]
        assert any("whole number" in line for line in told)

    def test_an_enormous_figure_is_refused(self, client, roster, gang):
        answer = client.post(
            page(gang),
            {
                "visiting": [str(roster["Vex"].pk)],
                "brought_default": "3",
                "brought": "100000",
            },
            follow=True,
        )

        gang.refresh_from_db()
        assert gang.visiting_trading_post is False
        told = [str(m) for m in answer.context["messages"]]
        assert any("whole number" in line for line in told)

    def test_the_box_still_looks_like_a_box(self, client, roster, gang):
        """c-ui.input declares no `class`, so one passed to it arrives as a
        second class attribute and the browser keeps the first — dropping
        the component's whole styling, and with it any sign that this is
        somewhere to type."""
        body = client.get(page(gang)).content.decode()

        tag = re.search(r'<input[^>]*name="brought"[^>]*>', body).group()
        assert tag.count("class=") == 1
        assert "Or use a specific TP amount" in body

    def test_the_box_shuts_with_the_rest_of_the_form(self, client, roster, gang):
        start(client, gang, roster["Vex"])

        body = client.get(page(gang)).content.decode()
        box = re.findall(r'<input[^>]*name="brought"[^>]*>', body)
        assert box and all(_SHUT.search(tag) for tag in box)
        assert not unrendered(body)


class TestTheReceipt:
    @pytest.fixture(autouse=True)
    def signed_in(self, client, tester):
        client.force_login(tester)

    def test_it_is_drawn_only_while_an_action_is_open(self, client, roster, gang):
        assert "Complete action" not in client.get(page(gang)).content.decode()

        start(client, gang, roster["Vex"])

        assert "Complete action" in client.get(page(gang)).content.decode()

    def test_it_names_the_ranks_that_brought_the_figure(self, client, roster, gang):
        start(client, gang, roster["Vex"], roster["Sura"])

        body = client.get(page(gang)).content.decode()
        assert "Leader, Champion" in body

    def test_it_offers_every_fighter_to_equip(self, client, roster, gang):
        """What a visit brought is the gang's, and it is spent on whoever
        it was for — including the fighters who did not go."""
        start(client, gang, roster["Vex"])

        body = client.get(page(gang)).content.decode()
        assert "Equip a fighter" in body
        for name in ("Vex", "Sura", "Nix"):
            assert name in body

    def test_each_fighter_gets_a_way_to_spend_what_they_brought(
        self, client, roster, gang
    ):
        """Having sent a fighter to the post, the next thing an owner
        wants is that fighter's own equip screen, opened on the post."""
        from n26.library.authoring import create_trading_post, create_wargear
        from n26.library.models import Wargear

        create_wargear("Mesh armour", price=15, trade_point_price=1)
        post = create_trading_post("Trading Post", contains=[Wargear])
        start(client, gang, roster["Vex"])

        body = client.get(page(gang)).content.decode()
        assert f"{reverse('n26-equip', args=[roster['Vex'].pk])}?list={post.pk}" in body

    def test_a_fighter_who_has_left_is_not_offered(self, client, tester, roster, gang):
        """Off the roster is off the list: there is no page left to send
        anybody to."""
        from n26.library.authoring import create_trading_post, create_wargear
        from n26.library.models import Wargear

        create_wargear("Mesh armour", price=15, trade_point_price=1)
        create_trading_post("Trading Post", contains=[Wargear])
        start(client, gang, roster["Vex"], roster["Sura"])
        with operation(gang, actor=tester) as op:
            op.remove(roster["Vex"].membership)

        body = client.get(page(gang)).content.decode()
        assert reverse("n26-equip", args=[roster["Vex"].pk]) not in body
        assert reverse("n26-equip", args=[roster["Nix"].pk]) in body

    def test_the_start_form_is_shut_while_an_action_is_open(self, client, roster, gang):
        """Never offer an act that will be refused: with an action open,
        starting another would throw away what it has left.

        Asserted on the tags themselves. The button component carries
        `disabled:` styling classes whatever its state, so counting the
        word in the page would pass on a form that is wide open.
        """
        assert not shut_boxes(client.get(page(gang)).content.decode())

        start(client, gang, roster["Vex"])

        shut = client.get(page(gang)).content.decode()
        assert shut_boxes(shut)
        assert "Finish the action above first" in shut
        # The word alone is not proof: an unread `{% if %}` among a
        # component's attributes puts "disabled" in the page as text.
        assert not unrendered(shut)

    def test_finishing_the_action_stays_live_while_it_is(self, client, roster, gang):
        """Only the start form shuts. The button that ends the action is
        the one thing on the card that must still work."""
        start(client, gang, roster["Vex"])

        submits = submit_buttons(client.get(page(gang)).content.decode())
        assert len(submits) == 2
        assert sum(bool(_SHUT.search(tag)) for tag in submits) == 1

    def test_the_shut_start_button_says_why(self, client, roster, gang):
        """A disabled button emits no mouse events, so the reason hangs off
        a wrapper around it rather than off the button."""
        start(client, gang, roster["Vex"])

        body = client.get(page(gang)).content.decode()
        assert "a gang performs one" in body
        assert "cursor-not-allowed" in body

    def test_it_shows_the_three_figures(self, client, roster, gang):
        start(client, gang, roster["Vex"])

        body = client.get(page(gang)).content.decode()
        for label in ("Available", "Spent", "Remaining"):
            assert label in body


class TestFinishingTheAction:
    @pytest.fixture(autouse=True)
    def signed_in(self, client, tester):
        client.force_login(tester)

    def test_it_shuts_the_post(self, client, roster, gang):
        start(client, gang, roster["Vex"])

        client.post(page(gang), {"act": "finish"})

        gang.refresh_from_db()
        assert gang.visiting_trading_post is False
        assert gang.starting_trade_points is None
        assert gang.trade_points_left is None

    def test_it_says_what_went_with_it(self, client, roster, gang):
        start(client, gang, roster["Vex"])

        answer = client.post(page(gang), {"act": "finish"}, follow=True)

        told = [str(m) for m in answer.context["messages"]]
        assert any("2 unspent went with it" in line for line in told)

    def test_finishing_a_shut_post_changes_nothing(self, client, roster, gang):
        answer = client.post(page(gang), {"act": "finish"})

        assert answer.status_code == 302
        gang.refresh_from_db()
        assert gang.visiting_trading_post is False
        assert not LedgerEvent.objects.filter(
            gang=gang, kind=LedgerEvent.Kind.TRADE_POINTS_SET
        ).exists()

    def test_the_confirmation_lands_where_the_card_was(self, client, roster, gang):
        """Finishing takes the card away. A confirmation at the top of the
        page would land nowhere near what the reader was looking at, so it
        arrives in the space the card just left — above the form that
        starts the next one."""
        start(client, gang, roster["Vex"])

        body = client.post(page(gang), {"act": "finish"}, follow=True).content.decode()

        assert "left the Trading Post" in body
        assert body.index("left the Trading Post") < body.index(
            "Start Visit Trading Post action"
        )
        assert body.index("What to edit") < body.index("left the Trading Post")

    def test_it_is_said_once(self, client, roster, gang):
        """Reading the storage is what consumes it, so a page that moves
        its messages and does not clear the layout's own slot draws every
        one of them twice."""
        start(client, gang, roster["Vex"])

        body = client.post(page(gang), {"act": "finish"}, follow=True).content.decode()

        assert body.count("left the Trading Post") == 1

    def test_the_figure_goes_back_to_an_em_dash(self, client, roster, gang):
        start(client, gang, roster["Vex"])
        client.post(page(gang), {"act": "finish"})

        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
        assert "No Visit Trading Post action open" in body


class TestTheShutPostSaysSo:
    """Informing, never blocking: the rules open the Trading Post only to
    a gang whose fighter performed the action, and the listing says as
    much rather than hiding itself."""

    @pytest.fixture
    def post(self, db):
        from n26.library.authoring import create_trading_post, create_wargear
        from n26.library.models import Wargear

        create_wargear("Mesh armour", price=15, trade_point_price=1)
        return create_trading_post("Trading Post", contains=[Wargear])

    def stash(self, client, gang, post):
        at = reverse("n26-equip-gang", args=[gang.pk])
        return client.get(f"{at}?list={post.pk}").content.decode()

    def test_the_stash_screen_says_the_post_is_shut(self, client, tester, gang, post):
        client.force_login(tester)
        assert "Not tracking TP" in self.stash(client, gang, post)

    def test_it_offers_one_way_in_and_not_two(self, client, tester, gang, post):
        """The rail's block and the link under the figures say the same
        thing. On a list that deals in Trade Points only the fuller one
        draws."""
        client.force_login(tester)
        body = self.stash(client, gang, post)
        assert "Not tracking TP" in body
        assert "Track TP spend by starting an action" not in body

    def test_and_stops_saying_it_once_somebody_has(
        self, client, tester, roster, gang, post
    ):
        client.force_login(tester)
        start(client, gang, roster["Vex"])
        assert "Not tracking TP" not in self.stash(client, gang, post)
