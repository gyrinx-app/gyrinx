"""The n26 edition inside the platform: the gate, the dashboard, the
founding form, the changelog, and the foundations backfill.

The load-bearing ideas:

* the whole /n26/ prefix is testers-only while the edition is in
  preview — one middleware fence, so a new page cannot ship open by
  forgetting a decorator (staff pass; members of "N26 Testers" pass;
  anonymous visitors sign in; everyone else gets a 404, because the
  beta is invisible rather than locked);
* the dashboard and the create form are the design system's views bound
  to real data — the user's own gangs, the platform's changelog;
* a valid create submit founds a real gang: the row, its founding
  assignment, and the type's built-ins, owned by the signed-in user;
* the shell's drawer holds whatever links the area gave it and the
  reader's own gangs, while the account menu behind their name holds
  the doors — and the staff-only ones only for staff.

Tests run --nomigrations, so the "N26 Testers" group the accounts data
migration creates does not exist here — each test that needs it makes
it, which also proves the gate reads the group by name rather than
assuming the migration ran.
"""

import pytest
from django.contrib.auth.models import Group, User

from gyrinx.middleware import N26_TESTERS_GROUP
from n26.core.views.gangs import CHANGELOG_TAG

pytestmark = pytest.mark.django_db


@pytest.fixture
def tester(client):
    user = User.objects.create_user("tester")
    group, _ = Group.objects.get_or_create(name=N26_TESTERS_GROUP)
    user.groups.add(group)
    client.force_login(user)
    return user


class TestTheGate:
    def test_anonymous_is_sent_to_sign_in_and_back(self, client, default_pack):
        response = client.get("/n26/")
        assert response.status_code == 302
        assert "login" in response["Location"]
        assert "next=/n26/" in response["Location"]

    def test_a_signed_in_stranger_sees_nothing(self, client, default_pack):
        """Not a 403: the beta is invisible, so there is nothing to ask
        for access to by URL-guessing."""
        client.force_login(User.objects.create_user("stranger"))
        assert client.get("/n26/").status_code == 404
        assert client.get("/n26/design/").status_code == 404

    def test_a_tester_is_let_in(self, tester, client, default_pack):
        assert client.get("/n26/").status_code == 200
        assert client.get("/n26/design/").status_code == 200

    def test_staff_pass_without_the_group(self, client, default_pack):
        client.force_login(User.objects.create_user("boss", is_staff=True))
        assert client.get("/n26/").status_code == 200

    def test_authoring_still_wants_staff_inside_the_gate(
        self, tester, client, default_pack
    ):
        """The fence is the outer check, not the only one: a tester who
        is not staff browses the app but never the authoring surface."""
        response = client.get("/n26/authoring/")
        assert response.status_code == 302
        assert "login" in response["Location"]


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
    """One entry in the site's changelog, wearing the tags named.

    Tags are made on demand: the rows are a lookup table an admin adds
    to, so a test asks for a name rather than for a row that exists.
    """
    from gyrinx.site.models import ChangelogEntry, ChangelogEntryTag

    entry = ChangelogEntry.objects.create(
        date=date, title=title, body=body, owner=owner
    )
    for name in tags:
        tag, _ = ChangelogEntryTag.objects.get_or_create(name=name)
        entry.tags.add(tag)
    return entry


class TestTheChangelogPanel:
    """The changelog belongs to the site, and both editions' dashboards
    read the same table — so this panel shows only what is tagged for
    this edition.

    An entry nobody tagged appears on neither dashboard. That is the
    point of the tag: a reader here should not have to work out for
    themselves which edition a change was about.
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
        assert "<strong>TP price</strong>" in body  # rich text survives the sanitiser

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
        """Tag names are unique, but case-sensitively so — an admin can
        make "n26" beside "N26" and would reasonably expect the entry to
        show up here either way."""
        changelog_entry("Written in lower case", CHANGELOG_TAG.lower())
        assert "Written in lower case" in client.get("/n26/").content.decode()

    def test_an_entry_wearing_two_spellings_is_still_one_entry(
        self, tester, client, default_pack
    ):
        """Matching either spelling means an entry carrying both matches
        the tag join twice; listed twice it would also eat two of the
        five places the panel has."""
        changelog_entry("Tagged twice over", CHANGELOG_TAG, CHANGELOG_TAG.lower())
        body = client.get("/n26/").content.decode()
        assert body.count("Tagged twice over") == 1

    def test_it_says_there_is_nothing_rather_than_showing_a_bare_heading(
        self, tester, client, default_pack
    ):
        """A heading with nothing under it reads as a section that
        failed to load."""
        changelog_entry("Not for this edition", "N23")
        body = client.get("/n26/").content.decode()
        assert "What&#x27;s new" in body
        assert "Nothing new yet." in body

    def test_the_body_is_sanitised(self, tester, client, default_pack):
        changelog_entry(
            "A careless entry",
            CHANGELOG_TAG,
            body='<script>alert("no")</script><p>fine</p>',
        )
        body = client.get("/n26/").content.decode()
        # The page has its own legitimate scripts; what must be gone is
        # the entry's payload — dropped with its content, not escaped.
        assert "alert" not in body
        assert "fine" in body

    def test_the_panel_costs_the_same_queries_however_many_entries_exist(
        self, tester, client, default_pack
    ):
        """The panel is one query for the page, not one per entry. The
        tag filter is a join rather than a lookup per row, and nothing
        drawn from an entry reaches past its own columns.

        The entries are owned, as an entry written in the admin is: an
        ownerless row follows no owner FK however carelessly a template
        asks for one, so a test built from ownerless rows could not see
        the commonest way this goes wrong.
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        # The first request of a session writes the session row and the
        # rest update it, so measure only once that has happened.
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


TELEPORT = '<template x-teleport="body">'


def nav_drawer(body):
    """The panel behind the burger.

    Alpine builds it out of a <template>, which is one inert block in
    the response — and the only place the reader's gangs appear, so it
    also tells the drawer's copy of the links apart from the flat copy
    drawn for a reader with no script.
    """
    header = body[body.index("<header") : body.index("</header>")]
    start = header.index(TELEPORT)
    return header[start : header.index("</template>", start)]


def nav_bar(body):
    """The row across the top, with the drawer's panel and the no-script
    strip cut out — both repeat the links, so a bare substring search
    could not tell which copy it had found."""
    header = body[body.index("<header") : body.index("</header>")]
    start = header.index(TELEPORT)
    end = header.index("</template>", start) + len("</template>")
    bar = header[:start] + header[end:]
    return bar[: bar.index("<noscript>")]


def nav_noscript(body):
    """The flat list of links under the bar, drawn for a reader whose
    browser ran no script and so has no drawer to open."""
    header = body[body.index("<header") : body.index("</header>")]
    return header[header.index("<noscript>") : header.index("</noscript>")]


def account_menu(body):
    """The panel behind the reader's own name. The header's one
    role="menu" region, and the account items live only in it."""
    bar = nav_bar(body)
    return bar[bar.index('role="menu"') :]


def in_order(text, *fragments):
    """Where each fragment first appears, for asserting a running order."""
    return [text.index(fragment) for fragment in fragments]


class TestTheNavigation:
    """A bar that names the page, a drawer that holds the places, an
    account menu that holds the doors.

    The bar reads left to right as one sentence — burger, brand, the
    page's own name — with the controls at the far end. Everywhere a
    reader can go is behind the burger: the area's pages, and their own
    gangs under them. Everything about the account, including the
    staff-only doors, is behind their name.
    """

    @pytest.fixture
    def staff(self, client):
        user = User.objects.create_user("boss", is_staff=True)
        client.force_login(user)
        return user

    def test_the_bar_reads_burger_brand_then_page(self, tester, client, default_pack):
        bar = nav_bar(client.get("/n26/").content.decode())
        positions = in_order(
            bar,
            'aria-label="Open navigation menu"',
            "n26-site-brand",
            "·",
            "Home",
        )
        assert positions == sorted(positions)

    def test_the_controls_sit_at_the_far_end(self, tester, client, default_pack):
        """Past the page's name, so nothing the page says can push them
        around and a reader finds them in the same place every time."""
        bar = nav_bar(client.get("/n26/").content.decode())
        positions = in_order(
            bar,
            "n26-site-brand",
            'aria-label="Open account menu"',
        )
        assert positions == sorted(positions)

    def test_the_colour_scheme_is_behind_the_account_menu(
        self, tester, client, default_pack
    ):
        """A scheme is chosen once and then never again, and a control in
        the bar holds a row of space the page's own name wants on every
        screen. Behind the name it is still one press away."""
        body = client.get("/n26/").content.decode()
        assert "set('system')" in account_menu(body)
        assert 'aria-label="Toggle dark mode"' not in nav_bar(body)

    def test_the_scheme_is_one_control_of_three_and_not_three_rows(
        self, tester, client, default_pack
    ):
        """Three menu rows would stand level with the places the menu
        leads to, and make the panel half as tall again on the screen
        with the least height to give. One segmented control says the
        same thing in a third of the space — and it is a choice of one
        from three, so each part announces itself as a radio in a group
        rather than as another door out of the menu."""
        menu = account_menu(client.get("/n26/").content.decode())
        assert menu.count('role="menuitemradio"') == 3
        assert 'role="group"' in menu
        assert 'aria-label="Theme"' in menu
        # Each state still sets it: a control that renders and no longer
        # switches looks right in every screenshot and works for nobody.
        for scheme in ("light", "dark", "system"):
            assert f"set('{scheme}')" in menu

    def test_each_scheme_carries_its_own_drawing(self, tester, client, default_pack):
        """The sun, the moon and a screen. One icon for the group could
        only picture whichever scheme is current, and which one is
        current is what the control is there to show."""
        from n26.core import icons

        menu = account_menu(client.get("/n26/").content.decode())
        for name in ("sun", "moon", "computer-desktop"):
            assert icons.paths(name)[0] in menu

    def test_the_drawer_holds_the_places_the_app_has(
        self, tester, client, default_pack
    ):
        drawer = nav_drawer(client.get("/n26/").content.decode())
        positions = in_order(
            drawer, ">Home</a>", ">Gangs</a>", "Campaigns", "Content Packs"
        )
        assert positions == sorted(positions)
        # Founding is an action with a button on both pages, not a place.
        assert ">Create a gang</a>" not in drawer

    def test_a_place_with_no_page_yet_is_not_a_link(self, tester, client, default_pack):
        """Campaigns and Content Packs are coming and are worth naming,
        but a link that lands nowhere teaches a reader to distrust the
        rest of the list."""
        drawer = nav_drawer(client.get("/n26/").content.decode())
        assert ">Campaigns</a>" not in drawer
        assert ">Content Packs</a>" not in drawer
        assert "Campaigns <span" in drawer

    def test_the_drawer_lists_the_readers_own_gangs(
        self, tester, client, default_pack, gang_type, make_profile
    ):
        """Under the places, because a gang is what someone opens the
        drawer for. With the type, which is how a player tells two of
        their own apart."""
        from n26.tests.sandbox.actions import found_gang

        gang = found_gang("The Bad Girls", gang_type, owner=tester)

        drawer = nav_drawer(client.get("/n26/").content.decode())
        positions = in_order(
            drawer,
            ">Gangs</a>",
            "Your gangs",
            "The Bad Girls",
            str(gang_type),
        )
        assert positions == sorted(positions)
        assert f"/n26/gangs/{gang.pk}/" in drawer

    def test_a_gangs_colour_is_a_mark_beside_its_name(
        self, tester, client, default_pack, gang_type, make_profile
    ):
        """The colour reaches the markup as the palette's variable in a
        style attribute. A class built from the colour's name is a string
        Tailwind never sees and never emits, so it would have styled
        nothing at all."""
        from n26.tests.sandbox.actions import found_gang

        gang = found_gang("The Bad Girls", gang_type, owner=tester)
        gang.colour = "violet"
        gang.save()

        drawer = nav_drawer(client.get("/n26/").content.decode())
        assert "background: var(--color-violet-500)" in drawer

    def test_a_gang_with_no_colour_gets_no_mark(
        self, tester, client, default_pack, gang_type, make_profile
    ):
        """Nothing is drawn and no space is held: most gangs have no
        colour, and a placeholder on every row is a gutter with nothing
        in it."""
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
        """The section is drawn only when something is in it: an empty
        "Your gangs" reads as a list that failed to load."""
        drawer = nav_drawer(client.get("/n26/").content.decode())
        assert "Your gangs" not in drawer

    def test_a_visitor_has_no_gangs_to_list(self, rf, default_pack):
        """Signed out there is nothing to put in the section, so the
        drawer draws neither the heading nor the rule above it. The
        gate turns an anonymous visitor away before any n26 page
        renders, so the claim is made where it is decided."""
        from django.contrib.auth.models import AnonymousUser

        from n26.core.templatetags.navigation import drawer_gangs

        request = rf.get("/n26/")
        request.user = AnonymousUser()
        assert drawer_gangs({"request": request}) == []

    def test_the_links_are_there_for_a_reader_with_no_script(
        self, tester, client, default_pack
    ):
        """The drawer is Alpine's and lives in a <template> that never
        runs without script, so the same links are drawn flat under the
        bar as well."""
        strip = nav_noscript(client.get("/n26/").content.decode())
        positions = in_order(strip, ">Home</a>", ">Gangs</a>")
        assert positions == sorted(positions)

    def test_the_account_menu_is_you_the_doors_and_the_way_out(
        self, staff, client, default_pack
    ):
        menu = account_menu(client.get("/n26/").content.decode())
        positions = in_order(
            menu, "Your account", "Staff only", "Admin", "Content Library", "Sign out"
        )
        assert positions == sorted(positions)
        # Only the way out draws a rule; the staff doors have a heading.
        assert menu.count('role="separator"') == 1

    def test_your_account_goes_to_the_page_that_is_actually_there(
        self, staff, client, default_pack
    ):
        """The account page is the site's, shared by both editions, and
        it is named rather than spelled out — a hand-written path can be
        wrong for as long as nobody clicks it."""
        from django.urls import reverse

        menu = account_menu(client.get("/n26/").content.decode())
        assert f'href="{reverse("core:account_home")}"' in menu
        assert client.get(reverse("core:account_home")).status_code == 200

    def test_the_staff_doors_say_they_are_staff_only(self, staff, client, default_pack):
        """A heading over them, so someone who has these doors knows at
        a glance which of their menu the person beside them does not
        have. The kit uppercases it, so the label is written as prose."""
        menu = account_menu(client.get("/n26/").content.decode())
        assert "Staff only" in menu
        positions = in_order(menu, "Staff only", "Admin")
        assert positions == sorted(positions)

    def test_nobody_else_is_shown_a_door_they_cannot_open(
        self, tester, client, default_pack
    ):
        """A tester who is not staff is refused by both pages anyway, so
        an item they can only bounce off is noise — and the heading over
        those two goes with them, rather than labelling nothing."""
        menu = account_menu(client.get("/n26/").content.decode())
        assert "Admin" not in menu
        assert "Content Library" not in menu
        assert "Staff only" not in menu
        assert menu.count('role="separator"') == 1

    def test_the_authoring_area_puts_its_own_pages_in_the_drawer(
        self, staff, client, default_pack
    ):
        """The drawer draws whatever the area gave it, so an author
        moving between the authoring pages gets those in the one
        control, with App at the end as the way back out."""
        drawer = nav_drawer(client.get("/n26/authoring/").content.decode())
        positions = in_order(
            drawer,
            ">Content library</a>",
            ">Modifiers</a>",
            ">Foundations</a>",
            ">Ingest</a>",
            ">App</a>",
        )
        assert positions == sorted(positions)
        assert ">Home</a>" not in drawer
        assert ">Gangs</a>" not in drawer

    def test_a_page_names_itself_in_the_bar_and_keeps_its_links(
        self, staff, client, default_pack
    ):
        """The name and the links no longer compete for the same space,
        so a page setting one keeps the other."""
        body = client.get("/n26/authoring/modifiers/").content.decode()
        assert "Modifiers" in nav_bar(body)
        assert ">Foundations</a>" in nav_drawer(body)


class TestTheSiteBanner:
    """The platform's banner, drawn in this edition's terms.

    Banner is platform-owned and shown by every edition, so it stores an
    icon *meaning* rather than a drawing, and each edition resolves that
    meaning in its own set. The colour is still Bootstrap's vocabulary,
    which n26 does not share, so the shell maps it onto the
    announcement's five tones.
    """

    @pytest.fixture
    def live_banner(self):
        from gyrinx.site.models import Banner

        def make(**kwargs):
            return Banner.objects.create(
                text="N26 support is coming.", is_live=True, **kwargs
            )

        return make

    def test_a_key_is_drawn_from_this_editions_own_set(
        self, tester, client, default_pack, live_banner
    ):
        """info's default icon is information-circle, so asking for
        success against an info bar proves the key was resolved rather
        than the tone's fallback being used."""
        from n26.core import icons

        live_banner(icon="success", colour="info")

        body = client.get("/n26/").content.decode()
        assert icons.ICONS["check-circle"][0] in body
        assert icons.ICONS["information-circle"][0] not in body

    def test_a_key_with_no_drawing_here_is_not_fatal(
        self, tester, client, default_pack, live_banner
    ):
        """The regression that started this. A live banner set to
        bi-blockquote-left took every page under /n26/ down with a
        KeyError out of the icon registry, which raises on a name it
        does not have — right for a name a template author wrote, fatal
        for one that arrived from a database column.

        The select box makes such a value unlikely rather than
        impossible: a row written before the choices existed, a key
        retired from the table, a banner restored from history. None of
        those is worth a 500, so the lookup stays total.
        """
        live_banner(icon="bi-blockquote-left", colour="primary")

        response = client.get("/n26/")
        assert response.status_code == 200
        assert "N26 support is coming." in response.content.decode()

    def test_an_unresolved_key_leaves_the_icon_the_tone_implies(
        self, tester, client, default_pack, live_banner
    ):
        """Not "no icon": the bar's colour and its icon say the same
        thing, and a coloured bar with nothing in it reads as a mistake.
        """
        from n26.core import icons

        live_banner(icon="nonsense", colour="danger")

        body = client.get("/n26/").content.decode()
        assert icons.ICONS["exclamation-triangle"][0] in body

    def test_a_bootstrap_colour_becomes_an_announcement_tone(
        self, tester, client, default_pack, live_banner
    ):
        """primary is not one of the five tones. Left untranslated it
        rendered data-tone="primary", which no rule matches, so the bar
        silently kept the default blue — right by luck, and wrong the
        moment the colour was secondary or dark."""
        live_banner(colour="primary")

        body = client.get("/n26/").content.decode()
        assert 'data-tone="info"' in body
        assert 'data-tone="primary"' not in body

    def test_a_colourless_banner_still_gets_a_tone(
        self, tester, client, default_pack, live_banner
    ):
        live_banner(colour="")

        body = client.get("/n26/").content.decode()
        assert 'data-tone="info"' in body


class TestTheSharedIconKeys:
    """gyrinx/site/icons.py names an n26 icon for every key, as a string,
    because the platform may not import an edition package. Nothing but
    this test keeps that column honest."""

    def test_every_key_names_an_icon_this_edition_actually_has(self):
        from gyrinx.site import icons as banner_icons
        from n26.core import icons

        missing = {
            entry.key: entry.n26
            for entry in banner_icons.BANNER_ICONS
            if entry.n26 not in icons.ICONS
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
        assert str(gang_type) in body  # the library's rows, not a fixture list

    def test_the_submit_button_is_the_editions_green(
        self, tester, client, default_pack, gang_type
    ):
        """The button that brings a thing into existence is `success` —
        a variant only the edition's cotton/ui/button.html knows. The
        package's own button shadowed it once (app order decides which
        template wins), and it failed by rendering the default colour
        with no error, which is what this pins."""
        body = client.get("/n26/gangs/new/").content.decode()
        assert "bg-green-700" in body

    def test_the_shell_carries_the_platform_brand_and_measure(
        self, tester, client, default_pack
    ):
        """The nav draws the platform's own logo from the platform's
        static tree, and the page states its width variable rather than
        leaning on the fallback — capped to match bootstrap's widest
        container so an n26 page reads as the same site."""
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
                "colour": "#b91c1c",
            },
        )
        assert response.status_code == 302
        assert response["Location"] == "/n26/"

        gang = Gang.objects.get(name="The Bad Girls")
        assert gang.owner == tester
        assert gang.gang_type == gang_type
        assert gang.starting_credits == 1000
        assert gang.credits == 1000
        assert gang.colour == "#b91c1c"
        # Founding is real: the gang-hosted assignment naming its type.
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

        call_command("n26_backfill_foundations")  # a second run changes nothing
        assert GangType.objects.count() == 17
        assert Skill.objects.filter(name="Catfall").count() == 1

    def test_the_testers_group_migration_is_reversible_data(self):
        """The group arrives by data migration; under --nomigrations it
        is absent, which is exactly what this asserts — anyone relying
        on it in tests must create it, as the gate tests do."""
        assert not Group.objects.filter(name=N26_TESTERS_GROUP).exists()
