"""Tests for the CrewTemplate model and CRUD views."""

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from gyrinx.content.models import ContentFighter, ContentHouse
from gyrinx.core.models import CrewTemplate, List, ListFighter


@pytest.fixture
def authenticated_client():
    """Create an authenticated client."""
    client = Client()
    user = User.objects.create_user(username="testuser", password="testpass")
    client.force_login(user)
    return client, user


@pytest.fixture
def test_list_with_fighters(authenticated_client):
    """Create a test list with active and inactive fighters."""
    client, user = authenticated_client

    house = ContentHouse.objects.create(name="Test House")
    test_list = List.objects.create(
        name="Test List",
        owner=user,
        content_house=house,
    )

    content_fighter = ContentFighter.objects.create(
        house=house,
        type="Fighter",
        category="GANGER",
        base_cost=50,
    )

    # Create active fighters
    active_fighter_1 = ListFighter.objects.create(
        name="Active Fighter 1",
        content_fighter=content_fighter,
        list=test_list,
        owner=user,
        injury_state=ListFighter.ACTIVE,
    )

    active_fighter_2 = ListFighter.objects.create(
        name="Active Fighter 2",
        content_fighter=content_fighter,
        list=test_list,
        owner=user,
        injury_state=ListFighter.ACTIVE,
    )

    active_fighter_3 = ListFighter.objects.create(
        name="Active Fighter 3",
        content_fighter=content_fighter,
        list=test_list,
        owner=user,
        injury_state=ListFighter.ACTIVE,
    )

    # Create an inactive fighter (recovery)
    inactive_fighter = ListFighter.objects.create(
        name="Recovering Fighter",
        content_fighter=content_fighter,
        list=test_list,
        owner=user,
        injury_state=ListFighter.RECOVERY,
    )

    return (
        test_list,
        [active_fighter_1, active_fighter_2, active_fighter_3],
        inactive_fighter,
    )


# Model Tests


@pytest.mark.django_db
def test_crew_template_creation(authenticated_client, test_list_with_fighters):
    """Test creating a crew template."""
    _, user = authenticated_client
    test_list, active_fighters, _ = test_list_with_fighters

    crew_template = CrewTemplate.objects.create(
        name="Alpha Crew",
        list=test_list,
        owner=user,
        random_count=2,
    )
    crew_template.chosen_fighters.add(active_fighters[0])

    assert crew_template.name == "Alpha Crew"
    assert crew_template.list == test_list
    assert crew_template.random_count == 2
    assert crew_template.chosen_fighters.count() == 1


@pytest.mark.django_db
def test_crew_template_str(authenticated_client, test_list_with_fighters):
    """Test the string representation of a crew template."""
    _, user = authenticated_client
    test_list, _, _ = test_list_with_fighters

    crew_template = CrewTemplate.objects.create(
        name="Alpha Crew",
        list=test_list,
        owner=user,
    )

    assert str(crew_template) == "Alpha Crew - Test List"


@pytest.mark.django_db
def test_crew_template_selection_summary_chosen_only(
    authenticated_client, test_list_with_fighters
):
    """Test selection summary with only chosen fighters."""
    _, user = authenticated_client
    test_list, active_fighters, _ = test_list_with_fighters

    crew_template = CrewTemplate.objects.create(
        name="Chosen Only",
        list=test_list,
        owner=user,
        random_count=0,
    )
    crew_template.chosen_fighters.add(active_fighters[0], active_fighters[1])

    assert crew_template.selection_summary() == "2 chosen"


@pytest.mark.django_db
def test_crew_template_selection_summary_random_only(
    authenticated_client, test_list_with_fighters
):
    """Test selection summary with only random fighters."""
    _, user = authenticated_client
    test_list, _, _ = test_list_with_fighters

    crew_template = CrewTemplate.objects.create(
        name="Random Only",
        list=test_list,
        owner=user,
        random_count=3,
    )

    assert crew_template.selection_summary() == "3 random"


@pytest.mark.django_db
def test_crew_template_selection_summary_both(
    authenticated_client, test_list_with_fighters
):
    """Test selection summary with chosen and random fighters."""
    _, user = authenticated_client
    test_list, active_fighters, _ = test_list_with_fighters

    crew_template = CrewTemplate.objects.create(
        name="Mixed",
        list=test_list,
        owner=user,
        random_count=2,
    )
    crew_template.chosen_fighters.add(active_fighters[0])

    assert crew_template.selection_summary() == "1 chosen, 2 random"


@pytest.mark.django_db
def test_crew_template_selection_summary_empty(
    authenticated_client, test_list_with_fighters
):
    """Test selection summary with no fighters selected."""
    _, user = authenticated_client
    test_list, _, _ = test_list_with_fighters

    crew_template = CrewTemplate.objects.create(
        name="Empty",
        list=test_list,
        owner=user,
        random_count=0,
    )

    assert crew_template.selection_summary() == "No fighters selected"


# View Tests


@pytest.mark.django_db
def test_crew_template_index_view(authenticated_client, test_list_with_fighters):
    """Test the crew template index view."""
    client, user = authenticated_client
    test_list, _, _ = test_list_with_fighters

    # Create a crew template
    CrewTemplate.objects.create(
        name="Alpha Crew",
        list=test_list,
        owner=user,
        random_count=3,
    )

    url = reverse("core:crew-template-index", kwargs={"list_id": test_list.id})
    response = client.get(url)

    assert response.status_code == 200
    assert "Alpha Crew" in response.content.decode()


@pytest.mark.django_db
def test_crew_template_index_hides_archived(
    authenticated_client, test_list_with_fighters
):
    """Test that archived crew templates are not shown in the index."""
    client, user = authenticated_client
    test_list, _, _ = test_list_with_fighters

    # Create an archived crew template
    CrewTemplate.objects.create(
        name="Archived Crew",
        list=test_list,
        owner=user,
        random_count=3,
        archived=True,
    )

    url = reverse("core:crew-template-index", kwargs={"list_id": test_list.id})
    response = client.get(url)

    assert response.status_code == 200
    assert "Archived Crew" not in response.content.decode()


@pytest.mark.django_db
def test_crew_template_create_view_get(authenticated_client, test_list_with_fighters):
    """Test the crew template create form loads."""
    client, user = authenticated_client
    test_list, _, _ = test_list_with_fighters

    url = reverse("core:crew-template-create", kwargs={"list_id": test_list.id})
    response = client.get(url)

    assert response.status_code == 200
    assert "Create Crew Template" in response.content.decode()


@pytest.mark.django_db
def test_crew_template_create_view_post(authenticated_client, test_list_with_fighters):
    """Test creating a crew template via POST."""
    client, user = authenticated_client
    test_list, active_fighters, _ = test_list_with_fighters

    url = reverse("core:crew-template-create", kwargs={"list_id": test_list.id})
    data = {
        "name": "New Crew",
        "random_count": 2,
        "chosen_fighters": [str(active_fighters[0].id)],
    }
    response = client.post(url, data)

    assert response.status_code == 302
    assert CrewTemplate.objects.filter(name="New Crew").exists()
    template = CrewTemplate.objects.get(name="New Crew")
    assert template.random_count == 2
    assert template.chosen_fighters.count() == 1


@pytest.mark.django_db
def test_crew_template_create_requires_selection(
    authenticated_client, test_list_with_fighters
):
    """Test that creating a crew template requires at least chosen fighters or random count."""
    client, user = authenticated_client
    test_list, _, _ = test_list_with_fighters

    url = reverse("core:crew-template-create", kwargs={"list_id": test_list.id})
    data = {
        "name": "Empty Crew",
        "random_count": 0,
    }
    response = client.post(url, data)

    # Should stay on form with validation error
    assert response.status_code == 200
    assert not CrewTemplate.objects.filter(name="Empty Crew").exists()


@pytest.mark.django_db
def test_crew_template_edit_view_get(authenticated_client, test_list_with_fighters):
    """Test the crew template edit form loads."""
    client, user = authenticated_client
    test_list, _, _ = test_list_with_fighters

    crew_template = CrewTemplate.objects.create(
        name="Editable Crew",
        list=test_list,
        owner=user,
        random_count=2,
    )

    url = reverse(
        "core:crew-template-edit",
        kwargs={"list_id": test_list.id, "template_id": crew_template.id},
    )
    response = client.get(url)

    assert response.status_code == 200
    assert "Edit Crew Template" in response.content.decode()


@pytest.mark.django_db
def test_crew_template_edit_view_post(authenticated_client, test_list_with_fighters):
    """Test editing a crew template via POST."""
    client, user = authenticated_client
    test_list, active_fighters, _ = test_list_with_fighters

    crew_template = CrewTemplate.objects.create(
        name="Original Name",
        list=test_list,
        owner=user,
        random_count=1,
    )

    url = reverse(
        "core:crew-template-edit",
        kwargs={"list_id": test_list.id, "template_id": crew_template.id},
    )
    data = {
        "name": "Updated Name",
        "random_count": 3,
        "chosen_fighters": [str(active_fighters[0].id), str(active_fighters[1].id)],
    }
    response = client.post(url, data)

    assert response.status_code == 302
    crew_template.refresh_from_db()
    assert crew_template.name == "Updated Name"
    assert crew_template.random_count == 3
    assert crew_template.chosen_fighters.count() == 2


@pytest.mark.django_db
def test_crew_template_delete_view_get(authenticated_client, test_list_with_fighters):
    """Test the crew template delete confirmation page."""
    client, user = authenticated_client
    test_list, _, _ = test_list_with_fighters

    crew_template = CrewTemplate.objects.create(
        name="Delete Me",
        list=test_list,
        owner=user,
        random_count=1,
    )

    url = reverse(
        "core:crew-template-delete",
        kwargs={"list_id": test_list.id, "template_id": crew_template.id},
    )
    response = client.get(url)

    assert response.status_code == 200
    assert "Delete Me" in response.content.decode()


@pytest.mark.django_db
def test_crew_template_delete_view_post(authenticated_client, test_list_with_fighters):
    """Test deleting (archiving) a crew template."""
    client, user = authenticated_client
    test_list, _, _ = test_list_with_fighters

    crew_template = CrewTemplate.objects.create(
        name="Delete Me",
        list=test_list,
        owner=user,
        random_count=1,
    )

    url = reverse(
        "core:crew-template-delete",
        kwargs={"list_id": test_list.id, "template_id": crew_template.id},
    )
    response = client.post(url)

    assert response.status_code == 302
    crew_template.refresh_from_db()
    assert crew_template.archived is True


@pytest.mark.django_db
def test_crew_template_only_shows_active_fighters_in_form(
    authenticated_client, test_list_with_fighters
):
    """Test that only active fighters appear in the form."""
    client, user = authenticated_client
    test_list, active_fighters, inactive_fighter = test_list_with_fighters

    url = reverse("core:crew-template-create", kwargs={"list_id": test_list.id})
    response = client.get(url)

    content = response.content.decode()
    # Active fighters should appear
    assert "Active Fighter 1" in content
    assert "Active Fighter 2" in content
    assert "Active Fighter 3" in content
    # Inactive fighter should not appear
    assert "Recovering Fighter" not in content


@pytest.mark.django_db
def test_crew_template_owner_check_on_create(test_list_with_fighters):
    """Test that non-owners cannot create crew templates."""
    test_list, _, _ = test_list_with_fighters

    # Create a different user
    other_user = User.objects.create_user(username="otheruser", password="testpass")
    other_client = Client()
    other_client.force_login(other_user)

    url = reverse("core:crew-template-create", kwargs={"list_id": test_list.id})
    response = other_client.get(url)

    assert response.status_code == 404


@pytest.mark.django_db
def test_crew_template_owner_check_on_edit(
    authenticated_client, test_list_with_fighters
):
    """Test that non-owners cannot edit crew templates."""
    _, user = authenticated_client
    test_list, _, _ = test_list_with_fighters

    crew_template = CrewTemplate.objects.create(
        name="Protected Crew",
        list=test_list,
        owner=user,
        random_count=1,
    )

    # Create a different user
    other_user = User.objects.create_user(username="otheruser", password="testpass")
    other_client = Client()
    other_client.force_login(other_user)

    url = reverse(
        "core:crew-template-edit",
        kwargs={"list_id": test_list.id, "template_id": crew_template.id},
    )
    response = other_client.get(url)

    assert response.status_code == 404


@pytest.mark.django_db
def test_crew_template_owner_check_on_delete(
    authenticated_client, test_list_with_fighters
):
    """Test that non-owners cannot delete crew templates."""
    _, user = authenticated_client
    test_list, _, _ = test_list_with_fighters

    crew_template = CrewTemplate.objects.create(
        name="Protected Crew",
        list=test_list,
        owner=user,
        random_count=1,
    )

    # Create a different user
    other_user = User.objects.create_user(username="otheruser", password="testpass")
    other_client = Client()
    other_client.force_login(other_user)

    url = reverse(
        "core:crew-template-delete",
        kwargs={"list_id": test_list.id, "template_id": crew_template.id},
    )
    response = other_client.post(url)

    assert response.status_code == 404
    crew_template.refresh_from_db()
    assert crew_template.archived is False


@pytest.mark.django_db
def test_crew_template_anonymous_redirect_on_index(test_list_with_fighters):
    """Test that anonymous users are redirected from the index."""
    test_list, _, _ = test_list_with_fighters

    client = Client()
    url = reverse("core:crew-template-index", kwargs={"list_id": test_list.id})
    response = client.get(url)

    assert response.status_code == 302
