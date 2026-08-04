"""Recording the result when a battle ends.

An ended battle with no recorded result is a distinct state from a draw:
battles ended before results were captured look exactly like a draw unless the
two are told apart, which is what ``Battle.result`` exists for.
"""

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from n23.core.handlers.battle import handle_battle_end
from n23.core.models import Battle, CampaignAction


@pytest.fixture
def in_progress_battle(user, campaign, make_list):
    """A battle in progress with two participating gangs."""

    def build(count=2):
        lists = []
        for i in range(count):
            lst = make_list(f"Gang {i + 1}")
            campaign.lists.add(lst)
            lists.append(lst)
        battle = Battle.objects.create(campaign=campaign, mission="M", owner=user)
        battle.set_participants(lists)
        battle.states.transition_to(Battle.IN_PROGRESS)
        return battle, lists

    return build


# --- Handler ---------------------------------------------------------------


@pytest.mark.django_db
def test_handler_records_winners(user, in_progress_battle):
    battle, (l1, l2) = in_progress_battle()

    result = handle_battle_end(user=user, battle=battle, winners=[l1], is_draw=False)

    battle.refresh_from_db()
    assert battle.result == Battle.RESULT_WINNERS
    assert battle.result_recorded is True
    assert battle.is_draw is False
    assert list(battle.winners.values_list("id", flat=True)) == [l1.id]
    assert battle.status == Battle.POST_BATTLE
    assert result.campaign_action.outcome == f"Winner: {l1.name}"
    assert result.campaign_action.battle == battle
    assert result.campaign_action.list is None


@pytest.mark.django_db
def test_handler_records_multiple_winners(user, in_progress_battle):
    battle, (l1, l2) = in_progress_battle()

    result = handle_battle_end(
        user=user, battle=battle, winners=[l2, l1], is_draw=False
    )

    assert battle.winners.count() == 2
    # Names are sorted so the outcome text is stable regardless of input order.
    assert result.campaign_action.outcome == f"Winners: {l1.name}, {l2.name}"


@pytest.mark.django_db
def test_handler_records_draw(user, in_progress_battle):
    battle, _ = in_progress_battle()

    result = handle_battle_end(user=user, battle=battle, winners=[], is_draw=True)

    battle.refresh_from_db()
    assert battle.result == Battle.RESULT_DRAW
    assert battle.is_draw is True
    assert battle.winners.count() == 0
    assert result.campaign_action.outcome == "Draw"


@pytest.mark.django_db
def test_handler_rejects_a_win_with_no_winners(user, in_progress_battle):
    """The form stops this, but the handler owns the invariant: "someone won"
    with nobody in it would record an empty "Winner:" outcome."""
    battle, _ = in_progress_battle()

    with pytest.raises(ValidationError, match="at least one winning gang"):
        handle_battle_end(user=user, battle=battle, winners=[], is_draw=False)

    battle.refresh_from_db()
    assert battle.result == Battle.RESULT_UNRECORDED
    assert battle.states.current == Battle.IN_PROGRESS
    assert not CampaignAction.objects.filter(battle=battle).exists()


@pytest.mark.django_db
def test_handler_draw_clears_prefilled_winners(user, in_progress_battle):
    """Winners set earlier via the edit form must not survive a draw."""
    battle, (l1, _) = in_progress_battle()
    battle.winners.set([l1])

    handle_battle_end(user=user, battle=battle, winners=[l1], is_draw=True)

    battle.refresh_from_db()
    assert battle.winners.count() == 0
    assert battle.result == Battle.RESULT_DRAW


@pytest.mark.django_db
def test_handler_rejects_already_ended_battle(user, in_progress_battle):
    battle, (l1, _) = in_progress_battle()
    handle_battle_end(user=user, battle=battle, winners=[l1], is_draw=False)
    actions_before = CampaignAction.objects.filter(battle=battle).count()

    with pytest.raises(ValidationError, match="already been ended"):
        handle_battle_end(user=user, battle=battle, winners=[l1], is_draw=True)

    battle.refresh_from_db()
    # The first result stands, and no second action was written.
    assert battle.result == Battle.RESULT_WINNERS
    assert CampaignAction.objects.filter(battle=battle).count() == actions_before


@pytest.mark.django_db
def test_handler_rejects_non_participant_winner(
    user, campaign, make_list, in_progress_battle
):
    battle, _ = in_progress_battle()
    outsider = make_list("Outsider")
    campaign.lists.add(outsider)

    with pytest.raises(ValidationError, match="without being a participant"):
        handle_battle_end(user=user, battle=battle, winners=[outsider], is_draw=False)

    battle.refresh_from_db()
    assert battle.status == Battle.IN_PROGRESS
    assert battle.result == Battle.RESULT_UNRECORDED


@pytest.mark.django_db
def test_result_survives_state_transition(user, in_progress_battle):
    """Regression: transition_to() saves with update_fields=["status", "modified"].

    If the result is written to the instance but not persisted before the
    transition, that save silently discards it and the battle ends with no
    recorded result.
    """
    battle, (l1, _) = in_progress_battle()

    handle_battle_end(user=user, battle=battle, winners=[l1], is_draw=False)

    battle.refresh_from_db()
    assert battle.result == Battle.RESULT_WINNERS
    assert battle.status == Battle.POST_BATTLE


# --- End view --------------------------------------------------------------


@pytest.mark.django_db
def test_end_view_renders_participants_and_options(client, user, in_progress_battle):
    battle, (l1, l2) = in_progress_battle()
    client.force_login(user)

    resp = client.get(reverse("core:battle-end", args=[battle.id]))
    assert resp.status_code == 200
    content = resp.content.decode()
    assert l1.name in content
    assert l2.name in content
    assert "One or more gangs won" in content
    assert "Draw" in content


@pytest.mark.django_db
def test_end_view_requires_a_result(client, user, in_progress_battle):
    battle, _ = in_progress_battle()
    client.force_login(user)

    resp = client.post(reverse("core:battle-end", args=[battle.id]), {})
    assert resp.status_code == 200
    assert "Choose a result before ending the battle." in resp.content.decode()
    battle.refresh_from_db()
    assert battle.status == Battle.IN_PROGRESS
    assert battle.result == Battle.RESULT_UNRECORDED


@pytest.mark.django_db
def test_end_view_winners_choice_needs_a_gang(client, user, in_progress_battle):
    battle, _ = in_progress_battle()
    client.force_login(user)

    resp = client.post(
        reverse("core:battle-end", args=[battle.id]), {"result": "winners"}
    )
    assert resp.status_code == 200
    assert "Select at least one winning gang" in resp.content.decode()
    battle.refresh_from_db()
    assert battle.status == Battle.IN_PROGRESS


@pytest.mark.django_db
def test_end_view_draw_rejects_winners(client, user, in_progress_battle):
    battle, (l1, _) = in_progress_battle()
    client.force_login(user)

    resp = client.post(
        reverse("core:battle-end", args=[battle.id]),
        {"result": "draw", "winners": [str(l1.id)]},
    )
    assert resp.status_code == 200
    assert "A draw has no winners" in resp.content.decode()
    battle.refresh_from_db()
    assert battle.status == Battle.IN_PROGRESS


@pytest.mark.django_db
def test_end_view_rejects_non_participant(
    client, user, campaign, make_list, in_progress_battle
):
    battle, _ = in_progress_battle()
    outsider = make_list("Outsider")
    campaign.lists.add(outsider)
    client.force_login(user)

    resp = client.post(
        reverse("core:battle-end", args=[battle.id]),
        {"result": "winners", "winners": [str(outsider.id)]},
    )
    assert resp.status_code == 200
    battle.refresh_from_db()
    assert battle.status == Battle.IN_PROGRESS
    assert battle.winners.count() == 0


@pytest.mark.django_db
def test_end_view_records_winner(client, user, in_progress_battle):
    battle, (l1, _) = in_progress_battle()
    client.force_login(user)

    resp = client.post(
        reverse("core:battle-end", args=[battle.id]),
        {"result": "winners", "winners": [str(l1.id)]},
    )
    assert resp.status_code == 302
    battle.refresh_from_db()
    assert battle.status == Battle.POST_BATTLE
    assert battle.result == Battle.RESULT_WINNERS
    assert list(battle.winners.values_list("id", flat=True)) == [l1.id]


@pytest.mark.django_db
def test_participant_gang_owner_can_record_result(
    client, user, make_user, campaign, make_list
):
    player = make_user("player_end", "password")
    plist = make_list("Player Gang", owner=player)
    campaign.lists.add(plist)
    battle = Battle.objects.create(campaign=campaign, mission="M", owner=user)
    battle.set_participants([plist])
    battle.states.transition_to(Battle.IN_PROGRESS)

    client.force_login(player)
    resp = client.post(
        reverse("core:battle-end", args=[battle.id]),
        {"result": "winners", "winners": [str(plist.id)]},
    )
    assert resp.status_code == 302
    battle.refresh_from_db()
    assert battle.result == Battle.RESULT_WINNERS


@pytest.mark.django_db
def test_non_manager_cannot_record_result(
    client, user, make_user, campaign, make_list, in_progress_battle
):
    battle, _ = in_progress_battle()
    outsider = make_user("outsider_end", "password")
    client.force_login(outsider)

    resp = client.post(reverse("core:battle-end", args=[battle.id]), {"result": "draw"})
    assert resp.status_code == 302
    battle.refresh_from_db()
    assert battle.status == Battle.IN_PROGRESS
    assert battle.result == Battle.RESULT_UNRECORDED


@pytest.mark.django_db
def test_ending_twice_is_idempotent(client, user, in_progress_battle):
    battle, (l1, l2) = in_progress_battle()
    client.force_login(user)
    url = reverse("core:battle-end", args=[battle.id])

    client.post(url, {"result": "winners", "winners": [str(l1.id)]})
    actions_after_first = CampaignAction.objects.filter(battle=battle).count()

    resp = client.post(url, {"result": "winners", "winners": [str(l2.id)]})
    assert resp.status_code == 302
    battle.refresh_from_db()
    # The second POST changes nothing: same winner, same action count.
    assert list(battle.winners.values_list("id", flat=True)) == [l1.id]
    assert CampaignAction.objects.filter(battle=battle).count() == actions_after_first


# --- Battle page display ---------------------------------------------------


@pytest.mark.django_db
def test_draw_shows_draw_note(client, user, in_progress_battle):
    battle, _ = in_progress_battle()
    handle_battle_end(user=user, battle=battle, winners=[], is_draw=True)
    client.force_login(user)

    content = client.get(reverse("core:battle", args=[battle.id])).content.decode()
    assert "This battle ended in a draw." in content
    assert "No result was recorded" not in content


@pytest.mark.django_db
def test_legacy_post_battle_without_result_is_not_called_a_draw(
    client, user, in_progress_battle
):
    """A battle ended before results existed has no winners and no result.

    It must not be presented as a draw — that is the bug this field fixes.
    """
    battle, _ = in_progress_battle()
    battle.states.transition_to(Battle.POST_BATTLE)
    battle.refresh_from_db()
    assert battle.result == Battle.RESULT_UNRECORDED
    assert battle.winners.count() == 0

    client.force_login(user)
    content = client.get(reverse("core:battle", args=[battle.id])).content.decode()
    assert "ended in a draw" not in content
    assert "No result was recorded for this battle." in content


@pytest.mark.django_db
def test_winner_result_shows_neither_note(client, user, in_progress_battle):
    battle, (l1, _) = in_progress_battle()
    handle_battle_end(user=user, battle=battle, winners=[l1], is_draw=False)
    client.force_login(user)

    content = client.get(reverse("core:battle", args=[battle.id])).content.decode()
    assert "ended in a draw" not in content
    assert "No result was recorded" not in content


# --- Edit form -------------------------------------------------------------


@pytest.mark.django_db
def test_post_battle_edit_requires_a_result(client, user, in_progress_battle):
    battle, (l1, _) = in_progress_battle()
    battle.states.transition_to(Battle.POST_BATTLE)
    client.force_login(user)

    resp = client.post(
        reverse("core:battle-edit", args=[battle.id]),
        {"mission": "M", "participants": [str(l1.id)]},
    )
    assert resp.status_code == 200
    battle.refresh_from_db()
    assert battle.result == Battle.RESULT_UNRECORDED

    resp = client.post(
        reverse("core:battle-edit", args=[battle.id]),
        {"mission": "M", "participants": [str(l1.id)], "result": "draw"},
    )
    assert resp.status_code == 302
    battle.refresh_from_db()
    assert battle.result == Battle.RESULT_DRAW


@pytest.mark.django_db
def test_pre_battle_edit_does_not_require_a_result(client, user, campaign, make_list):
    """Editing a battle that has not been fought must be unaffected."""
    l1 = make_list("Gang 1")
    campaign.lists.add(l1)
    battle = Battle.objects.create(campaign=campaign, mission="M", owner=user)
    battle.set_participants([l1])
    client.force_login(user)

    resp = client.post(
        reverse("core:battle-edit", args=[battle.id]),
        {"mission": "Ambush", "participants": [str(l1.id)]},
    )
    assert resp.status_code == 302
    battle.refresh_from_db()
    assert battle.mission == "Ambush"
    assert battle.result == Battle.RESULT_UNRECORDED
