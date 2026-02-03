from urllib.parse import urlencode
from django.urls import reverse
import pytest

from gyrinx.models import FighterCategoryChoices


@pytest.mark.django_db
def test_fighter_advancement_flow_promote_specialist_to_champion(
    client,
    user,
    make_content_house,
    make_content_fighter,
    make_content_skills_in_category,
    make_list,
    make_list_fighter,
):
    """Test the flow of creating a champion promotion advancement for a specialist."""
    # Setup content house, skills, categories, and fighter eligible for champion promotion
    content_house = make_content_house("Test House")
    _, cunning_category = make_content_skills_in_category(["Infiltrate"], "Cunning")
    _, shooting_category = make_content_skills_in_category(["Overwatch"], "Shooting")

    specialist_content_fighter = make_content_fighter(
        type="Specialist",
        category=FighterCategoryChoices.SPECIALIST,
        house=content_house,
        base_cost=50,
    )

    specialist_content_fighter.primary_skill_categories.set([cunning_category])
    specialist_content_fighter.secondary_skill_categories.set([shooting_category])
    specialist_content_fighter.save()

    # Create a list and add an instance of the specialist fighter
    gang_list = make_list(name="Champion promotion test list", owner=user)
    specialist_fighter = make_list_fighter(
        gang_list,
        "Test Specialist Fighter",
        content_fighter=specialist_content_fighter,
        xp_current=20,  # Ensure enough XP for promotion
    )

    # Log in the user
    client.force_login(user)

    # 1: Get the URL for adding a champion promotion advancement
    url = reverse(
        "core:list-fighter-advancement-type",
        args=[gang_list.id, specialist_fighter.id],
    )
    response = client.get(url)
    assert response.status_code == 200

    # 2: Post data to create the champion promotion advancement
    post_data = {
        "advancement_choice": "skill_promote_champion",
        "xp_cost": 12,
        "cost_increase": 40,
    }
    response = client.post(url, post_data, follow=True)

    # Should redirect to the skill choice page
    assert response.status_code == 200
    assert "Choose Primary Skill" in response.content.decode()

    # Parse the form and pick the first available skill category
    form = response.context["form"]
    category_field = form.fields.get("category")
    assert category_field is not None, "Category field not found in form."
    available_category_ids = list(category_field.queryset.values_list("id", flat=True))
    assert available_category_ids, "No skill categories available to choose from."
    skill_category_id = available_category_ids[0]

    # 3: Post the skill category choice to the correct URL (skill selection), including advancement params as query string
    advancement_params = {
        "advancement_choice": "skill_promote_champion",
        "xp_cost": 12,
        "cost_increase": 40,
    }
    skill_select_url = (
        f"{response.request['PATH_INFO']}?{urlencode(advancement_params)}"
    )
    post_data = {"category": skill_category_id}
    response = client.post(skill_select_url, post_data, follow=True)

    # Should successfully redirect to the gang list view
    assert response.status_code == 200

    # Directly test advancement creation and fighter promotion
    specialist_fighter.refresh_from_db()
    advancement_created = specialist_fighter.advancements.filter(
        advancement_choice="skill_promote_champion"
    ).exists()
    assert advancement_created, "Champion promotion advancement was not created."
    assert specialist_fighter.get_category() == FighterCategoryChoices.CHAMPION, (
        "Fighter was not promoted to Champion."
    )


@pytest.mark.django_db
def test_fighter_advancement_flow_promote_specialist_champion(
    client,
    user,
    make_content_house,
    make_content_fighter,
    make_content_skills_in_category,
    make_list,
    make_list_fighter,
):
    """
    Test the flow of creating a champion promotion advancement for a specialist
    previously promoted from a ganger.
    """
    # Setup content house, skills, categories, and fighter eligible for champion promotion
    content_house = make_content_house("Test House")
    _, cunning_category = make_content_skills_in_category(["Infiltrate"], "Cunning")
    _, shooting_category = make_content_skills_in_category(["Overwatch"], "Shooting")

    ganger_content_fighter = make_content_fighter(
        type="Ganger",
        category=FighterCategoryChoices.GANGER,
        house=content_house,
        base_cost=30,
    )

    ganger_content_fighter.primary_skill_categories.set([cunning_category])
    ganger_content_fighter.secondary_skill_categories.set([shooting_category])

    # Create a list and add an instance of the ganger fighter
    gang_list = make_list(name="Champion promotion test list", owner=user)
    ganger_fighter = make_list_fighter(
        gang_list,
        "Test Ganger Fighter",
        content_fighter=ganger_content_fighter,
        xp_current=30,  # Ensure enough XP for two promotions
    )

    # Apply the specialist promotion advancement first
    specialist_advancement = ganger_fighter.advancements.create(
        advancement_choice="skill_promote_specialist",
        xp_cost=8,
        cost_increase=20,
    )
    specialist_advancement.apply_advancement()

    # Check this advancement was applied
    ganger_fighter.refresh_from_db()
    assert ganger_fighter.get_category() == FighterCategoryChoices.SPECIALIST, (
        "Fighter was not promoted to Specialist."
    )

    # Log in the user
    client.force_login(user)

    # 1: Get the URL for adding a champion promotion advancement
    url = reverse(
        "core:list-fighter-advancement-type",
        args=[gang_list.id, ganger_fighter.id],
    )
    response = client.get(url)
    assert response.status_code == 200

    # 2: Post data to create the champion promotion advancement
    post_data = {
        "advancement_choice": "skill_promote_champion",
        "xp_cost": 12,
        "cost_increase": 40,
    }
    response = client.post(url, post_data, follow=True)

    # Should redirect to the skill choice page
    assert response.status_code == 200
    assert "Choose Primary Skill" in response.content.decode()

    # Parse the form and pick the first available skill category
    form = response.context["form"]
    category_field = form.fields.get("category")
    assert category_field is not None, "Category field not found in form."
    available_category_ids = list(category_field.queryset.values_list("id", flat=True))
    assert available_category_ids, "No skill categories available to choose from."
    skill_category_id = available_category_ids[0]

    # 3: Post the skill category choice to the correct URL (skill selection), including advancement params as query string
    advancement_params = {
        "advancement_choice": "skill_promote_champion",
        "xp_cost": 12,
        "cost_increase": 40,
    }
    skill_select_url = (
        f"{response.request['PATH_INFO']}?{urlencode(advancement_params)}"
    )
    post_data = {"category": skill_category_id}
    response = client.post(skill_select_url, post_data, follow=True)

    # Should successfully redirect to the gang list view
    assert response.status_code == 200

    # Directly test advancement creation and fighter promotion
    ganger_fighter.refresh_from_db()
    advancement_created = ganger_fighter.advancements.filter(
        advancement_choice="skill_promote_champion"
    ).exists()
    assert advancement_created, "Champion promotion advancement was not created."
    assert ganger_fighter.get_category() == FighterCategoryChoices.CHAMPION, (
        "Fighter was not promoted to Champion."
    )
