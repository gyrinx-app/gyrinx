import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from n23.content.models import ContentCounter, ContentInjury
from n23.content.models.injury import ContentInjuryDefaultOutcome
from n23.core.handlers.fighter import (
    handle_fighter_add_injury,
    handle_fighter_add_xp,
    handle_fighter_adjust_counter,
)
from n23.core.models.campaign import CampaignAction
from n23.core.models.list import ListFighter, ListFighterCounter, ListFighterInjury

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
def test_handle_fighter_add_injury_requires_campaign_mode(
    user, make_list, make_list_fighter
):
    lst = make_list("Building Gang")  # LIST_BUILDING, not campaign mode
    fighter = make_list_fighter(lst, "F1")
    injury = ContentInjury.objects.create(
        name="Scratch", phase=ContentInjuryDefaultOutcome.RECOVERY
    )
    with pytest.raises(ValueError):
        handle_fighter_add_injury(user=user, fighter=fighter, injury=injury)
    # Nothing was recorded.
    assert ListFighterInjury.objects.filter(fighter=fighter).count() == 0


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
            f"counter_{f_counter.pk}_{counter.pk}": "4",
        },
    )
    assert resp.status_code == 302

    f_xp.refresh_from_db()
    f_injury.refresh_from_db()
    f_counter.refresh_from_db()
    untouched.refresh_from_db()

    # Only the edited fields were applied.
    assert f_xp.xp_current == 2
    assert f_injury.injury_state == ListFighter.RECOVERY
    assert ListFighterInjury.objects.filter(fighter=f_injury).count() == 1
    assert ListFighterCounter.objects.get(fighter=f_counter, counter=counter).value == 4

    # Everyone else is untouched.
    assert untouched.xp_current == 0
    assert untouched.injury_state == ListFighter.ACTIVE
    assert f_xp.injury_state == ListFighter.ACTIVE
    assert f_injury.xp_current == 0


@pytest.mark.django_db
def test_post_battle_multiple_injuries_applied(
    client, user, list_with_campaign, make_list_fighter
):
    client.force_login(user)
    fighter = make_list_fighter(list_with_campaign, "HurtGuy")
    sprain = ContentInjury.objects.create(
        name="Sprain", phase=ContentInjuryDefaultOutcome.RECOVERY
    )
    scar = ContentInjury.objects.create(
        name="Scar", phase=ContentInjuryDefaultOutcome.NO_CHANGE
    )

    # The injury select can be repeated (same name, multiple values); blank
    # rows from untouched cloned selects are ignored.
    resp = client.post(
        reverse("core:list-post-battle", args=[list_with_campaign.id]),
        {f"injury_{fighter.pk}": ["", str(sprain.pk), str(scar.pk)]},
    )
    assert resp.status_code == 302
    fighter.refresh_from_db()
    assert ListFighterInjury.objects.filter(fighter=fighter).count() == 2
    # RECOVERY (from Sprain) sticks; Scar is NO_CHANGE.
    assert fighter.injury_state == ListFighter.RECOVERY


@pytest.mark.django_db
def test_post_battle_same_injury_twice(
    client, user, list_with_campaign, make_list_fighter
):
    client.force_login(user)
    fighter = make_list_fighter(list_with_campaign, "HurtGuy")
    injury = ContentInjury.objects.create(
        name="Humiliated", phase=ContentInjuryDefaultOutcome.NO_CHANGE
    )

    resp = client.post(
        reverse("core:list-post-battle", args=[list_with_campaign.id]),
        {f"injury_{fighter.pk}": [str(injury.pk), str(injury.pk)]},
    )
    assert resp.status_code == 302
    assert ListFighterInjury.objects.filter(fighter=fighter).count() == 2


@pytest.mark.django_db
def test_post_battle_fatal_injury_stops_further_injuries(
    client, user, list_with_campaign, make_list_fighter
):
    client.force_login(user)
    fighter = make_list_fighter(list_with_campaign, "Doomed")
    fatal = ContentInjury.objects.create(
        name="Critical", phase=ContentInjuryDefaultOutcome.DEAD
    )
    sprain = ContentInjury.objects.create(
        name="Sprain", phase=ContentInjuryDefaultOutcome.RECOVERY
    )

    resp = client.post(
        reverse("core:list-post-battle", args=[list_with_campaign.id]),
        {f"injury_{fighter.pk}": [str(fatal.pk), str(sprain.pk)]},
    )
    assert resp.status_code == 302
    fighter.refresh_from_db()
    assert fighter.is_dead is True
    # Only the fatal injury was recorded; the rest were dropped.
    assert ListFighterInjury.objects.filter(fighter=fighter).count() == 1


@pytest.mark.django_db
def test_post_battle_links_actions_to_selected_battle(
    client, user, list_with_campaign, make_list_fighter
):
    from n23.core.models.battle import Battle

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
    from n23.core.models.battle import Battle

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
def test_post_battle_fatal_injury_links_death_action_to_battle(
    client, user, list_with_campaign, make_list_fighter
):
    from n23.core.models.battle import Battle

    client.force_login(user)
    fighter = make_list_fighter(list_with_campaign, "Doomed")
    injury = ContentInjury.objects.create(
        name="Fatal Blow", phase=ContentInjuryDefaultOutcome.DEAD
    )
    battle = Battle.objects.create(
        campaign=list_with_campaign.campaign, mission="Last Stand", owner=user
    )
    battle.set_participants([list_with_campaign])

    resp = client.post(
        reverse("core:list-post-battle", args=[list_with_campaign.id]),
        {
            "battle": str(battle.pk),
            f"injury_{fighter.pk}": str(injury.pk),
        },
    )
    assert resp.status_code == 302
    fighter.refresh_from_db()
    assert fighter.is_dead is True

    # Both the injury action and the kill handler's "Death:" action link to the
    # battle — no action logged by this submit is left off the timeline.
    actions = CampaignAction.objects.filter(list=list_with_campaign)
    death = actions.filter(description__startswith="Death:").first()
    assert death is not None
    assert death.battle_id == battle.pk
    assert not actions.filter(battle__isnull=True).exists()


@pytest.mark.django_db
def test_post_battle_dead_fighter_has_no_injury_or_state_fields(
    client, user, list_with_campaign, make_list_fighter
):
    client.force_login(user)
    dead = make_list_fighter(list_with_campaign, "Corpse")
    dead.injury_state = ListFighter.DEAD
    dead.save()
    injury = ContentInjury.objects.create(
        name="Sprain", phase=ContentInjuryDefaultOutcome.RECOVERY
    )

    resp = client.get(reverse("core:list-post-battle", args=[list_with_campaign.id]))
    form = resp.context["form"]
    assert f"injury_{dead.pk}" not in form.fields
    assert f"state_{dead.pk}" not in form.fields

    # A POSTed injury for a dead fighter is ignored, not applied — otherwise
    # a RECOVERY-outcome injury would pull the fighter out of DEAD without
    # the resurrect flow (stuck cost_override=0), and a DEAD-outcome injury
    # would re-run the kill handler.
    resp = client.post(
        reverse("core:list-post-battle", args=[list_with_campaign.id]),
        {f"injury_{dead.pk}": str(injury.pk)},
    )
    assert resp.status_code == 302
    dead.refresh_from_db()
    assert dead.injury_state == ListFighter.DEAD
    assert ListFighterInjury.objects.filter(fighter=dead).count() == 0


@pytest.mark.django_db
def test_post_battle_vehicle_state_choices(
    client,
    user,
    content_house,
    list_with_campaign,
    make_content_fighter,
    make_list_fighter,
):
    from n23.models import FighterCategoryChoices

    client.force_login(user)
    vehicle_cf = make_content_fighter(
        type="Truck",
        category=FighterCategoryChoices.VEHICLE,
        house=content_house,
        base_cost=100,
    )
    vehicle = make_list_fighter(list_with_campaign, "Truck", content_fighter=vehicle_cf)
    human = make_list_fighter(list_with_campaign, "Human")

    resp = client.get(reverse("core:list-post-battle", args=[list_with_campaign.id]))
    form = resp.context["form"]

    vehicle_states = [c[0] for c in form.fields[f"state_{vehicle.pk}"].choices]
    human_states = [c[0] for c in form.fields[f"state_{human.pk}"].choices]
    assert ListFighter.IN_REPAIR in vehicle_states
    assert ListFighter.DEAD not in vehicle_states
    assert ListFighter.IN_REPAIR not in human_states
    assert ListFighter.DEAD in human_states


@pytest.mark.django_db
def test_post_battle_rerender_preserves_repeated_selections(
    client, user, list_with_campaign, make_list_fighter
):
    from n23.core.models.campaign import (
        CampaignListResource,
        CampaignResourceType,
    )

    client.force_login(user)
    fighter = make_list_fighter(list_with_campaign, "HurtGuy")
    sprain = ContentInjury.objects.create(
        name="Sprain", phase=ContentInjuryDefaultOutcome.RECOVERY
    )
    scar = ContentInjury.objects.create(
        name="Scar", phase=ContentInjuryDefaultOutcome.NO_CHANGE
    )
    rtype = CampaignResourceType.objects.create(
        campaign=list_with_campaign.campaign, name="Meat", owner=user
    )
    resource = CampaignListResource.objects.create(
        campaign=list_with_campaign.campaign,
        resource_type=rtype,
        list=list_with_campaign,
        amount=5,
        owner=user,
    )

    # A validation error elsewhere re-renders the page: both submitted
    # injuries must come back as two selects, not collapse into one.
    resp = client.post(
        reverse("core:list-post-battle", args=[list_with_campaign.id]),
        {
            f"injury_{fighter.pk}": [str(sprain.pk), str(scar.pk)],
            f"resource_{resource.pk}": "-10",
        },
    )
    assert resp.status_code == 200
    content = resp.content.decode()
    assert content.count(f'name="injury_{fighter.pk}"') == 2
    assert f'value="{sprain.pk}" selected' in content
    assert f'value="{scar.pk}" selected' in content


@pytest.mark.django_db
def test_post_battle_resource_race_rolls_back_and_rerenders(
    client, user, list_with_campaign, make_list_fighter
):
    from unittest import mock

    from n23.core.models.campaign import (
        CampaignListResource,
        CampaignResourceType,
    )

    client.force_login(user)
    make_list_fighter(list_with_campaign, "F1")
    rtype = CampaignResourceType.objects.create(
        campaign=list_with_campaign.campaign, name="Meat", owner=user
    )
    resource = CampaignListResource.objects.create(
        campaign=list_with_campaign.campaign,
        resource_type=rtype,
        list=list_with_campaign,
        amount=5,
        owner=user,
    )

    # Simulate a concurrent change that pushes the resource below zero after
    # form validation: the submit must roll back entirely (credits included)
    # and re-render with a field error, not 500.
    with mock.patch.object(
        CampaignListResource,
        "modify_amount",
        side_effect=ValueError("Cannot reduce Meat below zero."),
    ):
        resp = client.post(
            reverse("core:list-post-battle", args=[list_with_campaign.id]),
            {
                "credits_gained": "10",
                f"resource_{resource.pk}": "-2",
            },
        )
    assert resp.status_code == 200
    assert "Cannot reduce Meat below zero." in resp.content.decode()
    list_with_campaign.refresh_from_db()
    assert list_with_campaign.credits_current == 0


@pytest.mark.django_db
def test_post_battle_capture(
    client, user, list_with_campaign, make_list, make_list_fighter
):
    from n23.core.models.battle import Battle
    from n23.core.models.list import CapturedFighter, List

    client.force_login(user)
    fighter = make_list_fighter(list_with_campaign, "Snatched")
    rivals = make_list(
        "Rivals", status=List.CAMPAIGN_MODE, campaign=list_with_campaign.campaign
    )
    battle = Battle.objects.create(
        campaign=list_with_campaign.campaign, mission="Ambush", owner=user
    )
    battle.set_participants([list_with_campaign])

    resp = client.post(
        reverse("core:list-post-battle", args=[list_with_campaign.id]),
        {
            "battle": str(battle.pk),
            f"captured_by_{fighter.pk}": str(rivals.pk),
        },
    )
    assert resp.status_code == 302

    record = CapturedFighter.objects.get(fighter=fighter)
    assert record.capturing_list == rivals
    fighter.refresh_from_db()
    assert fighter.is_captured is True
    # The capture's campaign log entry lands on the battle timeline.
    action = CampaignAction.objects.get(description__contains="was captured by")
    assert action.battle_id == battle.pk


@pytest.mark.django_db
def test_post_battle_capture_skipped_when_killed_same_submit(
    client, user, list_with_campaign, make_list, make_list_fighter
):
    from n23.core.models.list import CapturedFighter, List

    client.force_login(user)
    fighter = make_list_fighter(list_with_campaign, "Doomed")
    rivals = make_list(
        "Rivals", status=List.CAMPAIGN_MODE, campaign=list_with_campaign.campaign
    )
    fatal = ContentInjury.objects.create(
        name="Critical", phase=ContentInjuryDefaultOutcome.DEAD
    )

    resp = client.post(
        reverse("core:list-post-battle", args=[list_with_campaign.id]),
        {
            f"injury_{fighter.pk}": str(fatal.pk),
            f"captured_by_{fighter.pk}": str(rivals.pk),
        },
    )
    assert resp.status_code == 302
    fighter.refresh_from_db()
    assert fighter.is_dead is True
    # The fatal injury wins; the capture is not applied.
    assert not CapturedFighter.objects.filter(fighter=fighter).exists()


@pytest.mark.django_db
def test_post_battle_state_change(client, user, list_with_campaign, make_list_fighter):
    from n23.core.models.battle import Battle

    client.force_login(user)
    fighter = make_list_fighter(list_with_campaign, "Winded")
    battle = Battle.objects.create(
        campaign=list_with_campaign.campaign, mission="Skirmish", owner=user
    )
    battle.set_participants([list_with_campaign])

    resp = client.post(
        reverse("core:list-post-battle", args=[list_with_campaign.id]),
        {
            "battle": str(battle.pk),
            f"state_{fighter.pk}": ListFighter.RECOVERY,
        },
    )
    assert resp.status_code == 302
    fighter.refresh_from_db()
    assert fighter.injury_state == ListFighter.RECOVERY
    action = CampaignAction.objects.get(description__startswith="State Change:")
    assert action.battle_id == battle.pk


@pytest.mark.django_db
def test_post_battle_state_dead_routes_through_kill(
    client, user, list_with_campaign, make_list_fighter
):
    client.force_login(user)
    fighter = make_list_fighter(list_with_campaign, "Goner")

    resp = client.post(
        reverse("core:list-post-battle", args=[list_with_campaign.id]),
        {f"state_{fighter.pk}": ListFighter.DEAD},
    )
    assert resp.status_code == 302
    fighter.refresh_from_db()
    assert fighter.is_dead is True
    # The kill handler zeroes the fighter's cost.
    assert fighter.cost_int() == 0


@pytest.mark.django_db
def test_post_battle_credits_gained(
    client, user, list_with_campaign, make_list_fighter
):
    from n23.core.models.battle import Battle

    client.force_login(user)
    make_list_fighter(list_with_campaign, "F1")
    battle = Battle.objects.create(
        campaign=list_with_campaign.campaign, mission="Heist", owner=user
    )
    battle.set_participants([list_with_campaign])

    resp = client.post(
        reverse("core:list-post-battle", args=[list_with_campaign.id]),
        {"battle": str(battle.pk), "credits_gained": "55"},
    )
    assert resp.status_code == 302
    list_with_campaign.refresh_from_db()
    assert list_with_campaign.credits_current == 55
    assert list_with_campaign.credits_earned == 55
    action = CampaignAction.objects.get(description__startswith="Added 55¢")
    assert action.battle_id == battle.pk


@pytest.mark.django_db
def test_post_battle_resource_delta(
    client, user, list_with_campaign, make_list_fighter
):
    from n23.core.models.campaign import (
        CampaignListResource,
        CampaignResourceType,
    )

    client.force_login(user)
    make_list_fighter(list_with_campaign, "F1")
    campaign = list_with_campaign.campaign
    rtype = CampaignResourceType.objects.create(
        campaign=campaign, name="Meat", owner=user
    )
    resource = CampaignListResource.objects.create(
        campaign=campaign,
        resource_type=rtype,
        list=list_with_campaign,
        amount=5,
        owner=user,
    )

    resp = client.post(
        reverse("core:list-post-battle", args=[list_with_campaign.id]),
        {f"resource_{resource.pk}": "-2"},
    )
    assert resp.status_code == 302
    resource.refresh_from_db()
    assert resource.amount == 3

    # A loss below zero is rejected up front; nothing is applied.
    resp = client.post(
        reverse("core:list-post-battle", args=[list_with_campaign.id]),
        {f"resource_{resource.pk}": "-10"},
    )
    assert resp.status_code == 200  # re-render with errors
    resource.refresh_from_db()
    assert resource.amount == 3


@pytest.mark.django_db
def test_post_battle_asset_claim(
    client, user, list_with_campaign, make_list, make_list_fighter
):
    from n23.core.models.battle import Battle
    from n23.core.models.campaign import CampaignAsset, CampaignAssetType
    from n23.core.models.list import List

    client.force_login(user)
    make_list_fighter(list_with_campaign, "F1")
    campaign = list_with_campaign.campaign
    rivals = make_list("Rivals", status=List.CAMPAIGN_MODE, campaign=campaign)
    atype = CampaignAssetType.objects.create(
        campaign=campaign,
        name_singular="Territory",
        name_plural="Territories",
        owner=user,
    )
    held = CampaignAsset.objects.create(
        asset_type=atype, name="The Sump", holder=rivals, owner=user
    )
    unclaimed = CampaignAsset.objects.create(
        asset_type=atype, name="Old Ruins", holder=None, owner=user
    )
    battle = Battle.objects.create(campaign=campaign, mission="Turf War", owner=user)
    battle.set_participants([list_with_campaign, rivals])

    resp = client.post(
        reverse("core:list-post-battle", args=[list_with_campaign.id]),
        {
            "battle": str(battle.pk),
            "assets_captured": [str(held.pk), str(unclaimed.pk)],
        },
    )
    assert resp.status_code == 302
    held.refresh_from_db()
    unclaimed.refresh_from_db()
    assert held.holder == list_with_campaign
    assert unclaimed.holder == list_with_campaign
    transfers = CampaignAction.objects.filter(description__contains="Transfer")
    assert transfers.count() == 2
    assert all(a.battle_id == battle.pk for a in transfers)


@pytest.mark.django_db
def test_post_battle_malformed_battle_param_is_ignored(
    client, user, list_with_campaign, make_list_fighter
):
    client.force_login(user)
    make_list_fighter(list_with_campaign, "F1")
    # A non-UUID ?battle= must not 500 the lookup — it's simply ignored.
    resp = client.get(
        reverse("core:list-post-battle", args=[list_with_campaign.id]),
        {"battle": "not-a-uuid"},
    )
    assert resp.status_code == 200
    assert resp.context["form"]["battle"].value() in (None, "")


@pytest.mark.django_db
def test_post_battle_link_visible_to_arbitrator_on_list_page(
    client, user, make_user, campaign, make_list, make_list_fighter
):
    from n23.core.models.list import List

    player = make_user("player_pb_menu", "password")
    plist = make_list(
        "Player Gang", owner=player, status=List.CAMPAIGN_MODE, campaign=campaign
    )
    campaign.lists.add(plist)
    post_battle_url = reverse("core:list-post-battle", args=[plist.id])

    # Arbitrator (campaign owner = user) sees the menu item on a gang they
    # don't own — the view lets them edit, so the link must be discoverable.
    client.force_login(user)
    resp = client.get(reverse("core:list", args=[plist.id]))
    assert resp.status_code == 200
    assert resp.context["is_campaign_arbitrator"] is True
    assert post_battle_url in resp.content.decode()

    # An unrelated viewer is not the arbitrator and does not see it.
    outsider = make_user("outsider_pb_menu", "password")
    plist.public = True
    plist.save()
    client.force_login(outsider)
    resp = client.get(reverse("core:list", args=[plist.id]))
    assert resp.status_code == 200
    assert resp.context["is_campaign_arbitrator"] is False
    assert post_battle_url not in resp.content.decode()


@pytest.mark.django_db
def test_post_battle_arbitrator_can_edit_and_outsider_cannot(
    client, user, make_user, campaign, content_house, make_list, make_list_fighter
):
    from n23.core.models.list import List

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
