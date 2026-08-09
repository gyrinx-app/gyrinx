"""Deleting a gang: the question, the act, and what stops being there.

Delete is archive. The row survives so the ledger under it stays a true
record, but nothing a player can reach shows the gang again and there is
no way back from the app. These tests hold both halves of that: the
surfaces really do stop naming it, and the money underneath really is
left alone.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.models import Assignment, Gang
from n26.core.operations import operation
from n26.core.reconcile import assert_reconciled

pytestmark = pytest.mark.django_db


@pytest.fixture
def tester(db):
    """Staff, because /n26/ is fenced to staff and testers."""
    return User.objects.create_user("player", is_staff=True)


@pytest.fixture
def gang(gang_type, tester):
    return Gang.objects.create(
        name="The Ashen Choir",
        owner=tester,
        gang_type=gang_type,
        starting_credits=1000,
        credits=1000,
    )


@pytest.fixture
def ganger(make_profile, make_statline):
    profile = make_profile("Ganger", price=55)
    make_statline(profile, movement=5, weapon_skill=4, toughness=3)
    return profile


@pytest.fixture
def delete_url(gang):
    return reverse("n26-delete-gang", args=[gang.pk])


class TestBeingAsked:
    """The confirmation is a page, so it has an address, survives a
    reload, and can be left by pressing Back."""

    def test_the_owner_is_asked_before_anything_happens(
        self, client, tester, gang, delete_url
    ):
        client.force_login(tester)
        response = client.get(delete_url)

        assert response.status_code == 200
        body = response.content.decode()
        assert "Delete The Ashen Choir?" in body
        # A form that posts back here, with a submit inside it: the act is
        # a POST, so a page drawing only links would be a dead end. Cotton
        # fails soft, and a footer that stopped rendering would look like a
        # styling problem rather than a screen with no button.
        assert f'action="{delete_url}"' in body
        assert 'type="submit"' in body
        assert "Delete gang" in body

    def test_the_page_says_the_press_cannot_be_taken_back(
        self, client, tester, gang, delete_url
    ):
        """The wording is the feature. There is no unarchive, so a screen
        that hinted the gang could come back would be a promise the app
        does not keep — and one claiming the gang is destroyed would be a
        different untruth. Both halves are pinned so neither drifts."""
        client.force_login(tester)
        body = client.get(delete_url).content.decode()

        assert "You cannot undo this" in body
        assert "You will not be able to bring it back." in body

    def test_the_page_names_what_would_go(
        self, client, tester, gang, ganger, delete_url
    ):
        """The roster count, so a player with two similarly named gangs
        has a second fact to check the decision against."""
        with operation(gang, actor=tester) as op:
            op.hire(ganger, "Vex")
            op.hire(ganger, "Sull")

        client.force_login(tester)
        response = client.get(delete_url)

        assert response.context["roster"] == 2
        assert "2 fighters" in response.content.decode()

    def test_the_footer_controls_are_drawn_once(self, client, tester, gang, delete_url):
        """A component's unfilled slot is not empty: with no declared
        default it holds whatever the enclosing scope has under that name.
        Both the form wrapper and the header inside it take an `actions`
        slot, so anything under that name in scope can be drawn twice —
        silently, and looking like a spacing accident rather than two
        Delete buttons.
        """
        client.force_login(tester)
        body = client.get(delete_url).content.decode()

        assert body.count("Cancel") == 1
        assert body.count('type="submit"') == 1

    def test_the_heading_offers_nowhere_else_to_go(
        self, client, tester, gang, delete_url
    ):
        """A confirmation is a considered stop. The form wrapper can put a
        switcher beside its heading, and this page does not take it up: a
        control offering somewhere else to be, on the screen asking whether
        you meant it, is an answer to a question nobody asked. The bar's
        own switcher is the one on the page, and it is the chrome's rather
        than this screen's.
        """
        client.force_login(tester)
        body = client.get(delete_url).content.decode()

        assert body.count('aria-haspopup="menu"') == 1
        assert "Switch to another gang" in body

    def test_the_way_out_is_on_the_page(self, client, tester, gang, delete_url):
        """Cancel goes back to the sheet the press came from — a
        confirmation with only one button is a trap, not a question. It is
        a link, so pressing it leaves rather than posting the form."""
        client.force_login(tester)
        body = client.get(delete_url).content.decode()

        sheet = reverse("n26-gang", args=[gang.pk])
        assert f'href="{sheet}"' in body
        assert "Cancel" in body

    def test_the_act_is_marked_as_taking_something_away(
        self, client, tester, gang, delete_url
    ):
        """Red on the submit and nothing on the way out. The colour is what
        tells the two apart before either word is read, and a page that
        ended in the green of a creating form would say the wrong thing."""
        client.force_login(tester)
        body = client.get(delete_url).content.decode()

        assert "bg-red-500" in body
        assert "bg-green-700" not in body

    def test_reading_the_page_deletes_nothing(self, client, tester, gang, delete_url):
        """A GET must never mutate: link checkers, prefetchers and the
        Back button all follow links, and none of them means it."""
        client.force_login(tester)
        client.get(delete_url)

        gang.refresh_from_db()
        assert gang.archived is False

    def test_the_sheet_offers_it(self, client, tester, gang, delete_url):
        """The control on the sheet was drawn before it led anywhere."""
        client.force_login(tester)
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()

        assert delete_url in body

    def test_a_pk_that_is_not_a_ulid_is_not_found(self, client, tester):
        """The id reaches ULIDField, which raises rather than missing —
        a 500 for what is only ever somebody's bad link."""
        client.force_login(tester)
        assert client.get("/n26/gangs/nonsense/delete/").status_code == 404


class TestDoingIt:
    """The POST is the act, and the only thing that is."""

    def test_confirming_deletes_the_gang(self, client, tester, gang, delete_url):
        client.force_login(tester)
        response = client.post(delete_url)

        gang.refresh_from_db()
        assert gang.archived is True
        assert gang.archived_at is not None
        assert response.status_code == 302
        assert response.url == reverse("n26-gangs")

    def test_the_confirmation_names_the_gang(self, client, tester, gang, delete_url):
        """Landing on a list one row shorter says nothing about which row
        went, so the message says it."""
        client.force_login(tester)
        body = client.post(delete_url, follow=True).content.decode()

        assert "Deleted The Ashen Choir." in body

    def test_deleting_twice_is_not_found(self, client, tester, gang, delete_url):
        """The second press has nothing live to act on — a stale tab is
        answered the same way a stranger is."""
        client.force_login(tester)
        client.post(delete_url)

        assert client.post(delete_url).status_code == 404


class TestWhoMayDoIt:
    """Owner only, and a stranger is told nothing.

    404 rather than 403 at both steps: which gangs exist is not something
    to be probed for, and a refusal that distinguishes "not yours" from
    "no such gang" is a way of asking.
    """

    @pytest.fixture
    def stranger(self, db, client):
        person = User.objects.create_user("stranger", is_staff=True)
        client.force_login(person)
        return person

    def test_a_stranger_cannot_reach_the_question(
        self, client, stranger, gang, delete_url
    ):
        assert client.get(delete_url).status_code == 404

    def test_a_stranger_cannot_do_it(self, client, stranger, gang, delete_url):
        assert client.post(delete_url).status_code == 404

        gang.refresh_from_db()
        assert gang.archived is False

    def test_a_signed_out_visitor_is_sent_to_sign_in(self, client, gang, delete_url):
        response = client.post(delete_url)

        assert response.status_code == 302
        assert "login" in response.url
        gang.refresh_from_db()
        assert gang.archived is False


class TestWhereItStopsAppearing:
    """A deleted gang that still shows up somewhere is the obvious bug,
    so every surface that lists gangs is checked by name."""

    @pytest.fixture
    def deleted(self, client, tester, gang, delete_url):
        client.force_login(tester)
        client.post(delete_url)
        return gang

    def test_it_is_gone_from_the_gangs_index(self, client, deleted):
        response = client.get(reverse("n26-gangs"))
        assert [g.name for g in response.context["gangs"]] == []

    def test_it_is_gone_from_the_dashboards_tab(self, client, deleted):
        response = client.get(reverse("n26-dashboard"))
        assert [g.name for g in response.context["gangs"]] == []

    def test_it_never_matches_a_search(self, client, deleted):
        response = client.get(reverse("n26-gangs"), {"q": "ashen"})
        assert [g.name for g in response.context["gangs"]] == []

    def test_it_is_gone_from_the_drawer(self, client, tester, gang, delete_url):
        """Read off the create-gang page, which lists no gangs of its own:
        on the index or the dashboard the drawer's copy of the row cannot
        be told from the table's.

        The link rather than the name, because the confirmation message
        rides the next page and names the gang there — which is the point
        of the message, and would answer this question wrongly.
        """
        client.force_login(tester)
        elsewhere = reverse("n26-create-gang")
        sheet = reverse("n26-gang", args=[gang.pk])
        assert sheet in client.get(elsewhere).content.decode()

        client.post(delete_url)
        assert sheet not in client.get(elsewhere).content.decode()


class TestWhereItStopsOpening:
    """One answer for every page the gang owned.

    A player told the gang is gone must not find a working gang sheet
    behind a bookmark, so the sheet, hire, equip and print all 404 — the
    same answer a stranger already got, and it comes from the same two
    guards rather than from four opinions.
    """

    @pytest.fixture
    def vex(self, gang, tester, ganger):
        with operation(gang, actor=tester) as op:
            return op.hire(ganger, "Vex")

    @pytest.fixture
    def deleted(self, client, tester, gang, vex, delete_url):
        client.force_login(tester)
        client.post(delete_url)
        return gang

    def test_the_sheet_is_not_found(self, client, deleted):
        assert client.get(reverse("n26-gang", args=[deleted.pk])).status_code == 404

    def test_hiring_is_not_found(self, client, deleted):
        url = reverse("n26-hire-fighter", args=[deleted.pk])
        assert client.get(url).status_code == 404

    def test_the_print_pages_are_not_found(self, client, deleted):
        assert (
            client.get(reverse("n26-print-setup", args=[deleted.pk])).status_code == 404
        )
        assert client.get(reverse("n26-print", args=[deleted.pk])).status_code == 404

    def test_equipping_a_fighter_of_a_deleted_gang_is_not_found(
        self, client, deleted, vex
    ):
        """The fighter's own page goes the way the gang did — the guard
        reads the gang through the membership rather than trusting that
        nobody kept the link."""
        assert client.get(reverse("n26-equip", args=[vex.pk])).status_code == 404


class TestWhatIsLeftAlone:
    """Nothing below the gang is touched.

    Archiving is the roster leaving, not the history being rewritten. An
    assignment's rating and a ledger entry's paid credits are true
    statements about what happened; they would still be true if the gang
    were shown again, and reconcile still proves the pinned numbers
    honest afterwards.
    """

    def test_the_assignments_stay_live(self, client, tester, gang, ganger, delete_url):
        with operation(gang, actor=tester) as op:
            op.hire(ganger, "Vex")
        before = Assignment.objects.filter(gang_root=gang).count()
        assert before > 0

        client.force_login(tester)
        client.post(delete_url)

        assert (
            Assignment.objects.filter(gang_root=gang, archived=False).count() == before
        )

    def test_the_money_is_untouched(self, client, tester, gang, ganger, delete_url):
        with operation(gang, actor=tester) as op:
            op.hire(ganger, "Vex")
        gang.refresh_from_db()
        rating, credits = gang.rating, gang.credits

        client.force_login(tester)
        client.post(delete_url)

        gang.refresh_from_db()
        assert (gang.rating, gang.credits) == (rating, credits)
        assert_reconciled(gang)
