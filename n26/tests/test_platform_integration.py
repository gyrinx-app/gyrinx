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
* the shell's one menu holds whatever links the area put in the bar,
  plus the account items — and the staff-only ones only for staff.

Tests run --nomigrations, so the "N26 Testers" group the accounts data
migration creates does not exist here — each test that needs it makes
it, which also proves the gate reads the group by name rather than
assuming the migration ran.
"""

import pytest
from django.contrib.auth.models import Group, User

from gyrinx.middleware import N26_TESTERS_GROUP

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

    def test_the_changelog_lists_platform_entries(self, tester, client, default_pack):
        from gyrinx.site.models import ChangelogEntry

        ChangelogEntry.objects.create(
            date="2026-08-07",
            title="The Trading Post opened",
            body="<p>Everything with a <strong>TP price</strong> is there.</p>",
        )
        body = client.get("/n26/").content.decode()
        assert "The Trading Post opened" in body
        assert "7 Aug" in body
        assert "<strong>TP price</strong>" in body  # rich text survives the sanitiser

    def test_the_changelog_body_is_sanitised(self, tester, client, default_pack):
        from gyrinx.site.models import ChangelogEntry

        ChangelogEntry.objects.create(
            date="2026-08-07",
            title="A careless entry",
            body='<script>alert("no")</script><p>fine</p>',
        )
        body = client.get("/n26/").content.decode()
        # The page has its own legitimate scripts; what must be gone is
        # the entry's payload — dropped with its content, not escaped.
        assert "alert" not in body
        assert "fine" in body


def nav_menu(body):
    """The panel behind the shell's one menu button.

    The header renders its links twice — flat in the bar and stacked in
    the menu — so a bare substring search cannot tell which copy it
    found. The menu is the header's one role="menu" region, and the
    account items live only in it.
    """
    header = body[: body.index("</header>")]
    return header[header.index('role="menu"') :]


def in_order(text, *fragments):
    """Where each fragment first appears, for asserting a running order."""
    return [text.index(fragment) for fragment in fragments]


class TestTheNavigation:
    """Two places in the bar and the account items under them.

    The bar is for where a reader can go — the dashboard and their
    gangs. Everything about the account, including the staff-only doors,
    is in the menu below those links, and the menu is the same list the
    bar drew, so the two can never name different pages.
    """

    @pytest.fixture
    def staff(self, client):
        user = User.objects.create_user("boss", is_staff=True)
        client.force_login(user)
        return user

    def test_the_bar_is_home_and_gangs(self, tester, client, default_pack):
        body = client.get("/n26/").content.decode()
        home, gangs = in_order(body, ">Home</a>", ">Gangs</a>")
        assert home < gangs
        # Founding is an action with a button on both pages, not a place.
        assert ">Create a gang</a>" not in body

    def test_the_menu_holds_the_links_and_then_the_account(
        self, tester, client, default_pack
    ):
        menu = nav_menu(client.get("/n26/").content.decode())
        positions = in_order(
            menu, ">Home</a>", ">Gangs</a>", "Your account", "Sign out"
        )
        assert positions == sorted(positions)

    def test_staff_get_the_two_extra_doors(self, staff, client, default_pack):
        menu = nav_menu(client.get("/n26/").content.decode())
        positions = in_order(menu, "Your account", "Admin", "Authoring", "Sign out")
        assert positions == sorted(positions)

    def test_nobody_else_is_shown_a_door_they_cannot_open(
        self, tester, client, default_pack
    ):
        """A tester who is not staff is refused by both pages anyway, so
        an item they can only bounce off is noise."""
        menu = nav_menu(client.get("/n26/").content.decode())
        assert "Admin" not in menu
        assert "Authoring" not in menu

    def test_the_authoring_area_puts_its_own_pages_in_the_menu(
        self, staff, client, default_pack
    ):
        """The menu draws whatever the area gave the bar, so an author
        gets the authoring pages there and not the app's."""
        menu = nav_menu(client.get("/n26/authoring/").content.decode())
        positions = in_order(
            menu,
            ">Authoring</a>",
            ">Modifiers</a>",
            ">Foundations</a>",
            ">Ingest</a>",
            ">App</a>",
        )
        assert positions == sorted(positions)
        assert ">Home</a>" not in menu
        assert ">Gangs</a>" not in menu


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
