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
  assignment, and the type's built-ins, owned by the signed-in user.

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
