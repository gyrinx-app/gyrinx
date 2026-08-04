"""Tests for the campaign "View all battles" page (#1015).

The campaign overview only shows the most recent battles (capped at
``battles_limit``) with a "View all N battles" link. These tests cover the
dedicated page that link points at: it renders and lists *every* non-archived
battle in the campaign, and the overview link actually targets it.
"""

import pytest
from django.urls import reverse

from n23.core.models import Battle


def _make_battles(campaign, owner, participant_list, count):
    """Create ``count`` battles in ``campaign`` with a single participant."""
    battles = []
    for i in range(count):
        battle = Battle.objects.create(
            campaign=campaign, mission=f"Mission {i}", owner=owner
        )
        battle.set_participants([participant_list])
        battles.append(battle)
    return battles


@pytest.mark.django_db
def test_campaign_battles_page_lists_all_battles(client, user, campaign, make_list):
    """The page renders (200) and lists every battle, past the overview cap."""
    client.force_login(user)
    gang = make_list("Gang")
    campaign.lists.add(gang)

    # More than the overview limit (5) so this exercises the "no limit" behaviour.
    battles = _make_battles(campaign, user, gang, 6)

    resp = client.get(reverse("core:campaign-battles", args=[campaign.id]))
    assert resp.status_code == 200

    content = resp.content.decode()
    for battle in battles:
        assert reverse("core:battle", args=[battle.id]) in content


@pytest.mark.django_db
def test_campaign_overview_links_to_view_all_battles(client, user, campaign, make_list):
    """The overview's "View all battles" link points at the battles page."""
    client.force_login(user)
    gang = make_list("Gang")
    campaign.lists.add(gang)

    # Need more battles than the overview cap (5) for the link to appear.
    _make_battles(campaign, user, gang, 6)

    resp = client.get(reverse("core:campaign", args=[campaign.id]))
    assert resp.status_code == 200

    battles_url = reverse("core:campaign-battles", args=[campaign.id])
    assert battles_url in resp.content.decode()


@pytest.mark.django_db
def test_campaign_battles_page_empty_state(client, user, campaign):
    """With no battles the page still renders and shows the empty state."""
    client.force_login(user)

    resp = client.get(reverse("core:campaign-battles", args=[campaign.id]))
    assert resp.status_code == 200
    assert "No battles have been recorded" in resp.content.decode()


@pytest.mark.django_db
def test_battle_card_separates_gang_names_without_a_leading_space(
    client, user, campaign, make_list
):
    """The names sat on their own template lines, so the newline rendered as a
    space and the list read "Gang A , Gang B"."""
    client.force_login(user)
    first = make_list("Gang A")
    second = make_list("Gang B")
    campaign.lists.add(first, second)
    battle = Battle.objects.create(campaign=campaign, mission="Mission", owner=user)
    battle.set_participants([first, second])

    content = client.get(
        reverse("core:campaign-battles", args=[campaign.id])
    ).content.decode()

    assert "<span>Gang A</span><span>,&nbsp;</span><span>Gang B</span>" in content
    assert "Gang A ," not in content


@pytest.mark.django_db
def test_battle_card_announces_the_winner_to_screen_readers(
    client, user, campaign, make_list
):
    """The trophy is the only winner marker on this card and carries no tooltip,
    so it must be decorative with the state spelled out beside it."""
    client.force_login(user)
    winner = make_list("Gang A")
    loser = make_list("Gang B")
    campaign.lists.add(winner, loser)
    battle = Battle.objects.create(campaign=campaign, mission="Mission", owner=user)
    battle.set_participants([winner, loser])
    battle.winners.set([winner])

    content = client.get(
        reverse("core:campaign-battles", args=[campaign.id])
    ).content.decode()

    assert '<i class="bi-trophy-fill text-warning" aria-hidden="true"></i>' in content
    assert '<span class="visually-hidden">(winner)</span>' in content
