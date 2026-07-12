import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from gyrinx.content.models import ContentCounter, ContentInjury
from gyrinx.content.models.injury import ContentInjuryDefaultOutcome
from gyrinx.core.handlers.fighter import (
    handle_fighter_add_injury,
    handle_fighter_add_xp,
    handle_fighter_adjust_counter,
)
from gyrinx.core.models.campaign import CampaignAction
from gyrinx.core.models.list import ListFighter, ListFighterCounter, ListFighterInjury


# --- Handlers --------------------------------------------------------------


@pytest.mark.django_db
def test_handle_fighter_add_xp(user, list_with_campaign, make_list_fighter):
    fighter = make_list_fighter(list_with_campaign, "F1")
    fighter.xp_current = 2
    fighter.xp_total = 5
    fighter.save()

    result = handle_fighter_add_xp(user=user, fighter=fighter, amount=3)

    fighter.refresh_from_db()
    assert fighter.xp_current == 5
    assert fighter.xp_total == 8
    assert result.campaign_action is not None
    assert CampaignAction.objects.filter(list=list_with_campaign).count() == 1


@pytest.mark.django_db
def test_handle_fighter_add_xp_rejects_nonpositive(
    user, list_with_campaign, make_list_fighter
):
    fighter = make_list_fighter(list_with_campaign, "F1")
    for bad in (0, -1):
        with pytest.raises(ValidationError):
            handle_fighter_add_xp(user=user, fighter=fighter, amount=bad)


@pytest.mark.django_db
def test_handle_fighter_add_injury_applies_outcome(
    user, list_with_campaign, make_list_fighter
):
    fighter = make_list_fighter(list_with_campaign, "F1")
    injury = ContentInjury.objects.create(
        name="Spinal Injury", phase=ContentInjuryDefaultOutcome.RECOVERY
    )

    result = handle_fighter_add_injury(user=user, fighter=fighter, injury=injury)

    fighter.refresh_from_db()
    assert fighter.injury_state == ListFighter.RECOVERY
    assert result.killed is False
    assert ListFighterInjury.objects.filter(fighter=fighter).count() == 1
    assert CampaignAction.objects.filter(list=list_with_campaign).count() == 1


@pytest.mark.django_db
def test_handle_fighter_add_injury_no_change_keeps_state(
    user, list_with_campaign, make_list_fighter
):
    fighter = make_list_fighter(list_with_campaign, "F1")
    assert fighter.injury_state == ListFighter.ACTIVE
    injury = ContentInjury.objects.create(
        name="Bruised", phase=ContentInjuryDefaultOutcome.NO_CHANGE
    )

    handle_fighter_add_injury(user=user, fighter=fighter, injury=injury)

    fighter.refresh_from_db()
    assert fighter.injury_state == ListFighter.ACTIVE
    assert ListFighterInjury.objects.filter(fighter=fighter).count() == 1


@pytest.mark.django_db
def test_handle_fighter_add_injury_dead_routes_through_kill(
    user, list_with_campaign, make_list_fighter
):
    fighter = make_list_fighter(list_with_campaign, "F1")
    injury = ContentInjury.objects.create(
        name="Critical", phase=ContentInjuryDefaultOutcome.DEAD
    )

    result = handle_fighter_add_injury(user=user, fighter=fighter, injury=injury)

    fighter.refresh_from_db()
    assert result.killed is True
    assert fighter.injury_state == ListFighter.DEAD
    assert fighter.is_dead is True
    # The kill handler zeroes the fighter's cost.
    assert fighter.cost_int() == 0


@pytest.mark.django_db
def test_handle_fighter_adjust_counter(user, list_with_campaign, make_list_fighter):
    fighter = make_list_fighter(list_with_campaign, "F1")
    counter = ContentCounter.objects.create(name="Kill Count")
    counter.restricted_to_fighters.add(fighter.content_fighter)

    # First adjustment creates the row.
    result = handle_fighter_adjust_counter(
        user=user, fighter=fighter, counter=counter, delta=3
    )
    assert result.new_value == 3
    row = ListFighterCounter.objects.get(fighter=fighter, counter=counter)
    assert row.value == 3

    # Negative delta clamps at zero.
    handle_fighter_adjust_counter(
        user=user, fighter=fighter, counter=counter, delta=-10
    )
    row.refresh_from_db()
    assert row.value == 0

    # A no-op delta (already zero) does nothing.
    assert (
        handle_fighter_adjust_counter(
            user=user, fighter=fighter, counter=counter, delta=-1
        )
        is None
    )


# --- View ------------------------------------------------------------------


@pytest.mark.django_db
def test_post_battle_requires_campaign_mode(client, user, make_list):
    client.force_login(user)
    lst = make_list("Building Gang")  # LIST_BUILDING by default
    resp = client.get(reverse("core:list-post-battle", args=[lst.id]))
    assert resp.status_code == 302
    assert resp.url == reverse("core:list", args=[lst.id])


@pytest.mark.django_db
def test_post_battle_page_renders(client, user, list_with_campaign, make_list_fighter):
    client.force_login(user)
    make_list_fighter(list_with_campaign, "Alpha")
    make_list_fighter(list_with_campaign, "Beta")

    resp = client.get(reverse("core:list-post-battle", args=[list_with_campaign.id]))
    assert resp.status_code == 200
    content = resp.content.decode()
    assert "Alpha" in content
    assert "Beta" in content
    assert "Post-battle updates" in content


@pytest.mark.django_db
def test_post_battle_applies_only_edited_fields(
    client, user, list_with_campaign, make_list_fighter
):
    client.force_login(user)
    f_xp = make_list_fighter(list_with_campaign, "XPGuy")
    f_injury = make_list_fighter(list_with_campaign, "HurtGuy")
    f_counter = make_list_fighter(list_with_campaign, "CountGuy")
    untouched = make_list_fighter(list_with_campaign, "Bystander")

    injury = ContentInjury.objects.create(
        name="Head Wound", phase=ContentInjuryDefaultOutcome.RECOVERY
    )
    counter = ContentCounter.objects.create(name="Kills")
    counter.restricted_to_fighters.add(f_counter.content_fighter)

    resp = client.post(
        reverse("core:list-post-battle", args=[list_with_campaign.id]),
        {
            f"xp_{f_xp.pk}": "2",
            f"injury_{f_injury.pk}": str(injury.pk),
            f"injury_reason_{f_injury.pk}": "Took a bad hit",
            f"counter_{f_counter.pk}_{counter.pk}": "4",
            f"private_notes_{f_xp.pk}": "Fought bravely",
        },
    )
    assert resp.status_code == 302

    f_xp.refresh_from_db()
    f_injury.refresh_from_db()
    f_counter.refresh_from_db()
    untouched.refresh_from_db()

    # Only the edited fields were applied.
    assert f_xp.xp_current == 2
    assert f_xp.private_notes == "Fought bravely"
    assert f_injury.injury_state == ListFighter.RECOVERY
    assert ListFighterInjury.objects.filter(fighter=f_injury).count() == 1
    assert ListFighterCounter.objects.get(fighter=f_counter, counter=counter).value == 4

    # Everyone else is untouched.
    assert untouched.xp_current == 0
    assert untouched.injury_state == ListFighter.ACTIVE
    assert f_xp.injury_state == ListFighter.ACTIVE
    assert f_injury.xp_current == 0


@pytest.mark.django_db
def test_post_battle_injury_requires_reason(
    client, user, list_with_campaign, make_list_fighter
):
    client.force_login(user)
    fighter = make_list_fighter(list_with_campaign, "HurtGuy")
    injury = ContentInjury.objects.create(
        name="Sprain", phase=ContentInjuryDefaultOutcome.RECOVERY
    )

    # Selecting an injury without a reason is rejected; nothing is applied.
    resp = client.post(
        reverse("core:list-post-battle", args=[list_with_campaign.id]),
        {f"injury_{fighter.pk}": str(injury.pk)},
    )
    assert resp.status_code == 200  # re-render with errors
    fighter.refresh_from_db()
    assert fighter.injury_state == ListFighter.ACTIVE
    assert ListFighterInjury.objects.filter(fighter=fighter).count() == 0


@pytest.mark.django_db
def test_post_battle_links_actions_to_selected_battle(
    client, user, list_with_campaign, make_list_fighter
):
    from gyrinx.core.models.battle import Battle

    client.force_login(user)
    fighter = make_list_fighter(list_with_campaign, "XPGuy")
    battle = Battle.objects.create(
        campaign=list_with_campaign.campaign, mission="Ambush", owner=user
    )
    battle.set_participants([list_with_campaign])

    resp = client.post(
        reverse("core:list-post-battle", args=[list_with_campaign.id]),
        {"battle": str(battle.pk), f"xp_{fighter.pk}": "2"},
    )
    assert resp.status_code == 302

    action = CampaignAction.objects.get(list=list_with_campaign)
    assert action.battle_id == battle.pk


@pytest.mark.django_db
def test_post_battle_battle_url_param_preselects(
    client, user, list_with_campaign, make_list_fighter
):
    from gyrinx.core.models.battle import Battle

    client.force_login(user)
    make_list_fighter(list_with_campaign, "F1")
    battle = Battle.objects.create(
        campaign=list_with_campaign.campaign, mission="Ambush", owner=user
    )
    battle.set_participants([list_with_campaign])

    resp = client.get(
        reverse("core:list-post-battle", args=[list_with_campaign.id]),
        {"battle": str(battle.pk)},
    )
    assert resp.status_code == 200
    assert resp.context["form"]["battle"].value() == str(battle.pk)

    # A battle the list didn't fight in is ignored, not preselected.
    other = Battle.objects.create(
        campaign=list_with_campaign.campaign, mission="Elsewhere", owner=user
    )
    resp = client.get(
        reverse("core:list-post-battle", args=[list_with_campaign.id]),
        {"battle": str(other.pk)},
    )
    assert resp.context["form"]["battle"].value() in (None, "")


@pytest.mark.django_db
def test_post_battle_arbitrator_can_edit_and_outsider_cannot(
    client, user, make_user, campaign, content_house, make_list, make_list_fighter
):
    from gyrinx.core.models.list import List

    player = make_user("player_pb", "password")
    plist = make_list(
        "Player Gang", owner=player, status=List.CAMPAIGN_MODE, campaign=campaign
    )
    campaign.lists.add(plist)
    fighter = make_list_fighter(plist, "PGang Fighter", owner=player)

    # Arbitrator (campaign owner = user) can apply updates to a list they don't own.
    client.force_login(user)
    resp = client.post(
        reverse("core:list-post-battle", args=[plist.id]),
        {f"xp_{fighter.pk}": "1"},
    )
    assert resp.status_code == 302
    fighter.refresh_from_db()
    assert fighter.xp_current == 1

    # An unrelated user gets a 404.
    outsider = make_user("outsider_pb", "password")
    client.force_login(outsider)
    resp = client.get(reverse("core:list-post-battle", args=[plist.id]))
    assert resp.status_code == 404
