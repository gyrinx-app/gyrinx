"""Recorded advancement rolls keep their choices and costs through every step."""

from unittest.mock import patch
from urllib.parse import urlencode

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from n23.core.advancement import resolve_advancement_roll
from n23.core.handlers.fighter.advancement import handle_fighter_advancement
from n23.core.models import ListFighterAdvancement
from n23.core.models.campaign import CampaignAction
from n23.models import FighterCategoryChoices

STAT_RESULTS = [
    (3, ("weapon_skill", "ballistic_skill"), 20),
    (4, ("weapon_skill", "ballistic_skill"), 20),
    (5, ("strength", "toughness"), 30),
    (6, ("strength", "toughness"), 30),
    (7, ("movement", "initiative"), 10),
    (8, ("willpower", "intelligence"), 5),
    (9, ("willpower", "intelligence"), 5),
    (10, ("leadership", "cool"), 10),
    (11, ("leadership", "cool"), 10),
]


@pytest.fixture
def rolled_fighter(list_with_campaign, make_list_fighter):
    return make_list_fighter(
        list_with_campaign,
        "Rolled ganger",
        category_override=FighterCategoryChoices.GANGER,
        xp_current=30,
        xp_total=30,
    )


@pytest.fixture
def roll_action(user, rolled_fighter):
    return CampaignAction.objects.create(
        owner=user,
        user=user,
        campaign=rolled_fighter.list.campaign,
        list=rolled_fighter.list,
        description="Rolling for advancement",
        dice_count=2,
        dice_results=[3, 4],
        dice_total=7,
    )


def flow_url(fighter, step, **params):
    url = reverse(
        f"core:list-fighter-advancement-{step}", args=[fighter.list_id, fighter.id]
    )
    return f"{url}?{urlencode(params)}" if params else url


@pytest.mark.django_db
@pytest.mark.parametrize("total,stats,rating", STAT_RESULTS)
@pytest.mark.parametrize("method", ["roll_auto", "roll_manual"])
def test_roll_offers_both_stats_at_fixed_cost(
    client, user, rolled_fighter, total, stats, rating, method
):
    client.force_login(user)
    dice = [max(1, total - 6), min(6, total - 1)]
    with patch("n23.core.views.fighter.advancements.random.randint", side_effect=dice):
        response = client.post(
            flow_url(rolled_fighter, "dice-choice"),
            {"roll_action": method, "d6_1": dice[0], "d6_2": dice[1]},
            follow=True,
        )
    assert response.status_code == 200
    action = response.context["campaign_action"]
    assert action.dice_total == total
    form = response.context["form"]
    assert list(dict(form.fields["advancement_choice"].choices)) == [
        f"stat_{stat}" for stat in stats
    ]
    assert form["advancement_choice"].value() == ""
    assert form["xp_cost"].value() == 6
    assert form["cost_increase"].value() == rating
    assert form.fields["xp_cost"].disabled
    assert form.fields["cost_increase"].disabled
    html = response.content.decode()
    assert 'type="radio"' in html
    assert 'id="advancement-configs"' not in html


@pytest.mark.django_db
@pytest.mark.parametrize("total,stats,rating", STAT_RESULTS)
@pytest.mark.parametrize("choice_index", [0, 1])
def test_either_rolled_stat_saves_fixed_costs(
    client, user, rolled_fighter, roll_action, total, stats, rating, choice_index
):
    dice = [max(1, total - 6), min(6, total - 1)]
    roll_action.dice_results = dice
    roll_action.dice_total = total
    roll_action.save()
    client.force_login(user)
    stat = stats[choice_index]
    response = client.post(
        flow_url(rolled_fighter, "type", campaign_action_id=roll_action.id),
        {"advancement_choice": f"stat_{stat}", "xp_cost": 0, "cost_increase": 999},
    )
    assert response.status_code == 302
    confirm_url = response.url
    response = client.get(confirm_url)
    assert response.status_code == 200
    assert response.context["details"]["xp_cost"] == 6
    assert response.context["details"]["cost_increase"] == rating
    response = client.post(confirm_url)
    assert response.status_code == 302
    rolled_fighter.refresh_from_db()
    advancement = rolled_fighter.advancements.get()
    assert rolled_fighter.xp_current == 24
    assert advancement.stat_increased == stat
    assert advancement.xp_cost == 6
    assert advancement.cost_increase == rating
    assert advancement.campaign_action_id == roll_action.id
    # A second submission must neither spend XP nor add another advancement.
    client.post(confirm_url)
    rolled_fighter.refresh_from_db()
    assert rolled_fighter.xp_current == 24
    assert rolled_fighter.advancements.count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize(
    "choice", ["", "stat_strength", "skill_primary_random", "other"]
)
def test_rolled_form_rejects_missing_or_unrelated_choice(
    client, user, rolled_fighter, roll_action, choice
):
    client.force_login(user)
    response = client.post(
        flow_url(rolled_fighter, "type", campaign_action_id=roll_action.id),
        {"advancement_choice": choice, "xp_cost": 0, "cost_increase": 0},
    )
    assert response.status_code == 200
    assert "advancement_choice" in response.context["form"].errors
    assert not rolled_fighter.advancements.exists()


@pytest.mark.django_db
def test_direct_confirmation_uses_recorded_costs(
    client, user, rolled_fighter, roll_action
):
    client.force_login(user)
    url = flow_url(
        rolled_fighter,
        "confirm",
        campaign_action_id=roll_action.id,
        advancement_choice="stat_initiative",
        xp_cost=0,
        cost_increase=999,
    )
    response = client.get(url)
    assert response.context["details"]["xp_cost"] == 6
    assert response.context["details"]["cost_increase"] == 10
    client.post(url)
    advancement = rolled_fighter.advancements.get()
    assert (advancement.xp_cost, advancement.cost_increase) == (6, 10)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "step,choice", [("confirm", "stat_strength"), ("select", "skill_primary_random")]
)
def test_direct_urls_reject_choices_outside_roll(
    client, user, rolled_fighter, roll_action, step, choice
):
    client.force_login(user)
    response = client.post(
        flow_url(
            rolled_fighter,
            step,
            campaign_action_id=roll_action.id,
            advancement_choice=choice,
            xp_cost=0,
            cost_increase=0,
        )
    )
    assert response.status_code == 302
    assert not rolled_fighter.advancements.exists()


@pytest.mark.django_db
def test_handler_validates_roll_and_derives_costs(user, rolled_fighter, roll_action):
    kwargs = dict(
        user=user,
        fighter=rolled_fighter,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_STAT,
        advancement_choice="stat_movement",
        stat_increased="movement",
        xp_cost=0,
        cost_increase=999,
        campaign_action_id=roll_action.id,
    )
    with pytest.raises(ValidationError, match="selected stat"):
        handle_fighter_advancement(**{**kwargs, "stat_increased": "strength"})
    with pytest.raises(ValidationError, match="for this roll"):
        handle_fighter_advancement(**{**kwargs, "advancement_choice": "stat_strength"})
    result = handle_fighter_advancement(**kwargs)
    assert result.advancement.xp_cost == 6
    assert result.cost_increase == 10


@pytest.mark.django_db
def test_recorded_roll_requires_six_xp(client, user, rolled_fighter, roll_action):
    rolled_fighter.xp_current = 5
    rolled_fighter.save()
    client.force_login(user)
    response = client.post(
        flow_url(rolled_fighter, "type", campaign_action_id=roll_action.id),
        {"advancement_choice": "stat_movement", "xp_cost": 0, "cost_increase": 0},
    )
    assert response.context["form"].non_field_errors()
    with pytest.raises(ValidationError, match="insufficient XP"):
        handle_fighter_advancement(
            user=user,
            fighter=rolled_fighter,
            advancement_type=ListFighterAdvancement.ADVANCEMENT_STAT,
            advancement_choice="stat_movement",
            stat_increased="movement",
            xp_cost=0,
            cost_increase=0,
            campaign_action_id=roll_action.id,
        )
    assert not rolled_fighter.advancements.exists()


@pytest.mark.django_db
def test_roll_from_another_gang_is_rejected(
    client, user, rolled_fighter, roll_action, make_list
):
    roll_action.list = make_list("Other gang", campaign=rolled_fighter.list.campaign)
    roll_action.save()
    client.force_login(user)
    assert (
        client.get(
            flow_url(rolled_fighter, "type", campaign_action_id=roll_action.id)
        ).status_code
        == 404
    )
    with pytest.raises(ValidationError, match="not found"):
        handle_fighter_advancement(
            user=user,
            fighter=rolled_fighter,
            advancement_type=ListFighterAdvancement.ADVANCEMENT_STAT,
            advancement_choice="stat_movement",
            stat_increased="movement",
            xp_cost=6,
            cost_increase=10,
            campaign_action_id=roll_action.id,
        )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "dice_count,dice_results", [(1, [3, 4]), (2, [3]), (2, [7, 0]), (2, [2, 4])]
)
def test_malformed_roll_is_rejected(
    client, user, rolled_fighter, roll_action, dice_count, dice_results
):
    roll_action.dice_count = dice_count
    roll_action.dice_results = dice_results
    roll_action.save()
    client.force_login(user)
    response = client.get(
        flow_url(rolled_fighter, "type", campaign_action_id=roll_action.id), follow=True
    )
    assert response.status_code == 200
    assert "valid 2D6 advancement roll" in response.content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "category,expected_status", [("EXOTIC_BEAST", 200), ("SPECIALIST", 302)]
)
def test_recorded_roll_checks_fighter_category(
    client, user, rolled_fighter, roll_action, category, expected_status
):
    rolled_fighter.category_override = category
    rolled_fighter.save()
    client.force_login(user)
    response = client.get(
        flow_url(rolled_fighter, "type", campaign_action_id=roll_action.id)
    )
    assert response.status_code == expected_status
    if expected_status == 200:
        assert dict(response.context["form"].fields["advancement_choice"].choices) == {
            "stat_movement": "Movement",
            "stat_initiative": "Initiative",
        }


@pytest.mark.django_db
@pytest.mark.parametrize("total", [2, 12])
@pytest.mark.parametrize("method", ["roll_auto", "roll_manual"])
def test_promotion_roll_keeps_six_xp_through_skill_selection(
    client, user, rolled_fighter, default_promotions, make_content_skill, total, method
):
    skill = make_content_skill("Iron Jaw", category="Combat")
    rolled_fighter.content_fighter.primary_skill_categories.add(skill.category)
    client.force_login(user)
    dice = [1, 1] if total == 2 else [6, 6]
    with patch("n23.core.views.fighter.advancements.random.randint", side_effect=dice):
        response = client.post(
            flow_url(rolled_fighter, "dice-choice"),
            {"roll_action": method, "d6_1": dice[0], "d6_2": dice[1]},
            follow=True,
        )
    path = default_promotions[("GANGER", "SPECIALIST")]
    type_url = response.redirect_chain[-1][0]
    response = client.post(
        type_url,
        {
            "advancement_choice": f"promotion_{path.id}",
            "xp_cost": 0,
            "cost_increase": 0,
        },
    )
    assert response.status_code == 302
    response = client.post(response.url, {"category": skill.category_id})
    assert response.status_code == 302
    advancement = rolled_fighter.advancements.get()
    rolled_fighter.refresh_from_db()
    assert advancement.promotion_path == path
    assert advancement.skill == skill
    assert (advancement.xp_cost, advancement.cost_increase) == (6, 20)
    assert rolled_fighter.xp_current == 24
    assert rolled_fighter.get_category() == FighterCategoryChoices.SPECIALIST


@pytest.mark.django_db
def test_missing_promotion_does_not_fall_back_to_willpower(rolled_fighter):
    with pytest.raises(ValidationError, match="No promotion"):
        resolve_advancement_roll(12, rolled_fighter)


@pytest.mark.django_db
def test_manual_advancement_keeps_custom_choice_and_cost(client, user, rolled_fighter):
    client.force_login(user)
    response = client.post(
        flow_url(rolled_fighter, "type"),
        {
            "advancement_choice": "stat_strength",
            "xp_cost": 4,
            "cost_increase": 15,
        },
    )
    client.post(response.url)
    advancement = rolled_fighter.advancements.get()
    assert (advancement.xp_cost, advancement.cost_increase) == (4, 15)
