"""Every username on a campaign screen carries the person's badge.

The badge beside a name is read off that person's profile and their badge
grants, so a page naming several people must fetch those for everybody at
once: these pin that the campaign screens draw the badge at every name, and
that naming more people costs no more queries.
"""

import pytest
from django.db import connection
from django.template.loader import render_to_string
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from gyrinx.accounts.models import PatreonStatus, UserProfile
from gyrinx.badges import badge_by_slug
from n23.core.models.battle import Battle, BattleNote
from n23.core.models.campaign import CampaignAction
from n23.core.models.invitation import CampaignInvitation
from n23.core.models.list import List
from n23.core.models.pack import CustomContentPack

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
    """A public campaign with badged admins and badged gang owners, one
    action logged by each gang owner, and badged owners of gangs still
    invited."""

    def _make(name, *, admins=0, gangs=0, invited=0):
        campaign = make_campaign(name, public=True)
        for index in range(admins):
            campaign.admins.add(_badged(make_user, f"{name}-admin-{index}"))
        for index in range(invited):
            player = _badged(make_user, f"{name}-invited-{index}")
            CampaignInvitation.objects.create(
                campaign=campaign,
                list=make_list(f"{name} invited gang {index}", owner=player),
                status=CampaignInvitation.PENDING,
            )
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


def _queries(client, url, post=None):
    """How many queries a page costs, once the session has settled — the
    first request after signing in records the session, which is a cost of
    signing in and not of the page. With ``post``, the cost of that form
    being submitted and the page re-drawn."""
    client.get(url)
    with CaptureQueriesContext(connection) as context:
        response = client.post(url, post) if post is not None else client.get(url)
    assert response.status_code == 200
    return len(context.captured_queries)


@pytest.mark.django_db
def test_the_campaign_page_marks_every_name_it_shows(viewer, client, make_table):
    bare = make_table("Bare")
    full = make_table("Full", admins=2, gangs=2, invited=2)

    # Each admin under Arbitrators, each gang's owner in the gangs table, each
    # gang owner again as the author of their action, and each invited gang's
    # owner under Invited.
    assert _marks(client, reverse("core:campaign", args=[full.id])) == (
        _marks(client, reverse("core:campaign", args=[bare.id])) + 2 + 2 + 2 + 2
    )


@pytest.mark.django_db
def test_the_campaign_page_reads_the_badges_once_for_everybody(
    viewer, client, make_table
):
    """More admins and more invited gangs is the same number of queries —
    the gangs table has per-gang costs of its own, so the count is held
    over the arbitrators and the invitations."""
    small = make_table("Small", admins=1, gangs=1, invited=1)
    large = make_table("Large", admins=4, gangs=1, invited=4)

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
def test_the_arbitrators_page_reads_the_owners_badge_with_the_campaign(
    viewer, client, make_user, make_campaign, make_table
):
    """The owner is named with their badge too, and the campaign arrives
    with their profile and grants alongside — so an owner holding a badge
    costs the page nothing more than one holding none."""
    badged = make_table("Badged")
    plain = make_campaign(
        "Plain", owner=make_user("plain-owner", "password"), public=True
    )
    for campaign in (badged, plain):
        campaign.admins.add(viewer)

    assert _queries(
        client, reverse("core:campaign-arbitrators", args=[badged.id])
    ) == _queries(client, reverse("core:campaign-arbitrators", args=[plain.id]))


@pytest.mark.django_db
def test_the_arbitrators_page_reads_the_owners_badge_when_it_refuses_a_name(
    viewer, client, make_user, make_campaign, make_table
):
    """A name nobody has is refused and the page drawn again, owner and
    all — with the owner's badge data read alongside, as on a plain visit."""
    badged = make_table("Badged")
    plain = make_campaign(
        "Plain", owner=make_user("plain-owner", "password"), public=True
    )
    for campaign in (badged, plain):
        campaign.admins.add(viewer)
    refused = {"username": "nobody-by-that-name"}

    assert _queries(
        client, reverse("core:campaign-arbitrators", args=[badged.id]), post=refused
    ) == _queries(
        client, reverse("core:campaign-arbitrators", args=[plain.id]), post=refused
    )


@pytest.mark.django_db
def test_the_campaign_page_reads_the_actions_battles_with_the_actions(
    owner, viewer, client, make_table
):
    """An action logged from a battle links the battle by name, and the
    battle comes with the action rather than one query per action. Held
    over the actions of one battle: the recent-battles block has a cost per
    battle of its own, and it is the actions' reading of the battle that is
    under test."""

    def fought(campaign, actions):
        battle = Battle.objects.create(
            campaign=campaign, mission="Mission", owner=owner
        )
        for index in range(actions):
            CampaignAction.objects.create(
                campaign=campaign,
                user=owner,
                battle=battle,
                description=f"Round {index} recorded",
            )
        return campaign

    small = fought(make_table("Small"), 1)
    large = fought(make_table("Large"), 4)

    assert (
        "Mission"
        in client.get(reverse("core:campaign", args=[small.id])).content.decode()
    )
    assert _queries(client, reverse("core:campaign", args=[large.id])) == _queries(
        client, reverse("core:campaign", args=[small.id])
    )


@pytest.fixture
def make_battle(owner, make_user):
    """A battle in a campaign, with a note from each of ``notes`` badged
    authors."""

    def _make(campaign, *, notes=0):
        battle = Battle.objects.create(
            campaign=campaign, mission="Mission", owner=owner
        )
        for index in range(notes):
            BattleNote.objects.create(
                battle=battle,
                content=f"Note {index}",
                owner=_badged(make_user, f"{campaign.name}-writer-{index}"),
            )
        return battle

    return _make


@pytest.mark.django_db
def test_the_battle_page_marks_its_owner_and_every_notes_author(
    viewer, client, make_table, make_battle
):
    bare = make_battle(make_table("Bare"))
    full = make_battle(make_table("Full"), notes=3)

    # The three authors; the battle's owner and the campaign's owner (the
    # same person, in the header and the trail) are on both pages.
    assert _marks(client, reverse("core:battle", args=[full.id])) == (
        _marks(client, reverse("core:battle", args=[bare.id])) + 3
    )
    assert _marks(client, reverse("core:battle", args=[bare.id])) >= 2


@pytest.mark.django_db
def test_the_battle_page_reads_the_badges_once_for_everybody(
    viewer, client, make_table, make_battle
):
    small = make_battle(make_table("Small"), notes=1)
    large = make_battle(make_table("Large"), notes=4)

    assert _queries(client, reverse("core:battle", args=[large.id])) == _queries(
        client, reverse("core:battle", args=[small.id])
    )


@pytest.mark.django_db
def test_a_printed_breadcrumb_names_the_owner_without_a_link(owner):
    """On paper there is nothing to click, so the breadcrumb include writes
    the owner's name plain when ``print`` is set, and links it otherwise."""
    context = {"type": "List", "owner": owner, "name": "Cawdor Facts"}

    printed = render_to_string(
        "core/includes/breadcrumb.html", {**context, "print": True}
    )
    screen = render_to_string("core/includes/breadcrumb.html", context)

    assert owner.username in printed and "<a" not in printed
    assert f'href="/user/{owner.username}"' in screen
    assert MARK in screen and MARK not in printed


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
def test_a_gang_nobody_owns_is_offered_with_no_owner_named(
    owner, client, make_table, content_house
):
    """``owner`` is nullable, and a public gang with no owner is offered to a
    campaign like any other: its row names nobody rather than failing to
    build a link to nobody's page."""
    campaign = make_table("Dust Falls")
    List.objects.create(
        name="Unclaimed gang",
        content_house=content_house,
        public=True,
        status=List.LIST_BUILDING,
        owner=None,
    )
    client.force_login(owner)

    response = client.get(reverse("core:campaign-add-lists", args=[campaign.id]))

    assert response.status_code == 200
    assert "Unclaimed gang" in response.content.decode()


@pytest.mark.django_db
def test_a_pack_nobody_owns_is_listed_with_no_owner_named(owner, client, make_table):
    campaign = make_table("Dust Falls")
    campaign.packs.add(
        CustomContentPack.objects.create(name="Unclaimed pack", owner=None, listed=True)
    )
    client.force_login(owner)

    response = client.get(reverse("core:campaign-packs", args=[campaign.id]))

    assert response.status_code == 200
    assert "Unclaimed pack" in response.content.decode()


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
