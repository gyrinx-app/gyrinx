"""Verify that N26 displays account badges selected by the shared platform registry. Use
the same eligibility, artwork and labels across account controls, profiles, gang owners
and campaigns. Batch badge reads for repeated names, and export allowlisted SVG data for
React islands.
"""

import re
from pathlib import Path

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from gyrinx.accounts.models import PatreonStatus, UserProfile
from gyrinx.badges import STAFF_BADGE, badge_by_slug
from gyrinx.site.templatetags.badge_tags import badge_svg

pytestmark = pytest.mark.django_db

GUILDER = badge_by_slug("guilder")

# Identify the badge wrapper so tests can detect unwanted empty spacing.
FLAIR_WRAPPER = 'class="ml-[0.25em] n26-icon-inline'


@pytest.fixture
def tester(client):
    """Create and sign in an account, with optional staff or other user fields."""

    def _make(username, **kwargs):
        user = User.objects.create_user(username, **kwargs)
        client.force_login(user)
        return user

    return _make


@pytest.fixture
def supporter(tester):
    """Active supporter who has selected the Guilder badge."""
    user = tester("patron")
    UserProfile.objects.create(
        user=user,
        patreon_status=PatreonStatus.ACTIVE,
        patreon_tier="Guilder",
        selected_badge="guilder",
    )
    return user


class TestTheBadgeBesideAName:
    """Display the platform-selected account badge through N26 components."""

    def test_a_supporter_sees_their_own_tier_badge(
        self, supporter, client, default_pack
    ):
        body = client.get("/n26/gangs/new/").content.decode()
        assert badge_svg(GUILDER).strip() in body

    def test_a_staff_member_who_has_chosen_nothing_gets_the_staff_mark(
        self, tester, client, default_pack
    ):
        """Default eligible staff accounts to the staff badge when no badge is selected."""
        UserProfile.objects.create(user=tester("boss", is_staff=True))

        body = client.get("/n26/gangs/new/").content.decode()
        assert badge_svg(STAFF_BADGE).strip() in body

    def test_someone_entitled_to_nothing_gets_no_mark_and_no_empty_span(
        self, tester, client, default_pack
    ):
        """Omit the badge wrapper when no badge is available so it adds no empty spacing."""
        tester("nobody")

        body = client.get("/n26/gangs/new/").content.decode()
        assert "nobody" in body
        assert FLAIR_WRAPPER not in body

    def test_a_lapsed_supporter_loses_the_badge_they_picked(
        self, tester, client, default_pack
    ):
        """Recheck eligibility rather than trusting a stored selection after entitlement
        ends.
        """
        user = tester("former-patron")
        UserProfile.objects.create(
            user=user,
            patreon_status=PatreonStatus.FORMER,
            patreon_tier="Guilder",
            selected_badge="guilder",
        )

        body = client.get("/n26/gangs/new/").content.decode()
        assert FLAIR_WRAPPER not in body

    def test_the_account_menu_names_the_reader_and_marks_them(
        self, supporter, client, default_pack
    ):
        """Keep account identity and badge in menu props because the header button can hide
        the name on narrow screens.
        """
        import json

        from bs4 import BeautifulSoup

        soup = BeautifulSoup(client.get("/n26/gangs/new/").content, "html.parser")
        host = soup.select_one('[data-react-name="account-menu"]')
        menu = json.loads(soup.find(id=host["data-react-props"]).string)

        assert menu["items"][0] == {"type": "person"}
        assert menu["person"]["name"] == "patron"
        assert menu["person"]["badge"] == "guilder"
        assert menu["badges"]["guilder"]["label"] == GUILDER.description

    def test_the_bars_account_button_marks_the_name_it_shows(
        self, supporter, client, default_pack
    ):
        """The server-rendered account button must show the same badge supplied to the
        React menu.
        """
        body = client.get("/n26/gangs/new/").content.decode()
        # Inspect the server fallback before the React island mounts.
        host = body.index('data-react-name="account-menu"')
        button = body[host : body.index("</button>", host)]
        assert "patron" in button
        assert badge_svg(GUILDER).strip() in button

    def test_the_badge_says_what_the_registry_says_it_means(
        self, supporter, client, default_pack
    ):
        """Use the registry description for both the accessible name and tooltip so renamed
        tiers remain consistent.
        """
        body = client.get("/n26/gangs/new/").content.decode()
        assert f'aria-label="{GUILDER.description}"' in body
        assert f'title="{GUILDER.description}"' in body


class TestTheHomePageGreeting:
    """Use the reader's account badge in the home-page heading."""

    def test_the_greeting_marks_the_reader(self, supporter, client, default_pack):
        body = client.get("/n26/").content.decode()
        heading = body[body.index("Hello,") :]
        heading = heading[: heading.index("</h1>")]
        assert "patron" in heading
        assert badge_svg(GUILDER).strip() in heading

    def test_the_badge_is_inside_the_heading_and_scales_with_it(
        self, supporter, client, default_pack
    ):
        """Size the badge in em units so it scales with the heading."""
        body = client.get("/n26/").content.decode()
        heading = body[body.index("Hello,") :]
        heading = heading[: heading.index("</h1>")]
        assert FLAIR_WRAPPER in heading
        assert "n26-icon-inline" in heading
        assert "[--n26-icon-size:1em]" in heading

    def test_a_reader_entitled_to_nothing_is_greeted_by_name_alone(
        self, tester, client, default_pack
    ):

        tester("nobody")

        body = client.get("/n26/").content.decode()
        assert "Hello," in body
        assert "nobody" in body
        assert FLAIR_WRAPPER not in body


class TestTheProfilePage:
    """Display the profile subject's badge, independently of the reader or selected edition
    tab.
    """

    @pytest.mark.parametrize("tab", ["n23", "n26"])
    def test_the_profile_header_marks_the_person_with_the_picker_artwork(
        self, supporter, tester, client, default_pack, tab
    ):
        tester("reader")
        profile = reverse("user-profile", args=[supporter.username])
        body = client.get(profile, {"tab": tab}).content.decode()
        heading = body[body.index("<h1") : body.index("</h1>")]
        assert "patron" in heading
        below_the_bar = body.split("</header>")[-1]
        assert below_the_bar.count(f'src="{GUILDER.image_url()}"') == 1
        assert f'title="{GUILDER.description}"' in below_the_bar
        assert f'href="{profile}"' not in below_the_bar

    @pytest.mark.parametrize("tab", ["n23", "n26"])
    def test_someone_entitled_to_nothing_is_headed_by_name_alone(
        self, tester, client, default_pack, tab
    ):
        tester("nobody")
        body = client.get(
            reverse("user-profile", args=["nobody"]), {"tab": tab}
        ).content.decode()
        heading = body[body.index("<h1") : body.index("</h1>")]
        assert "nobody" in heading
        assert FLAIR_WRAPPER not in body.split("</header>")[-1]


class TestTheOwnerOfAGang:
    """Use the owner's account badge throughout gang navigation."""

    @pytest.fixture
    def gang(self, supporter, gang_type, make_profile):
        from n26.tests.sandbox.actions import found_gang, hire

        gang = found_gang("The Bad Girls", gang_type, owner=supporter)
        hire(gang, make_profile("Ganger"), "Vex")
        return gang

    def test_the_sheet_shows_the_owners_badge(self, gang, client, default_pack):
        body = client.get(f"/n26/gangs/{gang.pk}/").content.decode()
        assert "patron" in body
        assert badge_svg(GUILDER).strip() in body
        assert f'aria-label="{GUILDER.description}"' in body

    def test_every_trail_into_the_gang_shows_it_too(self, gang, client, default_pack):

        from n26.core.models import Miniature

        fighter = Miniature.objects.get(name="Vex")
        for path in (
            f"/n26/gangs/{gang.pk}/hire/",
            f"/n26/gangs/{gang.pk}/print/setup/",
            f"/n26/fighters/{fighter.pk}/equip/",
        ):
            body = client.get(path).content.decode()
            assert badge_svg(GUILDER).strip() in body, path

    def test_a_gang_has_no_badge_of_its_own_to_show(self, gang, client, default_pack):
        """Below the account header, the gang sheet has one account badge: its owner's.
        Gang-type artwork must not introduce another account-badge wrapper.
        """
        body = client.get(f"/n26/gangs/{gang.pk}/").content.decode()
        sheet = body.split("</header>")[-1]
        assert sheet.count(FLAIR_WRAPPER) == 1


class TestTheNamesOnACampaign:
    """Display participant and arbitrator badges while keeping queries constant as people
    and campaigns increase.
    """

    @pytest.fixture
    def table(self, supporter, campaign_type):

        from n26.tests.sandbox.actions import found_campaign

        return found_campaign("Dust Falls", campaign_type, owner=supporter, budget=1000)

    @pytest.fixture
    def player(self, gang_type, default_pack):
        """Create an active Guilder supporter, accept their campaign invitation and add
        their gang.
        """
        from n26.core.campaigns import campaign_operation
        from n26.tests.sandbox.actions import found_gang, join_campaign

        def _seat(campaign, name):
            person = User.objects.create_user(name)
            UserProfile.objects.create(
                user=person,
                patreon_status=PatreonStatus.ACTIVE,
                patreon_tier="Guilder",
                selected_badge="guilder",
            )
            with campaign_operation(campaign, actor=campaign.owner) as act:
                act.invite(person)
            with campaign_operation(campaign, actor=person) as act:
                act.answer_invitation(person, accepted=True)
            join_campaign(
                found_gang(f"{name}'s gang", gang_type, owner=person), campaign
            )
            return person

        return _seat

    @staticmethod
    def _queries(client, path):
        """Warm session state before measuring page queries. Request roll dialogs over
        htmx, matching their caller.
        """
        headers = {"HX-Request": "true"} if "?roll=" in path else {}
        client.get(path, headers=headers)
        with CaptureQueriesContext(connection) as context:
            response = client.get(path, headers=headers)
        assert response.status_code == 200
        return len(context.captured_queries)

    def test_each_player_is_marked_at_the_table_and_on_their_gang(
        self, table, player, client
    ):
        """Check server-rendered player and log badges together with React gang-owner data.
        Exclude the account header from badge counts.
        """
        before = client.get(f"/n26/campaigns/{table.pk}/").content.decode()
        player(table, "vex")
        player(table, "kesh")
        after = client.get(f"/n26/campaigns/{table.pk}/").content.decode()

        mark = badge_svg(GUILDER).strip()
        assert after.split("</header>")[-1].count(mark) == (
            before.split("</header>")[-1].count(mark) + 4
        )
        from n26.tests.fixtures import island_props

        props = island_props(after, "campaign-gangs")
        assert {line["owner"]["name"] for line in props["gangs"]} == {"vex", "kesh"}
        assert all(line["owner"]["badge"] == GUILDER.slug for line in props["gangs"])
        assert props["badges"][GUILDER.slug]["svg"]["tag"] == "svg"

    def test_the_page_reads_the_badges_once_for_everybody(self, table, player, client):
        player(table, "vex")
        with_one = self._queries(client, f"/n26/campaigns/{table.pk}/")
        player(table, "kesh")
        player(table, "ash")
        player(table, "nyx")
        with_more = self._queries(client, f"/n26/campaigns/{table.pk}/")
        assert with_more == with_one

    def test_a_campaign_row_marks_its_arbitrator(self, table, player, client):

        person = player(table, "vex")
        client.force_login(person)
        body = client.get("/n26/campaigns/").content.decode()
        rows = body.split("</header>")[-1]
        assert "Arbitrator:" not in rows
        assert badge_svg(GUILDER).strip() in rows

    def test_the_list_reads_the_badges_once_for_every_campaign(
        self, supporter, campaign_type, player, client
    ):
        from n26.tests.sandbox.actions import found_campaign

        campaigns = [
            found_campaign(f"Campaign {index}", campaign_type, owner=supporter)
            for index in range(4)
        ]
        person = player(campaigns[0], "vex")
        client.force_login(person)
        with_one = self._queries(client, "/n26/campaigns/")
        for campaign in campaigns[1:]:
            player(campaign, f"vex-in-{campaign.name[-1]}")
        # Accept invitations as the same reader for all campaigns being compared.
        from n26.core.campaigns import campaign_operation

        for campaign in campaigns[1:]:
            with campaign_operation(campaign, actor=supporter) as act:
                act.invite(person)
            with campaign_operation(campaign, actor=person) as act:
                act.answer_invitation(person, accepted=True)
        with_more = self._queries(client, "/n26/campaigns/")
        assert with_more == with_one

    def test_a_dialog_that_cannot_be_drawn_serves_the_page_without_a_read_per_gang(
        self, table, player, client
    ):
        """A stale roll-dialog request redraws the campaign page. Batch badge loading for
        that fallback instead of reading once per gang.
        """
        player(table, "vex")
        with_one = self._queries(
            client, f"/n26/campaigns/{table.pk}/?roll=nothing-of-the-kind"
        )
        player(table, "kesh")
        player(table, "ash")
        player(table, "nyx")
        with_more = self._queries(
            client, f"/n26/campaigns/{table.pk}/?roll=nothing-of-the-kind"
        )
        assert with_more == with_one

    def test_the_log_names_who_acted_with_their_badge(self, table, player, client):
        """Show badges beside other actors' names. The reader's own acts use You without
        repeating their badge.
        """
        player(table, "vex")

        body = client.get(f"/n26/campaigns/{table.pk}/").content.decode()
        named = re.search(r"<a[^>]*font-medium[^>]*><span[^>]*>vex<", body)
        assert named
        assert FLAIR_WRAPPER in body[named.end() : named.end() + 400]
        assert not re.search(r"<a[^>]*font-medium[^>]*><span[^>]*>patron<", body)

    def test_the_log_page_reads_the_badges_once_for_everybody(
        self, table, player, client
    ):
        player(table, "vex")
        with_one = self._queries(client, f"/n26/campaigns/{table.pk}/log/")
        player(table, "kesh")
        player(table, "ash")
        player(table, "nyx")
        with_more = self._queries(client, f"/n26/campaigns/{table.pk}/log/")
        assert with_more == with_one

    def test_the_players_screen_marks_players_and_people_found(
        self, table, player, client
    ):
        """Include badges in both existing participant rows and account search results."""
        player(table, "vex")
        UserProfile.objects.create(
            user=User.objects.create_user("vexation"),
            patreon_status=PatreonStatus.ACTIVE,
            patreon_tier="Guilder",
            selected_badge="guilder",
        )

        body = client.get(
            f"/n26/campaigns/{table.pk}/players/add/?q=vex"
        ).content.decode()
        below_the_bar = body.split("</header>")[-1]
        # Count the arbitrator breadcrumb, participant row and both search results.
        assert below_the_bar.count(badge_svg(GUILDER).strip()) == 4

    def test_the_players_screen_reads_the_arbitrators_badge_with_the_campaign(
        self, table, supporter
    ):
        """Load the arbitrator's profile and grants with the campaign so rendering their
        breadcrumb needs no further account query.
        """
        from django.test import RequestFactory

        from gyrinx.site.templatetags.badge_tags import badge_for
        from n26.core.views.permissions import _own_campaign_or_404

        request = RequestFactory().get("/")
        request.user = supporter
        found = _own_campaign_or_404(request, table.pk, with_owner_badge=True)

        with CaptureQueriesContext(connection) as context:
            assert badge_for(found.owner) == GUILDER
        person_reads = [
            q["sql"]
            for q in context.captured_queries
            if "core_userprofile" in q["sql"] or '"user_id" =' in q["sql"]
        ]
        assert not person_reads

    def test_the_players_screen_reads_the_badges_once_for_everybody(
        self, table, player, client
    ):
        player(table, "vex-1")
        with_one = self._queries(
            client, f"/n26/campaigns/{table.pk}/players/add/?q=vex"
        )
        for index in range(2, 5):
            player(table, f"vex-{index}")
        with_more = self._queries(
            client, f"/n26/campaigns/{table.pk}/players/add/?q=vex"
        )
        assert with_more == with_one

    def test_the_add_gang_screen_marks_each_gangs_owner(self, table, player, client):
        """The arbitrator sees each gang owner's badge. A participant choosing among their
        own gangs needs no repeated owner identity.
        """
        player(table, "vex")
        person = player(table, "kesh")
        address = reverse("n26-campaign-add-gang", args=[table.pk])

        body = client.get(address).content.decode()
        below_the_bar = body.split("</header>")[-1]
        # Count the arbitrator breadcrumb and both gang owners.
        assert below_the_bar.count(badge_svg(GUILDER).strip()) == 3

        client.force_login(person)
        body = client.get(address).content.decode()
        below_the_bar = body.split("</header>")[-1]
        assert "kesh&#x27;s gang" in below_the_bar
        # Only the arbitrator breadcrumb remains when owner identity is omitted from the
        # participant's own gangs.
        assert below_the_bar.count(badge_svg(GUILDER).strip()) == 1

    def test_the_add_gang_island_names_each_owner_and_draws_each_badge_once(
        self, table, player, client
    ):
        """Reuse one badge-artwork entry across all owner links that select it."""
        import json

        from bs4 import BeautifulSoup

        def picker(response):
            soup = BeautifulSoup(response.content, "html.parser")
            host = soup.select_one("[data-react-name='campaign-gang-picker']")
            return json.loads(soup.find(id=host["data-react-props"]).string)

        player(table, "vex")
        person = player(table, "kesh")
        address = reverse("n26-campaign-add-gang", args=[table.pk])

        props = picker(client.get(address))
        owners = {
            gang["ownerLink"]["name"]: gang["ownerLink"] for gang in props["gangs"]
        }
        assert owners == {
            name: {
                "name": name,
                "href": reverse("user-profile", args=[name]),
                "badge": "guilder",
            }
            for name in ("vex", "kesh")
        }
        assert list(props["badges"]) == ["guilder"]
        assert props["badges"]["guilder"]["label"] == GUILDER.description
        assert props["badges"]["guilder"]["svg"]["tag"] == "svg"

        client.force_login(person)
        props = picker(client.get(address))
        assert [gang["ownerLink"] for gang in props["gangs"]] == [None]
        assert props["badges"] == {}

    def test_the_add_gang_screen_reads_the_badges_once_for_everybody(
        self, table, player, client
    ):
        player(table, "vex")
        address = reverse("n26-campaign-add-gang", args=[table.pk])
        with_one = self._queries(client, address)
        player(table, "kesh")
        player(table, "ash")
        player(table, "nyx")
        with_more = self._queries(client, address)
        assert with_more == with_one

    def test_an_add_gang_post_that_falls_through_costs_what_a_get_costs(
        self, table, player, client
    ):
        """Invalid gang submissions redraw the picker with the same batched badge reads as
        GET. Compare captured ORM queries; session advisory locks use the physical
        connection outside this capture.
        """

        def redraw(path):
            client.get(path)
            with CaptureQueriesContext(connection) as context:
                response = client.post(path, {"gang": "nothing-of-the-kind"})
            assert response.status_code == 200
            assert "That gang is not on this list." in response.content.decode()
            return len(context.captured_queries)

        address = reverse("n26-campaign-add-gang", args=[table.pk])
        player(table, "vex")
        on_get = self._queries(client, address)
        with_one = redraw(address)
        assert with_one == on_get
        player(table, "kesh")
        player(table, "ash")
        player(table, "nyx")
        with_more = redraw(address)
        assert with_more == with_one

    def test_every_screen_under_a_campaign_reads_the_arbitrators_badge_with_it(
        self, table, supporter, player, client
    ):
        """Batch campaign-person badge reads before rendering. Per-account reads must
        remain limited to the signed-in reader, matching the account header on a page
        outside the campaign.
        """
        from n26.core.models import Gang
        from n26.tests.sandbox.actions import (
            add_asset,
            add_campaign_asset_type,
            assign_asset,
            create_campaign_asset,
            create_campaign_table,
        )

        person = player(table, "vex")
        gang = Gang.objects.get(owner=person)
        racket = add_campaign_asset_type(table, "Racket")
        unheld = add_asset(table, create_campaign_asset(table, racket, "Protection"))
        held = add_asset(table, create_campaign_asset(table, racket, "Smuggling"))
        assign_asset(held, gang)
        rackets = create_campaign_table(table, racket, "Rackets", dice="d6")
        screens = [
            reverse("n26-edit-campaign", args=[table.pk]),
            reverse("n26-archive-campaign", args=[table.pk]),
            reverse("n26-campaign-add-gang", args=[table.pk]),
            reverse("n26-campaign-add-player", args=[table.pk]),
            reverse("n26-campaign-remove-player", args=[table.pk, person.pk]),
            reverse("n26-campaign-add-battle", args=[table.pk]),
            reverse("n26-campaign-add-asset", args=[table.pk]),
            reverse("n26-campaign-asset-assign", args=[table.pk, unheld.pk]),
            reverse("n26-campaign-asset-unassign", args=[table.pk, held.pk]),
            reverse("n26-campaign-asset-remove", args=[table.pk, unheld.pk]),
            reverse("n26-campaign-asset-transfer", args=[table.pk, held.pk]),
            reverse("n26-campaign-add-asset-type", args=[table.pk]),
            reverse("n26-campaign-edit-asset-type", args=[table.pk, racket.pk]),
            reverse("n26-campaign-new-asset", args=[table.pk]),
            reverse("n26-campaign-add-counter", args=[table.pk]),
            reverse("n26-campaign-add-label", args=[table.pk]),
            reverse("n26-campaign-tables", args=[table.pk]),
            reverse("n26-campaign-new-table", args=[table.pk]),
            reverse("n26-campaign-table", args=[table.pk, rackets.pk]),
        ]

        def grants_read(path):
            with CaptureQueriesContext(connection) as context:
                response = client.get(path)
            assert response.status_code == 200, path
            grants = [
                q["sql"]
                for q in context.captured_queries
                if 'FROM "accounts_badgegrant"' in q["sql"]
            ]
            for_one = [sql for sql in grants if '"user_id" = ' in sql]
            for_the_page = [sql for sql in grants if '"user_id" IN (' in sql]
            return for_one, for_the_page

        own = f'"accounts_badgegrant"."user_id" = {supporter.pk}'
        own_reads, _ = grants_read("/n26/")
        assert own_reads and all(own in sql for sql in own_reads)
        for screen in screens:
            for_one, for_the_page = grants_read(screen)
            assert for_the_page, screen
            assert len(for_one) == len(own_reads), (screen, for_one)
            assert all(own in sql for sql in for_one), (screen, for_one)

    def test_a_post_that_does_not_act_draws_the_page_with_the_badges_in_hand(
        self, table, player, client
    ):
        """A refused POST must load the same batched badge data as GET before redrawing the
        form.
        """
        player(table, "vex")
        refused = [
            (
                reverse("n26-campaign-add-gang", args=[table.pk]),
                {"gang": "nothing-of-the-kind"},
            ),
            (reverse("n26-edit-campaign", args=[table.pk]), {"name": ""}),
            # Exercise the shared additions-page renderer through one of its counter
            # views.
            (reverse("n26-campaign-add-counter", args=[table.pk]), {"name": ""}),
        ]

        def grants(fetch, *args):
            with CaptureQueriesContext(connection) as context:
                response = fetch(*args)
            assert response.status_code == 200
            return [
                q["sql"]
                for q in context.captured_queries
                if 'FROM "accounts_badgegrant"' in q["sql"]
                and '"user_id" IN (' in q["sql"]
            ]

        for address, payload in refused:
            drawn = grants(client.get, address)
            redrawn = grants(client.post, address, payload)
            assert redrawn and len(redrawn) == len(drawn), address

    def test_a_post_that_acts_reads_nobodys_badge(
        self, table, supporter, player, gang_type, client
    ):
        """Successful POSTs redirect without rendering names, so skip badge-grant queries.
        The destination loads its own display data.
        """
        from n26.core.models import Gang
        from n26.tests.sandbox.actions import (
            add_asset,
            add_campaign_asset_type,
            assign_asset,
            create_campaign_asset,
            found_gang,
        )

        person = player(table, "vex")
        theirs = Gang.objects.get(owner=person)
        racket = add_campaign_asset_type(table, "Racket")
        unheld = add_asset(table, create_campaign_asset(table, racket, "Protection"))
        held = add_asset(table, create_campaign_asset(table, racket, "Smuggling"))
        assign_asset(held, theirs)
        mine = found_gang("The Arbitrator's Own", gang_type, owner=supporter)

        acts = [
            (
                reverse("n26-edit-campaign", args=[table.pk]),
                {"name": "Dust Falls", "budget": 1000, "summary": ""},
            ),
            (reverse("n26-campaign-add-gang", args=[table.pk]), {"gang": str(mine.pk)}),
            (reverse("n26-campaign-asset-unassign", args=[table.pk, held.pk]), {}),
            (reverse("n26-campaign-asset-remove", args=[table.pk, unheld.pk]), {}),
            (reverse("n26-campaign-remove-player", args=[table.pk, person.pk]), {}),
            # Archive last because the remaining endpoints require an active campaign.
            (reverse("n26-archive-campaign", args=[table.pk]), {}),
        ]
        for address, payload in acts:
            with CaptureQueriesContext(connection) as context:
                response = client.post(address, payload)
            assert response.status_code == 302, (address, response.status_code)
            grants = [
                q["sql"]
                for q in context.captured_queries
                if 'FROM "accounts_badgegrant"' in q["sql"]
            ]
            assert not grants, (address, grants)

    def test_every_screen_under_a_campaign_says_whether_it_will_draw_anybody(self):
        """Discover campaign-fetch calls and require POST-capable views to choose
        with_owner_badge explicitly. The default display fetch would otherwise read
        grants on requests that only write and redirect.
        """
        import ast
        from pathlib import Path as _Path

        from n26.core import views as n26_views

        # Find the source through the package path because campaigns also names an
        # exported view function.
        source = (_Path(n26_views.__file__).parent / "campaigns.py").read_text()
        tree = ast.parse(source)
        guards = {"_any_campaign_or_404", "_own_campaign_or_404"}
        checked, silent = [], []
        for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
            found = [
                call
                for call in ast.walk(fn)
                if isinstance(call, ast.Call)
                and (getattr(call.func, "id", None) or getattr(call.func, "attr", None))
                in guards
            ]
            if not found:
                continue
            said = {k.arg for k in found[0].keywords}
            asks_the_method = any(
                "request.method" in ast.unparse(k.value)
                for k in found[0].keywords
                if k.arg == "with_owner_badge"
            )
            takes_a_post = any(
                isinstance(node, ast.If)
                and "request.method" in ast.unparse(node.test)
                and "POST" in ast.unparse(node.test)
                and "!=" not in ast.unparse(node.test)
                for node in ast.walk(fn)
            )
            checked.append(fn.name)
            if takes_a_post and not asks_the_method and "with_owner_badge" not in said:
                silent.append(fn.name)
        assert len(checked) > 20, checked
        assert not silent, (
            "These views act on a POST and leave, but fetch the campaign with "
            "the default that reads the arbitrator's badge grants for a page "
            "they will not draw. Pass with_owner_badge=request.method == "
            '"GET", or with_owner_badge=False where nothing is ever drawn: '
            f"{silent}"
        )

    def test_the_remove_player_question_names_them_with_their_badge(
        self, table, player, client
    ):
        """Fetch the removed participant's badge with their account so confirmation queries
        are the same for badged and plain accounts.
        """
        from n26.core.campaigns import campaign_operation

        badged = player(table, "vex")
        plain = User.objects.create_user("kesh")
        with campaign_operation(table, actor=table.owner) as act:
            act.invite(plain)

        def remove(person):
            return reverse("n26-campaign-remove-player", args=[table.pk, person.pk])

        body = client.get(remove(badged)).content.decode()
        question = body[body.index("Choose what happens to their gang") :]
        assert "vex" in question
        assert badge_svg(GUILDER).strip() in question
        badged_queries = self._queries(client, remove(badged))
        plain_queries = self._queries(client, remove(plain))
        assert badged_queries == plain_queries

    def test_an_invitation_names_its_arbitrator_with_their_badge(self, table, client):

        from n26.core.campaigns import campaign_operation

        person = User.objects.create_user("vex")
        with campaign_operation(table, actor=table.owner) as act:
            act.invite(person)
        client.force_login(person)

        body = client.get("/n26/campaigns/").content.decode()
        invitations = body[body.index(">Invitations<") :]
        assert re.search(r"from\s*<a[^>]*><span[^>]*>patron<", invitations)
        assert reverse("user-profile", args=[table.owner.username]) in invitations
        assert badge_svg(GUILDER).strip() in invitations

    def test_the_list_reads_the_badges_once_for_every_invitation(
        self, supporter, campaign_type, client
    ):
        from n26.core.campaigns import campaign_operation
        from n26.tests.sandbox.actions import found_campaign

        campaigns = [
            found_campaign(f"Campaign {index}", campaign_type, owner=supporter)
            for index in range(4)
        ]
        person = User.objects.create_user("vex")
        with campaign_operation(campaigns[0], actor=supporter) as act:
            act.invite(person)
        client.force_login(person)
        with_one = self._queries(client, "/n26/campaigns/")
        for campaign in campaigns[1:]:
            with campaign_operation(campaign, actor=supporter) as act:
                act.invite(person)
        with_more = self._queries(client, "/n26/campaigns/")
        assert with_more == with_one


class TestNoPageDecidesForItself:
    """Discover templates that bypass user-link by supplying usernames directly to
    flair-link. Account badge selection belongs to the shared registry.
    """

    # Exclude user-link itself because it implements account identity through
    # flair-link.
    PAGES = sorted(
        path
        for path in (Path(__file__).resolve().parents[1] / "core" / "templates").rglob(
            "*.html"
        )
        if path.name != "user_link.html"
    )
    NAMED_FLAIR = re.compile(r"<c-n26\.flair-link[^>]*username", re.DOTALL)

    def test_there_is_something_to_check(self):
        assert len(self.PAGES) > 50

    def test_no_template_hangs_a_persons_name_on_a_bare_flair_link(self):
        offenders = [
            str(path)
            for path in self.PAGES
            if self.NAMED_FLAIR.search(path.read_text())
        ]
        assert not offenders, (
            "These draw a username with a badge slot they fill themselves. Use "
            '<c-n26.user-link :user="…" />, which asks the platform\'s registry '
            f"which badge that person actually holds: {offenders}"
        )


class TestTheBadgeAsData:
    """Export badges as element trees restricted to the platform SVG allowlist, with React
    attribute names.
    """

    def test_the_staff_mark_crosses_with_its_drawing(self):
        from n26.badges import badge_mark

        mark = badge_mark(STAFF_BADGE)
        assert mark["label"] == STAFF_BADGE.description
        svg = mark["svg"]
        assert svg["tag"] == "svg"
        assert svg["props"]["viewBox"] == "0 0 24 24"
        assert svg["props"]["shapeRendering"] == "geometricPrecision"
        # The wrapper supplies the accessible name; the React renderer hides the SVG
        # itself.
        assert "aria-hidden" not in svg["props"]
        paths = [child for child in svg["children"] if child["tag"] == "path"]
        assert paths
        assert all(path["props"]["d"] and path["props"]["fill"] for path in paths)

    def test_anything_that_could_run_or_fetch_is_left_behind(self):
        from n26.badges import svg_tree

        tree = svg_tree(
            '<svg viewBox="0 0 1 1" onload="x()"><script>alert(1)</script>'
            "<foreignObject><div>hi</div></foreignObject>"
            '<a href="javascript:x()"><path d="M0 0"/></a>'
            '<use href="https://example.com/x.svg#a"/><use href="#a"/>'
            '<path d="M1 1" onclick="y()" style="fill:red"/>'
            '<linearGradient id="g" gradientUnits="userSpaceOnUse">'
            '<stop offset="0" stop-color="red"/></linearGradient>'
            "<title>Mark</title></svg>"
        )
        assert tree["props"] == {"viewBox": "0 0 1 1"}
        children = tree["children"]
        assert [child["tag"] for child in children] == [
            "use",
            "use",
            "path",
            "linearGradient",
            "title",
        ]
        assert children[0]["props"] == {}
        assert children[1]["props"] == {"href": "#a"}
        assert children[2]["props"] == {"d": "M1 1"}
        assert children[3]["props"] == {"id": "g", "gradientUnits": "userSpaceOnUse"}
        assert children[3]["children"][0]["props"] == {
            "offset": "0",
            "stopColor": "red",
        }
        assert children[4]["children"] == ["Mark"]

    def test_a_paint_or_clip_from_outside_the_drawing_is_dropped(self):
        from n26.badges import svg_tree

        tree = svg_tree(
            '<svg><rect fill="url(https://example.com/p.svg#x)" '
            'clip-path="url(#c)" stroke="URL( https://example.com/s )"/></svg>'
        )
        assert tree["children"][0]["props"] == {"clipPath": "url(#c)"}

    def test_the_browser_checks_the_same_attribute_names(self):
        from n26.badges import SVG_PROPS

        assert {"viewBox", "strokeWidth", "className", "href"} <= set(SVG_PROPS)
        assert not [name for name in SVG_PROPS if name.lower().startswith("on")]
        assert "style" not in SVG_PROPS

    def test_a_same_document_reference_is_kept_trimmed(self):
        from n26.badges import svg_tree

        tree = svg_tree('<svg><use href=" #mark"/></svg>')
        assert tree["children"][0]["props"] == {"href": "#mark"}

    def test_the_browser_checks_the_platforms_own_tag_list(self):
        from gyrinx.svg import SVG_ALLOWED_TAGS
        from n26.badges import SVG_TAGS

        assert set(SVG_TAGS) == SVG_ALLOWED_TAGS

    def test_markup_with_no_svg_gives_nothing(self):
        from n26.badges import svg_tree

        assert svg_tree("<div>not a drawing</div>") is None
