"""Verify N26 access rules, shared changelog pages, shell navigation, notifications and
gang founding. Use real platform services and edition data to check their integration.
"""

import json
import re

import pytest
from bs4 import BeautifulSoup
from django.contrib.auth.models import User

from n26.core.views.changelog import CHANGELOG_TAG

pytestmark = [pytest.mark.django_db, pytest.mark.core]


@pytest.fixture
def tester(client):
    """Authenticated ordinary user without staff permissions or grants."""
    user = User.objects.create_user("tester")
    client.force_login(user)
    return user


class TestWhoGetsIn:
    def test_anonymous_is_sent_to_sign_in_and_back(self, client, default_pack):
        response = client.get("/n26/")
        assert response.status_code == 302
        assert "login" in response["Location"]
        assert "next=/n26/" in response["Location"]

    def test_a_signed_in_reader_is_let_in(self, tester, client, default_pack):
        assert client.get("/n26/").status_code == 200

    def test_staff_are_let_in_too(self, client, default_pack):
        client.force_login(User.objects.create_user("boss", is_staff=True))
        assert client.get("/n26/").status_code == 200

    def test_a_visitor_reaches_no_player_page(self, client, default_pack):
        """Require authentication for the dashboard, gang listing and founding form."""
        for address in (
            "/n26/",
            "/n26/gangs/",
            "/n26/gangs/new/",
        ):
            response = client.get(address)
            assert response.status_code == 302, address
            assert "login" in response["Location"], address

    def test_the_workshop_pages_want_staff(self, tester, client, default_pack):

        for address in ("/n26/authoring/", "/n26/design/"):
            response = client.get(address)
            assert response.status_code == 302, address
            assert "login" in response["Location"], address


class TestTheDashboard:
    def test_it_greets_the_user_with_empty_sections(self, tester, client, default_pack):
        body = client.get("/n26/").content.decode()
        assert "tester" in body
        assert "No gangs yet" in body

    def test_it_lists_only_the_users_own_gangs(
        self, tester, client, default_pack, gang_type, make_profile
    ):
        from n26.tests.sandbox.actions import found_gang

        found_gang("The Bad Girls", gang_type, owner=tester)
        found_gang(
            "Someone Else's Problem",
            gang_type,
            owner=User.objects.create_user("rival"),
        )

        body = client.get("/n26/").content.decode()
        assert "The Bad Girls" in body
        assert "Someone Else&#x27;s Problem" not in body
        assert "Someone Else" not in body


def changelog_entry(title, *tags, body="", date="2026-08-07", owner=None):
    """Create a shared changelog entry and any missing tags."""
    from gyrinx.site.models import ChangelogEntry, ChangelogEntryTag

    entry = ChangelogEntry.objects.create(
        date=date, title=title, body=body, owner=owner
    )
    for name in tags:
        tag, _ = ChangelogEntryTag.objects.get_or_create(name=name)
        entry.tags.add(tag)
    return entry


class TestTheChangelogPanel:
    """Limit dashboard updates to entries tagged for N26, matching tags case-insensitively
    without duplicating entries.
    """

    def test_it_lists_the_entries_tagged_for_this_edition(
        self, tester, client, default_pack
    ):
        changelog_entry(
            "The Trading Post opened",
            CHANGELOG_TAG,
            body="<p>Everything with a <strong>TP price</strong> is there.</p>",
        )
        body = client.get("/n26/").content.decode()
        assert "The Trading Post opened" in body
        assert "7 Aug" in body
        assert "<strong>TP price</strong>" in body

    def test_it_leaves_out_the_other_editions_news_and_the_untagged(
        self, tester, client, default_pack
    ):
        changelog_entry("Vehicles came to the old edition", "N23")
        changelog_entry("Nobody said who this was for")
        body = client.get("/n26/").content.decode()
        assert "old edition" not in body
        assert "Nobody said" not in body

    def test_a_tag_spelled_in_another_case_is_the_same_tag(
        self, tester, client, default_pack
    ):
        """Stored tags are case-sensitive, so match equivalent names without regard to
        case.
        """
        changelog_entry("Written in lower case", CHANGELOG_TAG.lower())
        assert "Written in lower case" in client.get("/n26/").content.decode()

    def test_an_entry_wearing_two_spellings_is_still_one_entry(
        self, tester, client, default_pack
    ):
        """Deduplicate join results when both case variants are attached to one entry."""
        changelog_entry("Tagged twice over", CHANGELOG_TAG, CHANGELOG_TAG.lower())
        body = client.get("/n26/").content.decode()
        assert body.count("Tagged twice over") == 1

    def test_it_says_there_is_nothing_rather_than_showing_a_bare_heading(
        self, tester, client, default_pack
    ):

        changelog_entry("Not for this edition", "N23")
        body = client.get("/n26/").content.decode()
        assert "Latest updates" in body
        assert "Nothing new yet." in body

    def test_the_body_is_sanitised(self, tester, client, default_pack):
        changelog_entry(
            "A careless entry",
            CHANGELOG_TAG,
            body='<script>alert("no")</script><p>fine</p>',
        )
        body = client.get("/n26/").content.decode()
        preview = BeautifulSoup(body, "html.parser").select_one(".n26-clamp-2")
        assert preview is not None
        assert preview.find("script") is None
        assert preview.get_text(strip=True) == "fine"

    def test_the_panel_costs_the_same_queries_however_many_entries_exist(
        self, tester, client, default_pack
    ):
        """Compare query growth using owned entries so accidental owner lookups remain
        visible. Warm the session before measuring to exclude its initial write.
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        client.get("/n26/")

        for i in range(2):
            changelog_entry(f"Entry {i}", CHANGELOG_TAG, owner=tester)
        with CaptureQueriesContext(connection) as with_two:
            assert client.get("/n26/").status_code == 200

        for i in range(2, 10):
            changelog_entry(f"Entry {i}", CHANGELOG_TAG, owner=tester)
        with CaptureQueriesContext(connection) as with_ten:
            assert client.get("/n26/").status_code == 200

        assert len(with_ten.captured_queries) == len(with_two.captured_queries)


class TestTheChangelogLinks:
    """The dashboard previews rich entries and leads to their full pages."""

    def test_each_entry_links_to_its_full_page(self, tester, client, default_pack):
        entry = changelog_entry("Trading post", CHANGELOG_TAG)

        body = client.get("/n26/").content.decode()

        assert f"/changelog/{entry.pk}/?tag=N26" in body

    def test_the_heading_links_to_every_update(self, tester, client, default_pack):
        body = client.get("/n26/").content.decode()

        assert 'href="/changelog/?tag=N26"' in body
        assert "View all" in body


class TestTheChangelogIndex:
    """Show public live updates across editions and optionally filter them by tag. The
    footer opens the unfiltered feed; the N26 dashboard supplies its tag.
    """

    def test_anybody_may_read_it_without_an_account(self, client, default_pack):
        assert client.get("/changelog/").status_code == 200

    def test_it_lists_every_entry_not_just_the_dashboards_five(
        self, client, default_pack
    ):
        for i in range(7):
            changelog_entry(f"Entry number {i}", CHANGELOG_TAG)

        body = client.get("/changelog/").content.decode()

        assert "Entry number 0" in body
        assert "Entry number 6" in body

    def test_it_lists_every_editions_live_news(self, client, default_pack):
        changelog_entry("The N26 entry", CHANGELOG_TAG)
        changelog_entry("The old edition entry", "N23")
        changelog_entry("The untagged entry")
        archived = changelog_entry("The archived entry", CHANGELOG_TAG)
        archived.archive()

        body = client.get("/changelog/").content.decode()

        assert "The N26 entry" in body
        assert "The old edition entry" in body
        assert "The untagged entry" in body
        assert "The archived entry" not in body
        assert "Changes on Gyrinx." in body

    def test_a_tag_query_keeps_only_that_tag(self, client, default_pack):
        changelog_entry("The N26 entry", CHANGELOG_TAG)
        changelog_entry("The old edition entry", "N23")
        changelog_entry("The untagged entry")

        body = client.get("/changelog/?tag=N26").content.decode()

        assert "The N26 entry" in body
        assert "The old edition entry" not in body
        assert "The untagged entry" not in body
        assert "Changes tagged N26." in body
        assert "Nothing tagged N26 yet." not in body

    def test_a_tag_spelled_in_another_case_selects_the_stored_tag(
        self, client, default_pack
    ):
        changelog_entry("Written in lower case", CHANGELOG_TAG)

        body = client.get("/changelog/?tag=n26").content.decode()
        filters = tag_filters(body)

        assert "Written in lower case" in body
        assert "Changes tagged N26." in body
        assert 'aria-current="page"' in filters
        assert "N26" in filters

    def test_an_unknown_tag_lists_nothing_and_names_the_tag(self, client, default_pack):
        changelog_entry("The N26 entry", CHANGELOG_TAG)

        body = client.get("/changelog/?tag=Nope").content.decode()

        assert "The N26 entry" not in body
        assert "Nothing tagged Nope yet." in body
        assert "Changes tagged Nope." in body

    def test_a_query_longer_than_a_tag_name_does_not_select_that_prefix(
        self, client, default_pack
    ):
        name = "N" * 100
        changelog_entry("The full-length tag", name)

        body = client.get(f"/changelog/?tag={name}x").content.decode()

        assert "The full-length tag" not in body
        assert "Nothing matches that tag." in body
        assert f"Changes tagged {name}" not in body

    def test_two_spellings_of_a_tag_are_one_chip(self, client, default_pack):
        changelog_entry("One spelling", "N26")
        changelog_entry("The other spelling", "n26")

        filters = tag_filters(client.get("/changelog/").content.decode())

        assert filters.count("tag=N26") == 1
        assert "tag=n26" not in filters

    def test_tags_are_coloured_and_the_chosen_one_is_marked(self, client, default_pack):
        changelog_entry("Both editions", "N26", "N23")
        from gyrinx.site.models import ChangelogEntryTag

        ChangelogEntryTag.objects.filter(name="N26").update(colour="sky")
        ChangelogEntryTag.objects.filter(name="N23").update(colour="amber")

        body = client.get("/changelog/?tag=N26").content.decode()
        filters = tag_filters(body)

        assert "bg-sky-600" in filters
        assert "bg-amber-100" in filters
        assert "bg-sky-600" in body
        assert "bg-amber-600" in body

    def test_the_footer_address_serves_entries_rather_than_the_flat_page(
        self, tester, client, default_pack
    ):
        from django.contrib.flatpages.models import FlatPage
        from django.contrib.sites.models import Site

        page = FlatPage.objects.create(
            url="/changelog/",
            title="Changelog",
            content="<p>STATIC CHANGELOG SENTINEL</p>",
        )
        page.sites.add(Site.objects.get_current())
        changelog_entry("Vehicles came to the old edition", "N23")

        body = client.get("/changelog/").content.decode()
        home = client.get("/").content.decode()
        n26_home = client.get("/n26/").content.decode()

        assert "STATIC CHANGELOG SENTINEL" not in body
        assert "Vehicles came to the old edition" in body
        assert 'href="/changelog/"' in home
        assert ">Changelog" in home
        assert 'href="/changelog/"' in n26_home

    def test_it_deduplicates_two_spellings_and_orders_newest_first(
        self, client, default_pack
    ):
        changelog_entry(
            "The newest entry",
            CHANGELOG_TAG,
            CHANGELOG_TAG.lower(),
            date="2026-08-19",
        )
        changelog_entry("The older entry", CHANGELOG_TAG, date="2026-08-01")

        body = client.get("/changelog/").content.decode()
        sidebar = body[body.index("<aside") : body.index("</aside>")]
        listing = body[body.index("<section", body.index("</aside>")) :]

        assert sidebar.count("The newest entry") == 1
        assert listing.count("The newest entry") == 1
        assert in_order(listing, "The newest entry", "The older entry") == sorted(
            in_order(listing, "The newest entry", "The older entry")
        )

    def test_the_sidebar_links_every_entry_in_the_same_order(
        self, client, default_pack
    ):
        newest = changelog_entry("Newest in the menu", CHANGELOG_TAG, date="2026-08-19")
        oldest = changelog_entry("Oldest in the menu", CHANGELOG_TAG, date="2026-08-01")
        other = changelog_entry("Also in the menu", "N23", date="2026-08-20")

        body = client.get("/changelog/").content.decode()
        sidebar = body[body.index("<aside") : body.index("</aside>")]

        positions = in_order(
            sidebar, "Also in the menu", "Newest in the menu", "Oldest in the menu"
        )
        assert positions == sorted(positions)
        assert f"/changelog/{newest.pk}/" in sidebar
        assert f"/changelog/{oldest.pk}/" in sidebar
        assert f"/changelog/{other.pk}/" in sidebar
        assert 'aria-current="page"' not in sidebar

    def test_a_tag_query_drops_other_editions_from_the_menu(self, client, default_pack):
        newest = changelog_entry("Newest in the menu", CHANGELOG_TAG, date="2026-08-19")
        changelog_entry("Not in the menu", "N23", date="2026-08-20")

        body = client.get("/changelog/?tag=N26").content.decode()
        sidebar = body[body.index("<aside") : body.index("</aside>")]

        assert f"/changelog/{newest.pk}/?tag=N26" in sidebar
        assert "Not in the menu" not in sidebar

    def test_entries_are_rich_sanitised_previews_that_open_the_full_page(
        self, client, default_pack
    ):
        entry = changelog_entry(
            "A careful preview",
            CHANGELOG_TAG,
            body='<script>alert("no")</script><ul><li><strong>Safe</strong></li></ul>',
        )

        body = client.get("/changelog/").content.decode()

        assert "alert" not in body
        assert "<ul><li><strong>Safe</strong></li></ul>" in body
        assert f"/changelog/{entry.pk}/" in body

    def test_the_index_costs_the_same_queries_however_many_entries_exist(
        self, client, default_pack
    ):
        """Prefetch tags with their entries to avoid one lookup per displayed entry."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        client.get("/changelog/")

        for i in range(2):
            changelog_entry(f"Entry {i}", CHANGELOG_TAG if i % 2 else "N23")
        with CaptureQueriesContext(connection) as with_two:
            assert client.get("/changelog/").status_code == 200

        for i in range(2, 10):
            changelog_entry(f"Entry {i}", CHANGELOG_TAG if i % 2 else "N23")
        with CaptureQueriesContext(connection) as with_ten:
            assert client.get("/changelog/").status_code == 200

        assert len(with_ten.captured_queries) == len(with_two.captured_queries)


class TestOneChangelogEntry:
    """A public detail page shows the complete entry and an ordered menu."""

    def test_anybody_may_read_the_full_rich_entry(self, client, default_pack):
        entry = changelog_entry(
            "Everything in this update",
            CHANGELOG_TAG,
            body=(
                "<p>The opening.</p>"
                "<ul><li><strong>First point</strong></li><li>Second point</li></ul>"
            ),
        )

        response = client.get(f"/changelog/{entry.pk}/")
        body = response.content.decode()

        assert response.status_code == 200
        assert "<p>The opening.</p>" in body
        assert "<ul><li><strong>First point</strong></li>" in body
        assert "n26-clamp-2" not in body
        assert "bg-ink-700" in body
        assert "dark:bg-ink-300" in body

    @pytest.mark.parametrize("query", ["", "?tag=N26"])
    def test_entry_tags_open_the_filtered_feed_without_detail_filters(
        self, client, default_pack, query
    ):
        from urllib.parse import urlencode

        name = "Tools & fixes / café"
        entry = changelog_entry("A tagged update", "N26", name)
        response = client.get(f"/changelog/{entry.pk}/{query}")
        page = BeautifulSoup(response.content, "html.parser")
        assert page.select_one('nav[aria-label="Filter by tag"]') is None
        assert "filter_tags" not in response.context
        links = {
            link.get_text(strip=True): link["href"] for link in page.select("article a")
        }
        assert links[name] == f"/changelog/?{urlencode({'tag': name})}"
        feed = client.get(links[name])
        assert [item.pk for item in feed.context["entries"]] == [entry.pk]

    def test_the_full_body_is_sanitised(self, client, default_pack):
        entry = changelog_entry(
            "A careful entry",
            CHANGELOG_TAG,
            body='<script>alert("no")</script><p><strong>Safe</strong></p>',
        )

        body = client.get(f"/changelog/{entry.pk}/").content.decode()

        assert "alert" not in body
        assert "<strong>Safe</strong>" in body

    @pytest.mark.parametrize("tags", [("N23",), ()])
    def test_an_entry_for_any_edition_is_readable(self, client, default_pack, tags):
        entry = changelog_entry("For whichever edition", *tags)

        assert client.get(f"/changelog/{entry.pk}/").status_code == 200

    def test_an_archived_entry_is_not_reachable(self, client, default_pack):
        entry = changelog_entry("Archived news", CHANGELOG_TAG)
        entry.archive()

        assert client.get(f"/changelog/{entry.pk}/").status_code == 404

    def test_an_unknown_or_malformed_id_is_a_404(self, client, default_pack):
        from uuid import uuid4

        assert client.get(f"/changelog/{uuid4()}/").status_code == 404
        assert client.get("/changelog/not-a-uuid/").status_code == 404
        assert client.get("/n26/changelog/not-a-uuid/").status_code == 404

    def test_the_old_edition_address_opens_the_shared_page_on_n26(
        self, client, default_pack
    ):
        entry = changelog_entry("Still linked from somewhere", CHANGELOG_TAG)

        index = client.get("/n26/changelog/", follow=False)
        detail = client.get(f"/n26/changelog/{entry.pk}/", follow=False)

        assert index.status_code == 301
        assert index["Location"] == "/changelog/?tag=N26"
        assert detail.status_code == 301
        assert detail["Location"] == f"/changelog/{entry.pk}/?tag=N26"

    @pytest.mark.parametrize("tags", [("N23",), ()])
    def test_the_old_detail_address_404s_for_an_entry_that_was_not_n26(
        self, client, default_pack, tags
    ):
        entry = changelog_entry("Not this edition", *tags)

        assert client.get(f"/n26/changelog/{entry.pk}/").status_code == 404

    def test_the_old_detail_address_404s_for_an_archived_or_unknown_entry(
        self, client, default_pack
    ):
        from uuid import uuid4

        archived = changelog_entry("Gone from the old page", CHANGELOG_TAG)
        archived.archive()

        assert client.get(f"/n26/changelog/{archived.pk}/").status_code == 404
        assert client.get(f"/n26/changelog/{uuid4()}/").status_code == 404

    def test_the_sidebar_lists_every_entry_newest_first_and_marks_this_one(
        self, client, default_pack
    ):
        import re

        current = changelog_entry("The current entry", CHANGELOG_TAG, date="2026-08-10")
        changelog_entry("The newest entry", CHANGELOG_TAG, date="2026-08-19")
        changelog_entry("The oldest entry", CHANGELOG_TAG, date="2026-08-01")
        changelog_entry("The other edition", "N23", date="2026-08-20")

        body = client.get(f"/changelog/{current.pk}/?tag=N26").content.decode()
        sidebar = body[body.index("<aside") : body.index("</aside>")]

        positions = in_order(
            sidebar, "The newest entry", "The current entry", "The oldest entry"
        )
        assert positions == sorted(positions)
        assert "The other edition" not in sidebar
        current_url = f"/changelog/{current.pk}/?tag=N26"
        anchor = re.search(
            rf'<a[^>]*href="{re.escape(current_url)}"[^>]*>',
            sidebar,
        )
        assert anchor is not None
        assert 'aria-current="page"' in anchor.group()
        assert "is-current" in anchor.group()


TELEPORT = '<template x-teleport="body">'


def nav_drawer(body):
    """Extract the teleported drawer template from the header, excluding the repeated
    no-script navigation links.
    """
    header = body[body.index("<header") : body.index("</header>")]
    start = header.index(TELEPORT)
    return header[start : header.index("</template>", start)]


def without_noscript(text):
    """Remove all no-script blocks before comparing navigation markup, since the switcher
    and drawer each provide a fallback.
    """
    while "<noscript>" in text:
        start = text.index("<noscript>")
        end = text.index("</noscript>", start) + len("</noscript>")
        text = text[:start] + text[end:]
    return text


def nav_bar(body):
    """Extract header controls without the drawer or repeated no-script links."""
    header = body[body.index("<header") : body.index("</header>")]
    start = header.index(TELEPORT)
    end = header.index("</template>", start) + len("</template>")
    return without_noscript(header[:start] + header[end:])


def nav_noscript(body):
    """Extract the final no-script navigation block from the header. Earlier blocks belong
    to the switcher.
    """
    header = body[body.index("<header") : body.index("</header>")]
    start = header.rindex("<noscript>")
    return header[start : header.index("</noscript>", start)]


def account_menu(body):
    """Read account-menu island props from the rendered page."""
    soup = BeautifulSoup(body, "html.parser")
    host = soup.select_one('[data-react-name="account-menu"]')
    return json.loads(soup.find(id=host["data-react-props"]).string)


def menu_rows(menu):
    """Flatten menu entries into kind-label pairs in display order, preserving group
    headings.
    """
    rows = []

    def walk(entries):
        for entry in entries:
            kind = entry["type"]
            if kind == "person":
                rows.append(("person", menu["person"]["name"]))
            elif kind == "group":
                rows.append(("group", entry["label"]))
                walk(entry["items"])
            elif kind in ("separator", "theme"):
                rows.append((kind, ""))
            else:
                rows.append((kind, entry["label"]))

    walk(menu["items"])
    return rows


def menu_words(menu):
    return [words for _, words in menu_rows(menu) if words]


def menu_entry(menu, kind, label=None):
    """Find the first menu entry matching kind and optional label, including grouped
    entries.
    """

    def walk(entries):
        for entry in entries:
            if entry["type"] == kind and label in (None, entry.get("label")):
                return entry
            found = walk(entry.get("items", []))
            if found:
                return found
        return None

    return walk(menu["items"])


def account_button(body):
    """Extract the account-menu trigger button from the navigation bar."""
    bar = nav_bar(body)
    at = bar.index('aria-label="Open account menu')
    return bar[bar.rindex("<button", 0, at) : bar.index("</button>", at)]


def reads_as(markup):
    """Remove markup and normalise whitespace for text comparisons."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", markup)).strip()


def links_in(markup):
    """Map visible link text to parsed anchors."""
    return {
        reads_as(str(link)): link
        for link in BeautifulSoup(markup, "html.parser").find_all("a")
    }


def count_badge(markup):
    """Extract the count from its aria-hidden span, or None when absent."""
    found = re.findall(r'<span\s+aria-hidden="true">\s*(.*?)\s*</span>', markup)
    return found[0] if found else None


def in_order(text, *fragments):
    """Find each fragment's first position for order assertions."""
    return [text.index(fragment) for fragment in fragments]


def tag_filters(body):
    """Extract only the changelog tag-filter navigation."""
    start = body.index('aria-label="Filter by tag"')
    return body[start : body.index("</nav>", start)]


class TestTheFooterHelpColumn:
    """Share top-level platform documentation links and their visibility rules with the
    classic footer.
    """

    @pytest.fixture
    def help_page(self, db):
        from django.contrib.flatpages.models import FlatPage
        from django.contrib.sites.models import Site

        page = FlatPage.objects.create(url="/help/", title="Help")
        page.sites.add(Site.objects.get_current())
        return page

    def test_the_columns_pages_are_the_sites_flatpages(
        self, tester, client, default_pack, help_page
    ):
        body = client.get("/n26/").content.decode()
        assert 'href="/help/"' in body
        assert ">Help" in body

    def test_a_page_gated_to_another_group_is_not_offered(
        self, tester, client, default_pack, help_page
    ):
        from django.contrib.auth.models import Group

        from gyrinx.pages.models import FlatPageVisibility

        gate = FlatPageVisibility.objects.create(page=help_page)
        gate.groups.add(Group.objects.create(name="Somebody Else"))

        body = client.get("/n26/").content.decode()
        assert 'href="/help/"' not in body


class TestTheNavigation:
    """Keep page navigation in the drawer and account actions in the account menu. Verify
    link ordering, accessible names and native fallbacks.
    """

    @pytest.fixture
    def staff(self, client):
        user = User.objects.create_user("boss", is_staff=True)
        client.force_login(user)
        return user

    def test_the_bar_reads_brand_page_then_the_controls(
        self, tester, client, default_pack
    ):
        bar = nav_bar(client.get("/n26/").content.decode())
        positions = in_order(
            bar,
            'href="/n26/"',
            "Home",
            'aria-label="Open account menu"',
            'aria-label="Open navigation menu"',
        )
        assert positions == sorted(positions)

    def test_the_colour_scheme_is_behind_the_account_menu(
        self, tester, client, default_pack
    ):

        body = client.get("/n26/").content.decode()
        assert ("theme", "") in menu_rows(account_menu(body))
        assert 'aria-label="Toggle dark mode"' not in nav_bar(body)

    def test_the_scheme_is_one_control_of_three_and_not_three_rows(
        self, tester, client, default_pack
    ):
        """Keep all three modes in one radio-style theme control within the menu."""
        menu = account_menu(client.get("/n26/").content.decode())
        group = menu_entry(menu, "group", "Theme")
        (theme,) = group["items"]
        assert theme["type"] == "theme"
        # Component interaction tests cover radio behaviour; this integration check
        # supplies every supported mode.
        assert [scheme for scheme, _, _ in theme["choices"]] == [
            "light",
            "dark",
            "system",
        ]

    def test_each_scheme_carries_its_own_drawing(self, tester, client, default_pack):

        menu = account_menu(client.get("/n26/").content.decode())
        theme = menu_entry(menu, "theme")
        assert [icon for _, _, icon in theme["choices"]] == ["sun", "moon", "monitor"]

    def test_the_drawer_holds_the_places_the_app_has(
        self, tester, client, default_pack
    ):
        drawer = nav_drawer(client.get("/n26/").content.decode())
        positions = in_order(
            reads_as(drawer),
            "Home",
            "Gangs",
            "Campaigns",
            "Content Packs",
            "Help",
        )
        assert positions == sorted(positions)

        assert "Create a gang" not in links_in(drawer)

    def test_help_leads_to_the_guides_for_this_edition(
        self, tester, client, default_pack
    ):

        drawer = nav_drawer(client.get("/n26/").content.decode())
        assert 'href="/help/n26/"' in drawer
        assert "Help" in drawer

    def test_the_bar_carries_help_as_an_icon(self, tester, client, default_pack):

        import re

        body = client.get("/n26/").content.decode()
        icon = re.search(r'<a\s[^>]*aria-label="Help"[^>]*>', body)
        assert icon is not None
        assert 'href="/help/n26/"' in icon.group()

    def test_a_place_with_no_page_yet_is_not_a_link(self, tester, client, default_pack):
        """Display Content Packs as text while it has no destination."""
        drawer = nav_drawer(client.get("/n26/").content.decode())
        labels = links_in(drawer)
        assert "Campaigns" in labels
        assert "Content Packs" not in labels
        assert "Content Packs" in reads_as(drawer)

    def test_the_drawer_lists_the_readers_own_gangs(
        self, tester, client, default_pack, gang_type, make_profile
    ):

        from n26.tests.sandbox.actions import found_gang

        gang = found_gang("The Bad Girls", gang_type, owner=tester)

        drawer = nav_drawer(client.get("/n26/").content.decode())
        positions = in_order(
            reads_as(drawer),
            "Gangs",
            "Your gangs",
            "The Bad Girls",
            str(gang_type),
        )
        assert positions == sorted(positions)
        assert f"/n26/gangs/{gang.pk}/" in drawer

    def test_a_gangs_colour_is_a_mark_beside_its_name(
        self, tester, client, default_pack, gang_type, make_profile
    ):
        """Use the palette variable directly because Tailwind cannot discover a dynamically
        constructed colour class.
        """
        from n26.tests.sandbox.actions import found_gang

        gang = found_gang("The Bad Girls", gang_type, owner=tester)
        gang.colour = "violet"
        gang.save()

        drawer = nav_drawer(client.get("/n26/").content.decode())
        assert "background: var(--color-violet-500)" in drawer

    def test_a_gang_with_no_colour_gets_no_mark(
        self, tester, client, default_pack, gang_type, make_profile
    ):

        from n26.tests.sandbox.actions import found_gang

        found_gang("The Bad Girls", gang_type, owner=tester)

        drawer = nav_drawer(client.get("/n26/").content.decode())
        assert "The Bad Girls" in drawer
        assert "background: var(--color-" not in drawer

    def test_nobody_elses_gangs_are_in_it(
        self, tester, client, default_pack, gang_type, make_profile
    ):
        from n26.tests.sandbox.actions import found_gang

        found_gang(
            "Someone Else's Problem",
            gang_type,
            owner=User.objects.create_user("rival"),
        )

        drawer = nav_drawer(client.get("/n26/").content.decode())
        assert "Someone Else" not in drawer
        assert "Your gangs" not in drawer

    def test_a_reader_with_no_gangs_is_shown_no_heading_for_them(
        self, tester, client, default_pack
    ):

        drawer = nav_drawer(client.get("/n26/").content.decode())
        assert "Your gangs" not in drawer

    def test_a_visitor_has_no_gangs_to_list(self, rf, default_pack):
        """Check the template tag directly because anonymous dashboard requests redirect
        before the drawer renders.
        """
        from django.contrib.auth.models import AnonymousUser

        from n26.core.templatetags.navigation import drawer_gangs

        request = rf.get("/n26/")
        request.user = AnonymousUser()
        assert drawer_gangs({"request": request}) == []

    def test_the_links_are_there_for_a_reader_with_no_script(
        self, tester, client, default_pack
    ):
        """The teleported drawer template cannot render without JavaScript, so preserve a
        native list of the same links.
        """
        strip = nav_noscript(client.get("/n26/").content.decode())
        positions = in_order(reads_as(strip), "Home", "Gangs")
        assert positions == sorted(positions)

    def test_the_account_menu_is_you_the_doors_and_the_way_out(
        self, staff, client, default_pack
    ):
        rows = menu_rows(account_menu(client.get("/n26/").content.decode()))
        words = [words for _, words in rows]
        positions = [
            words.index(w)
            for w in (
                "boss",
                "Your account",
                "Staff only",
                "Admin",
                "Content library",
                "Sign out",
            )
        ]
        assert positions == sorted(positions)
        # Separate the account name and sign-out entry without adding a separator for
        # the staff heading.
        assert [kind for kind, _ in rows].count("separator") == 2

    def test_the_menu_says_who_you_are_signed_in_as(self, staff, client, default_pack):
        """Keep the signed-in account name inside the menu when the narrow navigation bar
        hides its label.
        """
        rows = menu_rows(account_menu(client.get("/n26/").content.decode()))
        # Keep the name display separate from the account navigation entry.
        assert rows[0] == ("person", "boss")
        assert rows.index(("link", "Your account")) > 0

    def test_your_account_goes_to_the_page_that_is_actually_there(
        self, staff, client, default_pack
    ):
        """Resolve the shared account route and verify that following it succeeds."""
        from django.urls import reverse

        menu = account_menu(client.get("/n26/").content.decode())
        assert menu_entry(menu, "link", "Your account")["href"] == reverse(
            "core:account_home"
        )
        assert client.get(reverse("core:account_home")).status_code == 200

    def test_the_staff_doors_say_they_are_staff_only(self, staff, client, default_pack):

        menu = account_menu(client.get("/n26/").content.decode())
        staff = menu_entry(menu, "group", "Staff only")
        assert [entry["label"] for entry in staff["items"]][:1] == ["Admin"]

    def test_nobody_else_is_shown_a_door_they_cannot_open(
        self, tester, client, default_pack
    ):
        """Omit both staff-only entries and their group heading for ordinary users."""
        rows = menu_rows(account_menu(client.get("/n26/").content.decode()))
        words = [words for _, words in rows]
        assert "Admin" not in words
        assert "Content library" not in words
        assert "Staff only" not in words

        assert [kind for kind, _ in rows].count("separator") == 2

    def test_the_drawer_is_the_same_list_wherever_you_are(
        self, staff, client, default_pack
    ):
        """Use the same navigation destinations on authoring and player pages."""
        drawer = nav_drawer(client.get("/n26/authoring/").content.decode())
        positions = in_order(
            reads_as(drawer),
            "Home",
            "Gangs",
            "Authoring",
            "Content library",
            "Modifiers",
            "Foundations",
            "Ingest",
        )
        assert positions == sorted(positions)
        assert "App" not in links_in(drawer)

    def test_the_authoring_pages_are_a_section_of_their_own(
        self, staff, client, default_pack
    ):

        drawer = nav_drawer(client.get("/n26/").content.decode())
        assert "Authoring" in drawer
        # Use Authoring for drawer pages, distinct from the account menu's Staff only
        # group.
        assert "Staff only" not in drawer

    def test_nobody_else_sees_the_authoring_section_or_its_rule(
        self, tester, client, default_pack
    ):

        drawer = nav_drawer(client.get("/n26/").content.decode())
        assert "Authoring" not in drawer
        assert "Modifiers" not in reads_as(drawer)

    def test_the_drawer_marks_the_page_on_either_side(
        self, staff, client, default_pack
    ):
        """Mark current destinations through aria-current in both player and authoring
        navigation.
        """

        app = links_in(nav_drawer(client.get("/n26/").content.decode()))["Home"]
        assert app.get("aria-current") == "page"

        authoring = links_in(
            nav_drawer(client.get("/n26/authoring/modifiers/").content.decode()),
        )["Modifiers"]
        assert authoring.get("aria-current") == "page"

    def test_a_screen_inside_a_gang_marks_gangs(
        self, tester, client, default_pack, gang_type
    ):
        """Gang detail pages use the parent Gangs destination as their current navigation
        entry.
        """
        from n26.tests.sandbox.actions import found_gang

        gang = found_gang("The Bad Girls", gang_type, owner=tester, budget=500)

        drawer = nav_drawer(client.get(f"/n26/gangs/{gang.pk}/").content.decode())
        assert links_in(drawer)["Gangs"].get("aria-current") == "page"

    def test_the_authoring_pages_are_in_the_scriptless_strip_too(
        self, staff, client, default_pack
    ):
        """Preserve access to authoring pages when neither the Alpine drawer nor React
        account menu mounts.
        """
        strip = nav_noscript(client.get("/n26/").content.decode())
        assert "Modifiers" in links_in(strip)

    def test_the_drawer_costs_an_authoring_page_no_extra_query(
        self, staff, client, default_pack, gang_type, make_profile
    ):
        """Load the user's first page of gangs once for the complete authoring page."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from n26.core.navigation import SWITCHER_PAGE
        from n26.tests.sandbox.actions import found_gang

        found_gang("The Bad Girls", gang_type, owner=staff)
        client.get("/n26/authoring/")

        with CaptureQueriesContext(connection) as captured:
            assert client.get("/n26/authoring/").status_code == 200
        capped = [
            query
            for query in captured.captured_queries
            if f"LIMIT {SWITCHER_PAGE + 1}" in query["sql"]
            and "n26_gang" in query["sql"]
        ]
        assert len(capped) == 1

    def test_a_page_names_itself_in_the_bar_and_keeps_its_links(
        self, staff, client, default_pack
    ):

        body = client.get("/n26/authoring/modifiers/").content.decode()
        assert "Modifiers" in nav_bar(body)
        assert "Foundations" in links_in(nav_drawer(body))


class TestTheAccountMenuAcrossShells:
    """Share account-menu rendering while allowing each shell to supply its own entries."""

    def test_the_account_pages_keep_their_shorter_menu(self, client, default_pack):
        """Platform account pages supply their own entry ordering without an account-name
        entry or staff group.
        """
        from django.urls import reverse

        client.force_login(User.objects.create_user("boss", is_staff=True))
        body = client.get(reverse("core:account_home")).content.decode()
        rows = menu_rows(account_menu(body))
        assert rows == [
            ("link", "Your account"),
            ("link", "Notifications"),
            ("group", "Theme"),
            ("theme", ""),
            ("link", "Admin"),
            ("link", "Sign out"),
        ]

    def test_a_visitor_has_no_menu_to_open(self, client, default_pack):
        body = client.get("/n26/").content.decode()
        assert 'data-react-name="account-menu"' not in body
        assert "Open account menu" not in body


class TestTheInbox:
    """Link to the shared inbox and reflect the same unread count in the account button and
    menu entry.
    """

    def unread(self, recipient, count):
        """Bulk-create unread notifications without individual notify calls."""
        from gyrinx.site.models import Notification

        Notification.objects.bulk_create(
            Notification(owner=recipient, subject=f"Something happened ({n})")
            for n in range(count)
        )

    def test_the_menu_holds_the_way_to_it(self, tester, client, default_pack):
        menu = account_menu(client.get("/n26/").content.decode())
        assert menu_entry(menu, "link", "Notifications")["href"] == "/notifications/"
        words = menu_words(menu)
        assert words.index("Your account") < words.index("Notifications")

    def test_the_page_it_leads_to_is_actually_there(self, tester, client, default_pack):
        assert client.get("/notifications/").status_code == 200

    def test_the_entry_wears_the_same_pill_as_the_button(
        self, tester, client, default_pack
    ):
        """Supply the same count to the trigger fallback and the menu's shared CountBadge
        component.
        """
        self.unread(tester, 2)
        body = client.get("/n26/").content.decode()
        menu, button = account_menu(body), account_button(body)

        assert menu_entry(menu, "link", "Notifications")["count"] == 2
        assert menu["unread"] == 2
        assert count_badge(button) == "2"

    def test_the_entry_says_what_the_number_means(self, tester, client, default_pack):
        """Provide an accessible count label rather than an unexplained number."""
        self.unread(tester, 2)
        entry = menu_entry(
            account_menu(client.get("/n26/").content.decode()),
            "link",
            "Notifications",
        )
        assert (entry["count"], entry["countLabel"]) == (2, "unread notifications")

    def test_the_button_wears_the_count_on_its_corner(
        self, tester, client, default_pack
    ):
        """Include unread state in the trigger's aria-label because it overrides the
        accessible text of its children.
        """
        self.unread(tester, 2)
        button = account_button(client.get("/n26/").content.decode())
        assert reads_as(button) == "tester 2"
        assert 'aria-label="Open account menu — 2 unread notifications"' in button

    def test_an_empty_inbox_says_nothing_at_all(self, tester, client, default_pack):
        """Omit zero-count badges while retaining the inbox link."""
        body = client.get("/n26/").content.decode()
        assert reads_as(account_button(body)) == "tester"
        assert "unread notifications" not in account_button(body)
        menu = account_menu(body)
        assert menu["unread"] == 0
        assert menu_entry(menu, "link", "Notifications")["count"] == 0

    def test_a_crowded_inbox_stops_counting(self, tester, client, default_pack):
        """Cap the visible count while preserving the full accessible number."""
        self.unread(tester, 120)
        body = client.get("/n26/").content.decode()
        button = account_button(body)
        assert reads_as(button) == "tester 99+"
        # Keep full accessible counts despite the visual cap; component tests check the
        # menu's visible 99+.
        assert 'aria-label="Open account menu — 120 unread notifications"' in button
        assert menu_entry(account_menu(body), "link", "Notifications")["count"] == 120

    def test_only_your_own_is_counted(self, tester, client, default_pack):
        self.unread(User.objects.create_user("rival"), 5)
        self.unread(tester, 1)
        body = client.get("/n26/").content.decode()
        assert reads_as(account_button(body)) == "tester 1"

    def test_one_is_a_notification_not_notifications(
        self, tester, client, default_pack
    ):

        self.unread(tester, 1)
        body = client.get("/n26/").content.decode()
        assert 'aria-label="Open account menu — 1 unread notification"' in (
            account_button(body)
        )
        menu = account_menu(body)
        assert menu["unreadText"] == "1 unread notification"
        entry = menu_entry(menu, "link", "Notifications")
        assert (entry["count"], entry["countLabel"]) == (1, "unread notification")


class TestTheEditionToggle:
    """Show signed-in users their current edition and a link to the other edition's
    dashboard.
    """

    def test_the_n26_bar_offers_the_way_back(self, tester, client, default_pack):
        bar = nav_bar(client.get("/n26/").content.decode())
        assert 'aria-label="Edition"' in bar
        assert 'title="Go to the classic app"' in bar

        assert 'title="You are in the N26 preview"' in bar

    def test_the_way_back_says_the_reader_means_it(self, tester, client, default_pack):
        """Override the remembered N26 preference when linking to the classic root;
        otherwise middleware redirects back to N26.
        """
        bar = nav_bar(client.get("/n26/").content.decode())
        assert 'href="/?edition=n23"' in bar

        response = client.get("/?edition=n23", follow=True)
        assert response.status_code == 200
        assert response.redirect_chain[-1][0] == "/"

    def test_the_pill_sits_left_of_the_account_menu(self, tester, client, default_pack):
        bar = nav_bar(client.get("/n26/").content.decode())
        positions = in_order(
            bar,
            'aria-label="Edition"',
            'aria-label="Open account menu"',
        )
        assert positions == sorted(positions)

    def test_the_classic_bar_offers_the_other_edition(self, tester, client):

        body = client.get("/").content.decode()
        assert 'aria-label="Edition"' in body
        assert 'title="Go to the N26 preview"' in body

    def test_the_classic_bar_offers_it_to_staff(self, client):
        client.force_login(User.objects.create_user("boss", is_staff=True))
        body = client.get("/").content.decode()
        assert 'aria-label="Edition"' in body

    def test_a_visitor_sees_no_pill(self, client):
        assert 'aria-label="Edition"' not in client.get("/").content.decode()


def announcement_bar(body):
    """Extract the announcement from its start to the following closing aside tag. Starting
    the closing-tag search earlier could produce an empty slice and vacuous absence
    assertions.
    """
    start = body.index("n26-announcement")
    return body[start : body.index("</aside>", start)]


class TestTheSiteBanner:
    """Resolve shared semantic icon keys and Bootstrap colour values into N26 announcement
    components.
    """

    @pytest.fixture
    def live_banner(self):
        from gyrinx.site.models import Banner

        def make(**kwargs):
            return Banner.objects.create(
                text="N26 support is coming.", live_n26=True, **kwargs
            )

        return make

    def test_a_key_is_drawn_from_this_editions_own_set(
        self, tester, client, default_pack, live_banner
    ):
        """Choose an icon differing from the tone's default so fallback rendering cannot
        satisfy the assertion.
        """
        from n26.core import icons

        live_banner(icon="success", colour="info")

        body = client.get("/n26/").content.decode()
        assert str(icons.resolve("circle-check").body) in body
        assert str(icons.resolve("info").body) not in body

    def test_a_key_with_no_drawing_here_is_not_fatal(
        self, tester, client, default_pack, live_banner
    ):
        """Unknown stored icon keys must not prevent page rendering, even when written
        outside the current choices.
        """
        live_banner(icon="bi-blockquote-left", colour="primary")

        response = client.get("/n26/")
        assert response.status_code == 200
        assert "N26 support is coming." in response.content.decode()

    def test_an_unresolved_key_leaves_the_icon_the_tone_implies(
        self, tester, client, default_pack, live_banner
    ):

        from n26.core import icons

        live_banner(icon="nonsense", colour="danger")

        body = client.get("/n26/").content.decode()
        assert str(icons.resolve("triangle-alert").body) in body

    def test_a_bootstrap_colour_becomes_an_announcement_tone(
        self, tester, client, default_pack, live_banner
    ):
        """Translate Bootstrap colour values before setting the announcement tone."""
        from django.urls import reverse

        live_banner(colour="primary")

        body = client.get("/n26/").content.decode()
        assert 'data-tone="info"' in body
        assert 'data-tone="primary"' not in body
        assert reverse("core:dismiss-banner") in body
        assert 'x-show="shown"' not in body

    def test_a_colourless_banner_still_gets_a_tone(
        self, tester, client, default_pack, live_banner
    ):
        live_banner(colour="")

        body = client.get("/n26/").content.decode()
        assert 'data-tone="info"' in body

    def test_the_bar_says_only_what_the_bar_was_given(
        self, tester, client, default_pack, gang_type, make_profile, live_banner
    ):
        """Declare the optional action slot so an unrelated page context variable cannot
        become banner content.
        """
        from django.urls import reverse

        from n26.library.models import Skill
        from n26.tests.sandbox.actions import (
            create_category,
            create_collection,
            create_skill,
            found_gang,
            hire_with_option,
            modifier,
            places,
            section_of,
            targets_model,
        )

        # Provide one placed skill set so the skills page can render.
        agility = create_category("Skills", "Agility")
        create_skill("Catfall", category=agility)
        collection = create_collection("Skills", contains=[Skill])
        profile = make_profile("Ganger", price=50)
        modifier(
            "Ganger: Agility under Primary",
            targets_model(),
            places(agility, section_of(collection, "Primary", 0)),
            carried_by=profile,
        )
        gang = found_gang("The Bad Girls", gang_type, owner=tester, budget=500)
        fighter = hire_with_option(gang, profile, "Yolanda")

        live_banner()
        skills_url = reverse("n26-skills", args=[fighter.pk])
        body = client.get(skills_url).content.decode()

        # Keep the page action URL on its form and out of the announcement slot.
        assert f'action="{skills_url}' in body
        bar = announcement_bar(body)
        assert "N26 support is coming." in bar
        assert skills_url not in bar

    def test_closing_the_bar_is_remembered(
        self, tester, client, default_pack, live_banner
    ):
        """Post the rendered dismissal endpoint and banner ID, then verify that the shared
        session state hides it on the next page.
        """
        import json
        import re

        from django.urls import reverse

        banner = live_banner()

        body = client.get("/n26/").content.decode()
        assert "N26 support is coming." in body

        dismiss_url = reverse("core:dismiss-banner")
        assert dismiss_url in body
        # Check the ID posted by dismissal, not just the banner wrapper ID.
        assert re.search(
            rf"{re.escape(dismiss_url)}.*{re.escape(str(banner.id))}", body, re.S
        )

        dismissed = client.post(
            dismiss_url,
            data=json.dumps({"banner_id": str(banner.id)}),
            content_type="application/json",
        )
        assert dismissed.status_code == 200

        assert "N26 support is coming." not in client.get("/n26/").content.decode()

    def test_the_call_to_action_is_counted(
        self, tester, client, default_pack, live_banner
    ):
        """Route the banner link through the platform tracker, preserving its destination
        while recording the click.
        """
        from django.urls import reverse

        from gyrinx.analytics.models import Event, EventVerb
        from gyrinx.analytics.nouns import PlatformNoun

        banner = live_banner(cta_text="Read the notes", cta_url="https://example.com")

        body = client.get("/n26/").content.decode()
        bar = announcement_bar(body)
        tracked = reverse("core:track-banner-click", kwargs={"id": banner.id})
        assert f'href="{tracked}"' in bar
        assert 'href="https://example.com"' not in bar

        followed = client.get(tracked)
        assert followed.status_code == 302
        assert followed.url == "https://example.com"

        assert Event.objects.filter(
            noun=PlatformNoun.BANNER,
            verb=EventVerb.CLICK,
            object_id=banner.id,
        ).exists()

    def test_a_banner_with_nowhere_to_go_draws_no_button(
        self, tester, client, default_pack, live_banner
    ):
        """Do not create a tracker link for an empty destination, whose tracker fallback
        would lead to the site home.
        """
        live_banner(cta_text="Read the notes", cta_url="")

        body = client.get("/n26/").content.decode()
        bar = announcement_bar(body)
        assert "Read the notes" not in bar
        assert "n26-announcement-cta" not in bar

    def test_an_impersonation_notice_keeps_its_stop_form(
        self, client, tester, default_pack
    ):
        """Preserve the native stop form and account-name markup inside the impersonation
        notice.
        """
        from django.contrib.auth.models import User
        from django.urls import reverse

        admin = User.objects.create_superuser("overseer", "overseer@example.com")
        client.force_login(admin)
        started = client.post(
            reverse("core:impersonate-start", args=[tester.pk]),
            {"next": "/n26/"},
        )
        assert started.status_code == 302

        body = client.get("/n26/").content.decode()
        # The announcement extractor starts after the aside ID, so check that ID
        # separately.
        assert 'id="impersonation-banner"' in body
        bar = announcement_bar(body)
        assert f"<strong>{tester.username}</strong>" in bar
        assert "<form" in bar
        assert reverse("core:impersonate-stop") in bar
        assert "Stop impersonating" in bar
        assert "data-react-module" not in bar


class TestTheSharedIconKeys:
    """Validate platform-declared N26 icon strings without importing edition code into the
    platform registry.
    """

    def test_every_key_names_an_icon_this_edition_actually_has(self):
        from gyrinx.site import icons as banner_icons
        from n26.core import icons

        missing = {
            entry.key: entry.n26
            for entry in banner_icons.BANNER_ICONS
            if entry.n26 not in icons.names()
        }
        assert not missing

    def test_the_lookup_is_total(self):
        from gyrinx.site import icons as banner_icons

        assert banner_icons.n26_name("nonsense") == ""
        assert banner_icons.n26_name("") == ""
        assert banner_icons.n26_name(None) == ""


class TestFoundingAGang:
    def test_the_form_page_renders_from_the_design_system(
        self, tester, client, default_pack, gang_type
    ):
        body = client.get("/n26/gangs/new/").content.decode()
        assert "Create a gang" in body
        assert "Leave blank to spend as much as you like." in body
        assert str(gang_type) in body

    def test_the_shell_carries_the_platform_brand_and_measure(
        self, tester, client, default_pack
    ):
        """Use the shared logo and explicit container width matching the platform layout."""
        body = client.get("/n26/").content.decode()
        assert "platform/img/brand/logo-gold-transparent-bg.svg" in body
        assert "--n26-site-width: 1320px" in body

    def test_a_valid_submit_founds_a_real_gang(
        self, tester, client, default_pack, gang_type
    ):
        from n26.core.models import Gang

        response = client.post(
            "/n26/gangs/new/",
            {
                "name": "The Bad Girls",
                "gang_type": str(gang_type.pk),
                "starting_credits": "1000",
                "colour": "red",
            },
        )
        assert response.status_code == 302

        gang = Gang.objects.get(name="The Bad Girls")

        assert response["Location"] == f"/n26/gangs/{gang.pk}/"
        assert gang.owner == tester
        assert gang.gang_type == gang_type
        assert gang.starting_credits == 1000
        assert gang.credits == 1000
        assert gang.colour == "red"
        # Verify the gang-hosted founding assignment.
        assert gang.founding is not None
        assert gang.founding.assignable == gang_type

        body = client.get("/n26/").content.decode()
        assert "The Bad Girls" in body

    def test_blank_credits_mean_no_limit(self, tester, client, default_pack, gang_type):
        from n26.core.models import Gang

        client.post(
            "/n26/gangs/new/",
            {"name": "Unbudgeted", "gang_type": str(gang_type.pk)},
        )
        gang = Gang.objects.get(name="Unbudgeted")
        assert gang.starting_credits is None
        assert gang.credits == 0

    def test_a_missing_name_redisplays_with_the_error(
        self, tester, client, default_pack, gang_type
    ):
        from n26.core.models import Gang

        response = client.post(
            "/n26/gangs/new/", {"name": "", "gang_type": str(gang_type.pk)}
        )
        assert response.status_code == 200
        assert "required" in response.content.decode()
        assert Gang.objects.count() == 0


class TestTheFoundationsBackfill:
    def test_the_command_seeds_everything_idempotently(self, default_pack):
        from django.core.management import call_command

        from n26.library.models import GangType, Skill
        from n26.library.standard_content import STANDARD_CONTENT

        call_command("n26_backfill_foundations")
        assert all(item.status() == "complete" for item in STANDARD_CONTENT.values())
        assert GangType.objects.count() == 17

        call_command("n26_backfill_foundations")
        assert GangType.objects.count() == 17
        assert Skill.objects.filter(name="Catfall").count() == 1
