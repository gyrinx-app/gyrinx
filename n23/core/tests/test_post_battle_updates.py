from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from bs4 import BeautifulSoup
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
def test_fatal_injury_does_not_report_an_already_completed_death(
    user, list_with_campaign, make_list_fighter
):
    from n23.core.handlers.fighter.kill import handle_fighter_kill
    from n23.core.models.action import ListAction

    fighter = make_list_fighter(list_with_campaign, "F1")
    stale_fighter = ListFighter.objects.get(pk=fighter.pk)
    injury = ContentInjury.objects.create(
        name="Critical", phase=ContentInjuryDefaultOutcome.DEAD
    )
    handle_fighter_kill(user=user, lst=list_with_campaign, fighter=fighter)
    action_count = ListAction.objects.filter(list=list_with_campaign).count()

    result = handle_fighter_add_injury(user=user, fighter=stale_fighter, injury=injury)

    assert result.killed is False
    assert result.outcome_state == ListFighter.DEAD
    assert result.fighter.injury_state == ListFighter.DEAD
    assert ListFighterInjury.objects.filter(fighter=fighter).count() == 1
    assert ListAction.objects.filter(list=list_with_campaign).count() == action_count


@pytest.mark.django_db
@pytest.mark.parametrize("death_source", ["injury", "state"])
def test_post_battle_does_not_report_death_completed_by_another_request(
    rf,
    user,
    list_with_campaign,
    make_list,
    make_list_fighter,
    monkeypatch,
    death_source,
):
    from n23.core.handlers.fighter import injury as injury_handler
    from n23.core.handlers.fighter.kill import handle_fighter_kill
    from n23.core.models.list import CapturedFighter, List
    from n23.core.views.list import post_battle

    fighter = make_list_fighter(list_with_campaign, "Doomed")
    rivals = make_list(
        "Rivals", status=List.CAMPAIGN_MODE, campaign=list_with_campaign.campaign
    )
    data = {f"captured_by_{fighter.pk}": rivals}
    if death_source == "injury":
        fatal = ContentInjury.objects.create(
            name="Critical", phase=ContentInjuryDefaultOutcome.DEAD
        )
        recovery = ContentInjury.objects.create(
            name="Spinal Injury", phase=ContentInjuryDefaultOutcome.RECOVERY
        )
        data[f"injury_{fighter.pk}"] = [fatal, recovery]
        data[f"state_{fighter.pk}"] = ListFighter.ACTIVE
        target = injury_handler
    else:
        data[f"state_{fighter.pk}"] = ListFighter.DEAD
        target = post_battle

    def death_completed_before_lock(**kwargs):
        # Another request finishes after the form loads the live fighter.
        handle_fighter_kill(
            user=user,
            lst=List.objects.get(pk=list_with_campaign.pk),
            fighter=ListFighter.objects.get(pk=fighter.pk),
        )
        return handle_fighter_kill(**kwargs)

    monkeypatch.setattr(target, "handle_fighter_kill", death_completed_before_lock)
    log_event = Mock()
    monkeypatch.setattr(post_battle, "log_event", log_event)
    request = rf.post("/")
    request.user = user

    summary = post_battle._apply(
        request, list_with_campaign, [fighter], [], SimpleNamespace(cleaned_data=data)
    )

    fighter.refresh_from_db()
    assert fighter.is_dead
    assert summary.kills == 0
    assert summary.killed_names == []
    assert summary.states == 0
    assert summary.injuries == (1 if death_source == "injury" else 0)
    assert summary.capture_skipped_names == [fighter.name]
    assert not CapturedFighter.objects.filter(fighter=fighter).exists()
    assert ListFighterInjury.objects.filter(fighter=fighter).count() == summary.injuries
    assert all(call.kwargs["action"] != "killed" for call in log_event.call_args_list)
    assert (
        CampaignAction.objects.filter(
            list=list_with_campaign, description__contains="was killed"
        ).count()
        == 1
    )


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
@pytest.mark.parametrize("payload", ["nonfatal_first", "state_override", "xp"])
def test_post_battle_skips_stale_updates_to_newly_dead_fighter(
    rf, user, list_with_campaign, content_fighter, payload, monkeypatch
):
    from n23.core.handlers.fighter.kill import handle_fighter_kill
    from n23.core.models.action import ListActionType
    from n23.core.tests.test_balance_sheet import assert_reconciles, fresh, hire_fighter
    from n23.core.views.list import post_battle

    lst = list_with_campaign
    lst.create_action(
        user=user,
        action_type=ListActionType.UPDATE_CREDITS,
        credits_before=0,
        credits_delta=1000,
        description="Starting credits",
    )
    lst.apply_credit_delta(1000)
    fighter = hire_fighter(user, lst, content_fighter)
    stale_fighter = fresh(fighter)
    data = {}
    if payload == "nonfatal_first":
        recovery = ContentInjury.objects.create(
            name="Spinal Injury", phase=ContentInjuryDefaultOutcome.RECOVERY
        )
        fatal = ContentInjury.objects.create(
            name="Critical", phase=ContentInjuryDefaultOutcome.DEAD
        )
        data[f"injury_{fighter.pk}"] = [recovery, fatal]
    elif payload == "state_override":
        data[f"state_{fighter.pk}"] = ListFighter.RECOVERY
    else:
        data[f"xp_{fighter.pk}"] = 3
    handle_fighter_kill(user=user, lst=fresh(lst), fighter=fresh(fighter))
    action_count = lst.actions.count()
    log_event = Mock()
    monkeypatch.setattr(post_battle, "log_event", log_event)
    request = rf.post("/")
    request.user = user

    summary = post_battle._apply(
        request, lst, [stale_fighter], [], SimpleNamespace(cleaned_data=data)
    )

    assert not summary.changed
    assert summary.kills == 0
    log_event.assert_not_called()
    assert fresh(fighter).is_dead
    assert fresh(fighter).cost_override == 0
    assert fresh(fighter).rating_current == fresh(lst).rating_current == 0
    assert fresh(fighter).xp_current == stale_fighter.xp_current
    assert ListFighterInjury.objects.filter(fighter=fighter).count() == 0
    assert lst.actions.count() == action_count
    assert_reconciles(lst)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("two_deaths", [False, True])
def test_post_battle_credits_and_deaths_race_with_confirmation(
    rf,
    user,
    list_with_campaign,
    content_fighter,
    stash_fighter_type,
    make_list_fighter,
    make_equipment,
    two_deaths,
):
    import threading

    from django.db import connection

    from n23.core.handlers.fighter.kill import handle_fighter_kill
    from n23.core.models.action import ListActionType
    from n23.core.tests.test_balance_sheet import (
        assert_reconciles,
        buy_equipment,
        fresh,
        hire_fighter,
    )
    from n23.core.tests.test_task_chaos_concurrency import _run_concurrently
    from n23.core.views.list import post_battle

    lst = list_with_campaign
    lst.create_action(
        user=user,
        action_type=ListActionType.UPDATE_CREDITS,
        credits_before=0,
        credits_delta=1000,
        description="Starting credits",
    )
    lst.apply_credit_delta(1000)
    fighters = [
        hire_fighter(user, lst, content_fighter, name=f"F{i}") for i in range(2)
    ]
    stash = make_list_fighter(lst, "Stash", content_fighter=stash_fighter_type)
    equipment = make_equipment("Race Lasgun", cost=15)
    for fighter in fighters:
        buy_equipment(user, lst, fighter, equipment)
    credits_before = fresh(lst).credits_current
    live_rating = fresh(fighters[0]).rating_current
    raced_fighter = fighters[1]
    data = {"credits_gained": 25, f"state_{raced_fighter.pk}": ListFighter.DEAD}
    if two_deaths:
        data[f"state_{fighters[0].pk}"] = ListFighter.DEAD
    confirmation_locked = threading.Event()
    bulk_lock_attempted = threading.Event()
    roles = iter(["confirm", "bulk"])
    summaries = []

    def fighter_lock_sql(sql):
        return "FOR NO KEY UPDATE" in sql and f'"{ListFighter._meta.db_table}"' in sql

    def hold_confirmation_lock(execute, sql, params, many, context):
        result = execute(sql, params, many, context)
        if fighter_lock_sql(sql) and not confirmation_locked.is_set():
            confirmation_locked.set()
            assert bulk_lock_attempted.wait(timeout=5)
        return result

    def announce_bulk_lock(execute, sql, params, many, context):
        if fighter_lock_sql(sql):
            bulk_lock_attempted.set()
        return execute(sql, params, many, context)

    def confirm_or_submit():
        if next(roles) == "confirm":
            with connection.execute_wrapper(hold_confirmation_lock):
                handle_fighter_kill(
                    user=user, lst=fresh(lst), fighter=fresh(raced_fighter)
                )
        else:
            stale_fighters = [fresh(fighter) for fighter in fighters]
            assert confirmation_locked.wait(timeout=5)
            request = rf.post("/")
            request.user = user
            with connection.execute_wrapper(announce_bulk_lock):
                summaries.append(
                    post_battle._apply(
                        request,
                        fresh(lst),
                        stale_fighters,
                        [],
                        SimpleNamespace(cleaned_data=data),
                    )
                )

    _run_concurrently(confirm_or_submit)

    deaths = 2 if two_deaths else 1
    assert summaries[0].kills == deaths - 1
    assert summaries[0].credits == 25
    assert fresh(lst).credits_current == credits_before + 25
    assert fresh(lst).rating_current == (0 if two_deaths else live_rating)
    assert fresh(stash).rating_current == fresh(lst).stash_current == deaths * 15
    assert stash.listfighterequipmentassignment_set.count() == deaths
    assert (
        CampaignAction.objects.filter(
            list=lst, description__startswith="Death:"
        ).count()
        == deaths
    )
    assert_reconciles(lst)


@pytest.mark.django_db
def test_post_battle_existing_dead_fighter_can_still_gain_xp(
    client, user, list_with_campaign, make_list_fighter
):
    fighter = make_list_fighter(list_with_campaign, "Corpse", cost_override=0)
    fighter.injury_state = ListFighter.DEAD
    fighter.save()
    client.force_login(user)

    response = client.post(
        reverse("core:list-post-battle", args=[list_with_campaign.pk]),
        {f"xp_{fighter.pk}": "3"},
    )

    assert response.status_code == 302
    fighter.refresh_from_db()
    assert fighter.is_dead
    assert fighter.xp_current == 3
    assert fighter.cost_int() == fighter.rating_current == 0


@pytest.mark.django_db
@pytest.mark.parametrize("dead_before_get", [False, True])
def test_post_battle_round_trips_state_to_skip_stale_browser_updates(
    client,
    user,
    list_with_campaign,
    content_fighter,
    dead_before_get,
):
    from n23.core.handlers.fighter.kill import handle_fighter_kill
    from n23.core.models.action import ListActionType
    from n23.core.tests.test_balance_sheet import assert_reconciles, fresh, hire_fighter

    lst = list_with_campaign
    lst.create_action(
        user=user,
        action_type=ListActionType.UPDATE_CREDITS,
        credits_before=0,
        credits_delta=1000,
        description="Starting credits",
    )
    lst.apply_credit_delta(1000)
    fighter = hire_fighter(user, lst, content_fighter)
    counter = ContentCounter.objects.create(name="Race counter")
    counter.restricted_to_fighters.add(content_fighter)
    if dead_before_get:
        handle_fighter_kill(user=user, lst=fresh(lst), fighter=fresh(fighter))
    client.force_login(user)
    url = reverse("core:list-post-battle", args=[lst.pk])
    response = client.get(url)
    assert response.status_code == 200
    hidden = BeautifulSoup(response.content, "html.parser").select(
        'input[type="hidden"][name]'
    )
    data = {field["name"]: field.get("value", "") for field in hidden}
    assert data[f"initial_state_{fighter.pk}"] == (
        ListFighter.DEAD if dead_before_get else ListFighter.ACTIVE
    )
    if not dead_before_get:
        handle_fighter_kill(user=user, lst=fresh(lst), fighter=fresh(fighter))
    action_count = lst.actions.count()
    data[f"xp_{fighter.pk}"] = "3"
    data[f"counter_{fighter.pk}_{counter.pk}"] = "2"

    response = client.post(url, data)

    assert response.status_code == 302
    assert fresh(fighter).is_dead
    assert fresh(fighter).xp_current == (3 if dead_before_get else 0)
    value = ListFighterCounter.objects.filter(fighter=fighter, counter=counter).first()
    assert (value.value if value else 0) == (2 if dead_before_get else 0)
    if not dead_before_get:
        assert lst.actions.count() == action_count
    assert fresh(fighter).rating_current == fresh(lst).rating_current == 0
    assert_reconciles(lst)


@pytest.mark.django_db
def test_post_battle_locked_roster_reload_has_flat_query_growth(
    rf, user, list_with_campaign, content_fighter, make_list_fighter
):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from n23.core.views.list import post_battle

    counter = ContentCounter.objects.create(name="Race counter")
    counter.restricted_to_fighters.add(content_fighter)
    make_list_fighter(list_with_campaign, "F1", content_fighter=content_fighter)
    request = rf.post("/")
    request.user = user

    def measure():
        fighters = post_battle._post_battle_fighters(list_with_campaign)
        with CaptureQueriesContext(connection) as queries:
            summary = post_battle._apply(
                request,
                list_with_campaign,
                fighters,
                [],
                SimpleNamespace(cleaned_data={}),
            )
        assert not summary.changed
        return len(queries)

    baseline = measure()
    for i in range(2, 7):
        make_list_fighter(list_with_campaign, f"F{i}", content_fighter=content_fighter)
    assert measure() <= baseline


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
def test_post_battle_resource_delta_can_go_negative(
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
        campaign=campaign, name="Heat", can_go_negative=True, owner=user
    )
    resource = CampaignListResource.objects.create(
        campaign=campaign,
        resource_type=rtype,
        list=list_with_campaign,
        amount=2,
        owner=user,
    )

    resp = client.post(
        reverse("core:list-post-battle", args=[list_with_campaign.id]),
        {f"resource_{resource.pk}": "-5"},
    )
    assert resp.status_code == 302
    resource.refresh_from_db()
    assert resource.amount == -3


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

    # Arbitrator (campaign owner = user) sees the button on a gang they
    # don't own — the view lets them edit, so the link must be discoverable.
    client.force_login(user)
    resp = client.get(reverse("core:list", args=[plist.id]))
    assert resp.status_code == 200
    assert post_battle_url in resp.content.decode()

    # An unrelated viewer is not the arbitrator and does not see it.
    outsider = make_user("outsider_pb_menu", "password")
    plist.public = True
    plist.save()
    client.force_login(outsider)
    resp = client.get(reverse("core:list", args=[plist.id]))
    assert resp.status_code == 200
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


@pytest.mark.django_db
def test_post_battle_button_on_gang_page_once_and_not_in_dropdown(
    client, user, list_with_campaign
):
    # The owner of a campaign-mode gang gets the sequence as a primary button in
    # the action bar. The dropdown entry is gone and the common header (which the
    # gang page also includes) does not repeat it, so the URL appears exactly once.
    client.force_login(user)
    resp = client.get(reverse("core:list", args=[list_with_campaign.id]))
    assert resp.status_code == 200
    html = resp.content.decode()
    post_battle_url = reverse("core:list-post-battle", args=[list_with_campaign.id])
    links = BeautifulSoup(html, "html.parser").find_all("a", href=post_battle_url)
    assert len(links) == 1
    assert "Post-battle updates" in links[0].get_text(" ", strip=True)


@pytest.mark.django_db
def test_post_battle_button_absent_for_list_building_gang(client, user, make_list):
    # Not in campaign mode: neither the gang page nor a sub-page offers the sequence.
    lst = make_list("Builder")
    client.force_login(user)
    post_battle_url = reverse("core:list-post-battle", args=[lst.id])
    for name in ("core:list", "core:list-about"):
        resp = client.get(reverse(name, args=[lst.id]))
        assert resp.status_code == 200
        assert post_battle_url not in resp.content.decode()


@pytest.mark.django_db
def test_post_battle_icon_in_common_header_on_sub_pages(
    client, user, make_user, campaign, make_list
):
    from n23.core.models.list import List

    player = make_user("player_pb_header", "password")
    plist = make_list(
        "Player Gang",
        owner=player,
        status=List.CAMPAIGN_MODE,
        campaign=campaign,
        public=True,
    )
    campaign.lists.add(plist)
    post_battle_url = reverse("core:list-post-battle", args=[plist.id])
    about_url = reverse("core:list-about", args=[plist.id])
    # The header renders the icon-only button with a visually-hidden label.
    icon_button = f'href="{post_battle_url}"'
    hidden_label = '<span class="visually-hidden">Post-battle updates</span>'

    # Owner sees it on a sub-page.
    client.force_login(player)
    html = client.get(about_url).content.decode()
    assert icon_button in html
    assert hidden_label in html
    assert 'data-bs-title="Post-battle updates"' in html

    # The campaign arbitrator (campaign owner = user) sees it on a gang they
    # do not own, matching what the post-battle view lets them do.
    client.force_login(user)
    html = client.get(about_url).content.decode()
    assert icon_button in html
    assert hidden_label in html

    # An unrelated viewer of the public gang does not.
    outsider = make_user("outsider_pb_header", "password")
    client.force_login(outsider)
    html = client.get(about_url).content.decode()
    assert post_battle_url not in html

    # The post-battle page itself does not offer a link to itself in the header.
    client.force_login(player)
    html = client.get(post_battle_url).content.decode()
    assert hidden_label not in html


@pytest.mark.django_db
def test_post_battle_button_visible_to_shared_campaign_admin(
    client, make_user, campaign, make_list
):
    """A shared campaign admin can open the post-battle view, so both the
    gang-page button and the sub-page header icon show for them."""
    from n23.core.models.list import List

    player = make_user("player_pb_shared_admin", "password")
    shared_admin = make_user("shared_admin_pb", "password")
    campaign.admins.add(shared_admin)
    plist = make_list(
        "Player Gang",
        owner=player,
        status=List.CAMPAIGN_MODE,
        campaign=campaign,
        public=True,
    )
    campaign.lists.add(plist)
    post_battle_url = reverse("core:list-post-battle", args=[plist.id])

    client.force_login(shared_admin)
    # The link must lead somewhere the shared admin may go.
    assert client.get(post_battle_url).status_code == 200
    html = client.get(reverse("core:list", args=[plist.id])).content.decode()
    links = BeautifulSoup(html, "html.parser").find_all("a", href=post_battle_url)
    assert len(links) == 1
    assert "Post-battle updates" in links[0].get_text(" ", strip=True)

    html = client.get(reverse("core:list-about", args=[plist.id])).content.decode()
    link = BeautifulSoup(html, "html.parser").find("a", href=post_battle_url)
    assert link is not None
    assert "Post-battle updates" in link.get_text(" ", strip=True)
