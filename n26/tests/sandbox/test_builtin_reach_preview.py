"""An author sees how far a built-in change travels before committing.

The reach of an addition — how many live uses of the set exist, in how
many gangs — is counted by the same carrier resolution the propagation
pass walks, so the number the author reads is the number of uses a pass
then visits. The pages that add a member say it in a sentence whose
promise follows the feature flag: reach within seconds while passes
run, a plain "when it is switched on" while they stand down, and its
own quiet sentence when nothing holds the set at all. The preview is
informative only — the pass recomputes when it runs.
"""

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from gyrinx.site.models import Availability, FeatureFlag
from n26.core.models import BuiltInPropagationTask
from n26.core.operations import operation
from n26.core.propagation import Reach, reach_of, reach_of_new_built_ins
from n26.flags import BUILT_IN_PROPAGATION
from n26.tests.sandbox.actions import (
    add_built_in,
    assign,
    create_profile,
    create_rule,
    found_gang,
    hire,
    hire_with_option,
    offer_option,
    remove,
)
from n26.tests.sandbox.test_ingest_page import PREVIEW_URL, hold, hold_all

pytestmark = pytest.mark.django_db


@pytest.fixture
def flag(db):
    """Passes run only while the flag is open; the wording tests that
    want the within-seconds promise request this row."""
    return FeatureFlag.objects.create(
        slug=BUILT_IN_PROPAGATION,
        name="Built-in propagation",
        availability=Availability.EVERYONE,
    )


@pytest.fixture
def player():
    return User.objects.create_user("tom")


@pytest.fixture
def author(client):
    user = User.objects.create_user("author", is_staff=True)
    client.force_login(user)
    return user


@pytest.fixture
def ganger(person_type, gang_type, default_pack):
    profile = create_profile("Ganger", person_type, gang_type, price=50)
    add_built_in(profile, create_rule("Gang Fighter"))
    return profile


@pytest.fixture
def foundation(default_pack):
    """The seed rows the sheets resolve against, planted the way the
    Foundations page plants them."""
    from n26.library.standard_content import STANDARD_CONTENT

    for item in STANDARD_CONTENT.values():
        item.create()


def comes_with_section(page):
    return next(
        section
        for section in page.context["part_sections"]
        if section["act"] == "built_in"
    )


class TestTheReachPlanner:
    """The counts are the carriers a pass visits: holders' live uses
    and option selectors, outside archived gangs, nothing else."""

    def test_the_counts_agree_with_what_a_pass_then_touches(
        self, ganger, gang_type, player, default_pack, task_queue, flag
    ):
        here = found_gang("The Bad Girls", gang_type, owner=player, budget=1000)
        there = found_gang("The Movers", gang_type, owner=player, budget=1000)
        hire(here, ganger, "Ana", paid=50)
        hire(here, ganger, "Bea", paid=50)
        hire(there, ganger, "Cat", paid=50)

        reach = reach_of(ganger.built_ins)
        assert reach == Reach(uses=3, gangs=2)

        with task_queue.capture():
            member = add_built_in(ganger, create_rule("Nerves of Steel"))
        task_queue.deliver_all()

        filed = (
            BuiltInPropagationTask.objects.filter(
                status="DONE", default_set=member.default_set
            )
            .order_by("created")
            .last()
        )
        ending = filed.states.history.get(to_status="DONE")
        assert ending.metadata["gangs"] == reach.gangs
        assert ending.metadata["granted"] == reach.uses

    def test_an_option_set_counts_only_the_gangs_that_chose_it(
        self, gang_type, person_type, player, default_pack
    ):
        profile = create_profile("Chooser", person_type, gang_type, price=100)
        offer_option(profile, "Plain", thing=create_rule("Plain Style"))
        fancy = offer_option(profile, "Fancy", thing=create_rule("Fancy Style"))
        gang = found_gang("The Bad Girls", gang_type, owner=player, budget=1000)
        hire_with_option(gang, profile, "Ana", option=fancy.default_set)
        hire(gang, profile, "Bea", paid=100)

        assert reach_of(fancy.default_set) == Reach(uses=1, gangs=1)

    def test_archived_gangs_and_parted_with_uses_are_outside_the_reach(
        self, ganger, gang_type, player, default_pack
    ):
        here = found_gang("The Bad Girls", gang_type, owner=player, budget=1000)
        there = found_gang("The Leavers", gang_type, owner=player, budget=1000)
        hire(here, ganger, "Ana", paid=50)
        bea = hire(here, ganger, "Bea", paid=50)
        hire(there, ganger, "Cat", paid=50)

        remove(bea.membership)
        there.archived = True
        there.save()

        assert reach_of(ganger.built_ins) == Reach(uses=1, gangs=1)

    def test_an_owners_removal_of_the_thing_is_not_a_use(
        self, ganger, gang_type, player, default_pack
    ):
        """A removes assignment is the owner striking the thing off, so
        nothing rides it — a pass skips it and the count does too."""
        cursed = create_rule("Cursed")
        add_built_in(cursed, create_rule("Curse Mark"))
        gang = found_gang("The Bad Girls", gang_type, owner=player, budget=1000)
        ana = hire(gang, ganger, "Ana", paid=50)
        bea = hire(gang, ganger, "Bea", paid=50)
        assign(cursed, miniature=ana)
        with operation(gang, actor=gang.owner) as op:
            op.take_away(bea, cursed)

        assert reach_of(cursed.built_ins) == Reach(uses=1, gangs=1)

    def test_a_set_nobody_holds_reports_zero(self, ganger, default_pack):
        assert reach_of(ganger.built_ins) == Reach(uses=0, gangs=0)

    def test_a_thing_with_no_set_yet_counts_its_own_uses(
        self, person_type, gang_type, player, default_pack
    ):
        """The first built-in founds the set on the thing, so before it
        exists the reach is the thing's own live uses."""
        bare = create_profile("Plain Hand", person_type, gang_type, price=50)
        gang = found_gang("The Bad Girls", gang_type, owner=player, budget=1000)
        hire(gang, bare, "Ana", paid=50)

        assert bare.built_ins_id is None
        assert reach_of_new_built_ins(bare) == Reach(uses=1, gangs=1)

    def test_the_query_count_stays_flat_as_the_holders_grow(
        self, ganger, gang_type, player, default_pack
    ):
        gang = found_gang("The Bad Girls", gang_type, owner=player, budget=1000)
        hire(gang, ganger, "Ana", paid=50)
        with CaptureQueriesContext(connection) as small:
            reach_of(ganger.built_ins)

        for name in ("The Movers", "The Stayers", "The Walkers"):
            grown = found_gang(name, gang_type, owner=player, budget=1000)
            hire(grown, ganger, f"{name} One", paid=50)
            hire(grown, ganger, f"{name} Two", paid=50)
        with CaptureQueriesContext(connection) as large:
            assert reach_of(ganger.built_ins) == Reach(uses=7, gangs=4)

        assert len(large) == len(small)


class TestTheAuthoringPagesSayIt:
    """Each page that adds a member carries the sentence, rendered
    server-side, its promise following the feature flag."""

    def test_the_comes_with_form_says_the_reach(
        self, client, author, ganger, gang_type, player, default_pack, flag
    ):
        gang = found_gang("The Bad Girls", gang_type, owner=player, budget=1000)
        hire(gang, ganger, "Ana", paid=50)

        page = client.get(reverse("authoring-detail", args=["profile", ganger.pk]))

        said = comes_with_section(page)["reach_said"]
        assert said == (
            "Already held once, in one gang — a built-in added here "
            "reaches it within seconds."
        )
        assert said in page.content.decode()

    def test_several_uses_are_counted_in_the_plural(
        self, client, author, ganger, gang_type, player, default_pack, flag
    ):
        here = found_gang("The Bad Girls", gang_type, owner=player, budget=1000)
        there = found_gang("The Movers", gang_type, owner=player, budget=1000)
        hire(here, ganger, "Ana", paid=50)
        hire(here, ganger, "Bea", paid=50)
        hire(there, ganger, "Cat", paid=50)

        page = client.get(reverse("authoring-detail", args=["profile", ganger.pk]))

        assert comes_with_section(page)["reach_said"] == (
            "Already held 3 times, across 2 gangs — a built-in added here "
            "reaches every one of them within seconds."
        )

    def test_shut_the_sentence_promises_nothing_until_the_flag_opens(
        self, client, author, ganger, gang_type, player, default_pack
    ):
        gang = found_gang("The Bad Girls", gang_type, owner=player, budget=1000)
        hire(gang, ganger, "Ana", paid=50)

        page = client.get(reverse("authoring-detail", args=["profile", ganger.pk]))

        assert comes_with_section(page)["reach_said"] == (
            "Already held once, in one gang — a built-in added here will "
            "reach it when built-in propagation is switched on."
        )

    def test_no_holders_reads_as_its_own_sentence(
        self, client, author, ganger, default_pack, flag
    ):
        page = client.get(reverse("authoring-detail", args=["profile", ganger.pk]))

        said = comes_with_section(page)["reach_said"]
        assert said == (
            "Held by no gang yet, so a built-in added here changes only "
            "what is acquired from now on."
        )
        assert said in page.content.decode()

    def test_a_thing_without_a_set_counts_its_uses_all_the_same(
        self, client, author, person_type, gang_type, player, default_pack, flag
    ):
        bare = create_profile("Plain Hand", person_type, gang_type, price=50)
        gang = found_gang("The Bad Girls", gang_type, owner=player, budget=1000)
        hire(gang, bare, "Ana", paid=50)

        page = client.get(reverse("authoring-detail", args=["profile", bare.pk]))

        assert (
            "Already held once, in one gang" in (comes_with_section(page)["reach_said"])
        )

    def test_the_gun_members_page_says_the_reach(
        self, client, author, person_type, gang_type, player, default_pack, flag
    ):
        from n26.library.authoring import create_weapon

        launcher = create_weapon("Launcher", profiles=[("Frag", 0), ("Smoke", 10)])
        gunner = create_profile("Gunner", person_type, gang_type, price=50)
        add_built_in(gunner, launcher)
        gang = found_gang("The Bad Girls", gang_type, owner=player, budget=1000)
        hire(gang, gunner, "Ana", paid=50)
        gun_member = gunner.built_ins.members.get(weapon__isnull=False)

        page = client.get(reverse("authoring-built-in-profiles", args=[gun_member.pk]))

        said = page.context["reach_said"]
        assert said == (
            "Already held once, in one gang — a line added here reaches "
            "it within seconds."
        )
        assert said in page.content.decode()

    def test_the_set_door_page_says_the_reach(
        self, client, author, ganger, gang_type, player, default_pack, flag
    ):
        gang = found_gang("The Bad Girls", gang_type, owner=player, budget=1000)
        hire(gang, ganger, "Ana", paid=50)

        page = client.get(reverse("authoring-set-profiles", args=[ganger.built_ins_id]))

        said = page.context["reach_said"]
        assert "Already held once, in one gang" in said
        assert said in page.content.decode()

    def test_the_option_page_counts_choosers_only(
        self, client, author, person_type, gang_type, player, default_pack, flag
    ):
        profile = create_profile("Chooser", person_type, gang_type, price=100)
        offer_option(profile, "Plain", thing=create_rule("Plain Style"))
        fancy = offer_option(profile, "Fancy", thing=create_rule("Fancy Style"))
        gang = found_gang("The Bad Girls", gang_type, owner=player, budget=1000)
        hire_with_option(gang, profile, "Ana", option=fancy.default_set)
        hire(gang, profile, "Bea", paid=100)
        option = profile.options.get(name="Fancy")

        page = client.get(reverse("authoring-option-add", args=[option.pk]))

        said = page.context["reach_said"]
        assert said == (
            "Already held once, in one gang — anything added here reaches "
            "it within seconds."
        )
        assert said in page.content.decode()


#: The profiles sheet with one line grown: Way-Brethren gains the
#: Witch special rule the pack already holds, so a re-upload plans one
#: set update whose only difference is the added member.
def grown_profiles_csv():
    from n26.tests.sandbox.test_ingest import PROFILES_CSV

    return PROFILES_CSV.replace(
        'Specialist",13,45,,,,Cawdor', 'Specialist",13,45,Witch,,,Cawdor'
    )


class TestTheIngestPreviewSaysIt:
    """The upload preview carries the same sentence for the sets the
    sheets would add members to — counted by the same planner, said in
    the same words."""

    def test_the_reach_line_reflects_the_standing_uses(
        self, client, author, foundation, player, default_pack
    ):
        from n26.library.models import Profile

        hold_all(client)
        client.post(PREVIEW_URL)
        brethren = Profile.objects.get(name="Way-Brethren")
        gang = found_gang(
            "The Bad Girls", brethren.gang_type, owner=player, budget=1000
        )
        hire(gang, brethren, "Ana", paid=45)

        hold(client, "profiles", text=grown_profiles_csv())
        page = client.get(PREVIEW_URL)

        said = page.context["preview"]["reach_said"]
        assert said == (
            "Some of these additions grow what a thing comes with: already "
            "held once, in one gang — each addition will reach it when "
            "built-in propagation is switched on."
        )
        assert said in page.content.decode()

    def test_open_the_line_promises_the_reach_within_seconds(
        self, client, author, foundation, player, default_pack, flag
    ):
        from n26.library.models import Profile

        hold_all(client)
        client.post(PREVIEW_URL)
        brethren = Profile.objects.get(name="Way-Brethren")
        gang = found_gang(
            "The Bad Girls", brethren.gang_type, owner=player, budget=1000
        )
        hire(gang, brethren, "Ana", paid=45)

        hold(client, "profiles", text=grown_profiles_csv())
        page = client.get(PREVIEW_URL)

        assert page.context["preview"]["reach_said"].endswith(
            "each addition reaches it within seconds."
        )

    def test_an_upload_growing_no_standing_set_says_nothing(
        self, client, author, foundation, default_pack
    ):
        hold_all(client)
        client.post(PREVIEW_URL)

        page = client.get(PREVIEW_URL)

        assert page.context["preview"]["reach_said"] == ""


class TestRemovalSaysWhatKeepsIt:
    """Taking a built-in off a set does not take it off anything that
    already has it, and the page says so with the count — an author who
    has watched an addition travel would otherwise expect the reverse."""

    def test_the_page_counts_the_copies_that_keep_it(
        self, client, author, player, gang_type, ganger
    ):
        gang = found_gang("The Old Guard", gang_type, owner=player, budget=1000)
        hire(gang, ganger, "Ana", paid=50)
        hire(gang, ganger, "Bea", paid=50)
        member = ganger.built_ins.members.get(rule__isnull=False)

        response = client.get(reverse("authoring-built-in-remove", args=[member.pk]))

        page = response.content.decode()
        assert "2 standing copies" in page
        assert "in one gang" in page
        assert "does not take it off anything that already has it" in page

    def test_a_member_nothing_holds_says_nothing_about_keeping(
        self, client, author, ganger
    ):
        member = ganger.built_ins.members.get(rule__isnull=False)

        response = client.get(reverse("authoring-built-in-remove", args=[member.pk]))

        assert "standing cop" not in response.content.decode()
