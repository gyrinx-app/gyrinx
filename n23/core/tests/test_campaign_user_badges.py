"""Every username on a campaign screen carries the person's badge.

The badge beside a name is read off that person's profile and their badge
grants, so a page naming several people must fetch those for everybody at
once: these pin that the campaign screens draw the badge at every name, and
that naming more people costs no more queries.
"""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from gyrinx.accounts.models import PatreonStatus, UserProfile
from gyrinx.badges import badge_by_slug
from n23.core.models.campaign import CampaignAction

# The accessible name the badge tag puts on every mark it draws. Counted
# rather than the artwork, which a {% spaceless %} block reflows.
MARK = f'aria-label="{badge_by_slug("guilder").description}"'


def _badged(make_user, username):
    user = make_user(username, "password")
    UserProfile.objects.create(
        user=user,
        patreon_status=PatreonStatus.ACTIVE,
        patreon_tier="Guilder",
        selected_badge="guilder",
    )
    return user


@pytest.fixture
def owner(user):
    """The campaign owner, holding a badge — ``make_campaign`` owns by ``user``."""
    UserProfile.objects.create(
        user=user,
        patreon_status=PatreonStatus.ACTIVE,
        patreon_tier="Guilder",
        selected_badge="guilder",
    )
    return user


@pytest.fixture
def viewer(client, make_user):
    """Somebody with no badge, signed in, so the page chrome draws none and
    every mark on the page belongs to a name the campaign itself shows."""
    person = make_user("viewer", "password")
    client.force_login(person)
    return person


@pytest.fixture
def make_table(owner, make_campaign, make_list, make_user):
    """A public campaign with badged admins and badged gang owners, and one
    action logged by each gang owner."""

    def _make(name, *, admins=0, gangs=0):
        campaign = make_campaign(name, public=True)
        for index in range(admins):
            campaign.admins.add(_badged(make_user, f"{name}-admin-{index}"))
        for index in range(gangs):
            player = _badged(make_user, f"{name}-player-{index}")
            lst = make_list(f"{name} gang {index}", owner=player)
            campaign.lists.add(lst)
            CampaignAction.objects.create(
                campaign=campaign,
                user=player,
                list=lst,
                description=f"{player.username} did something",
            )
        return campaign

    return _make


def _marks(client, url):
    response = client.get(url)
    assert response.status_code == 200
    return response.content.decode().count(MARK)


def _queries(client, url):
    """How many queries a page costs, once the session has settled — the
    first request after signing in records the session, which is a cost of
    signing in and not of the page."""
    client.get(url)
    with CaptureQueriesContext(connection) as context:
        response = client.get(url)
    assert response.status_code == 200
    return len(context.captured_queries)


@pytest.mark.django_db
def test_the_campaign_page_marks_every_name_it_shows(viewer, client, make_table):
    bare = make_table("Bare")
    full = make_table("Full", admins=2, gangs=2)

    # Each admin under Arbitrators, each gang's owner in the gangs table, and
    # each gang owner again as the author of their action.
    assert _marks(client, reverse("core:campaign", args=[full.id])) == (
        _marks(client, reverse("core:campaign", args=[bare.id])) + 2 + 2 + 2
    )


@pytest.mark.django_db
def test_the_campaign_page_reads_the_badges_once_for_everybody(
    viewer, client, make_table
):
    """More admins is the same number of queries — the gangs table has
    per-gang costs of its own, so the count is held over the arbitrators."""
    small = make_table("Small", admins=1, gangs=1)
    large = make_table("Large", admins=4, gangs=1)

    assert _queries(client, reverse("core:campaign", args=[large.id])) == _queries(
        client, reverse("core:campaign", args=[small.id])
    )


@pytest.mark.django_db
def test_the_arbitrators_page_marks_the_owner_and_every_admin(
    owner, client, make_table
):
    bare = make_table("Bare")
    full = make_table("Full", admins=3)
    client.force_login(owner)

    assert _marks(client, reverse("core:campaign-arbitrators", args=[full.id])) == (
        _marks(client, reverse("core:campaign-arbitrators", args=[bare.id])) + 3
    )


@pytest.mark.django_db
def test_the_arbitrators_page_reads_the_badges_once_for_everybody(
    owner, client, make_table
):
    small = make_table("Small", admins=1)
    large = make_table("Large", admins=4)
    client.force_login(owner)

    assert _queries(
        client, reverse("core:campaign-arbitrators", args=[large.id])
    ) == _queries(client, reverse("core:campaign-arbitrators", args=[small.id]))


@pytest.mark.django_db
def test_the_start_page_marks_every_gang_owner(owner, client, make_table):
    """Held over a campaign of one gang: a campaign with none has nothing
    to start, and the page sends the reader back."""
    small = make_table("Small", gangs=1)
    large = make_table("Large", gangs=4)
    client.force_login(owner)

    assert _marks(client, reverse("core:campaign-start", args=[large.id])) == (
        _marks(client, reverse("core:campaign-start", args=[small.id])) + 3
    )


@pytest.mark.django_db
def test_the_start_page_reads_the_badges_once_for_everybody(owner, client, make_table):
    small = make_table("Small", gangs=1)
    large = make_table("Large", gangs=4)
    client.force_login(owner)

    assert _queries(
        client, reverse("core:campaign-start", args=[large.id])
    ) == _queries(client, reverse("core:campaign-start", args=[small.id]))


@pytest.mark.django_db
def test_the_actions_page_marks_every_author(viewer, client, make_table):
    bare = make_table("Bare")
    full = make_table("Full", gangs=3)

    assert _marks(client, reverse("core:campaign-actions", args=[full.id])) == (
        _marks(client, reverse("core:campaign-actions", args=[bare.id])) + 3
    )


@pytest.mark.django_db
def test_the_actions_page_reads_the_badges_once_for_everybody(
    viewer, client, make_table
):
    small = make_table("Small", gangs=1)
    large = make_table("Large", gangs=4)

    assert _queries(
        client, reverse("core:campaign-actions", args=[large.id])
    ) == _queries(client, reverse("core:campaign-actions", args=[small.id]))
