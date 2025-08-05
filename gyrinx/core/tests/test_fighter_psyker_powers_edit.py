import pytest
from django.test import Client
from django.urls import reverse

from gyrinx.content.models import (
    ContentFighterPsykerDisciplineAssignment,
    ContentFighterPsykerPowerDefaultAssignment,
    ContentPsykerDiscipline,
    ContentPsykerPower,
    ContentRule,
)
from gyrinx.core.models.list import ListFighterPsykerPowerAssignment


@pytest.fixture
def psyker_rule():
    """Get or create psyker rule."""
    return ContentRule.objects.get_or_create(name="Psyker")[0]


@pytest.fixture
def biomancy_discipline():
    """Create generic biomancy discipline."""
    return ContentPsykerDiscipline.objects.get_or_create(
        name="Biomancy",
        defaults={"generic": True},
    )[0]


@pytest.fixture
def chronomancy_discipline():
    """Create non-generic chronomancy discipline."""
    return ContentPsykerDiscipline.objects.get_or_create(
        name="Chronomancy",
        defaults={"generic": False},
    )[0]


@pytest.fixture
def telepathy_discipline():
    """Create another generic discipline."""
    return ContentPsykerDiscipline.objects.get_or_create(
        name="Telepathy",
        defaults={"generic": True},
    )[0]


@pytest.fixture
def biomancy_power(biomancy_discipline):
    """Create a biomancy power."""
    return ContentPsykerPower.objects.get_or_create(
        name="Arachnosis",
        discipline=biomancy_discipline,
    )[0]


@pytest.fixture
def chronomancy_power(chronomancy_discipline):
    """Create a chronomancy power."""
    return ContentPsykerPower.objects.get_or_create(
        name="Freeze Time",
        discipline=chronomancy_discipline,
    )[0]


@pytest.fixture
def telepathy_power(telepathy_discipline):
    """Create a telepathy power."""
    return ContentPsykerPower.objects.get_or_create(
        name="Mind Control",
        discipline=telepathy_discipline,
    )[0]


@pytest.fixture
def psyker_fighter(content_fighter, psyker_rule):
    """Create a content fighter with psyker rule."""
    content_fighter.rules.add(psyker_rule)
    return content_fighter


@pytest.fixture
def psyker_list(make_list):
    """Create a test list."""
    return make_list("Psyker Test List")


@pytest.fixture
def list_psyker(psyker_list, make_list_fighter, psyker_fighter):
    """Create a list fighter that is a psyker."""
    return make_list_fighter(psyker_list, "Test Psyker", content_fighter=psyker_fighter)


@pytest.fixture
def client(user):
    """Create a logged-in test client."""
    c = Client()
    c.login(username="testuser", password="password")
    return c


# Basic View Tests


@pytest.mark.django_db
def test_psyker_powers_view_requires_login(psyker_list, list_psyker):
    """Test that the view requires authentication."""
    client = Client()
    url = reverse(
        "core:list-fighter-powers-edit", args=[psyker_list.id, list_psyker.id]
    )
    response = client.get(url)
    assert response.status_code == 302
    assert "login" in response.url


@pytest.mark.django_db
def test_psyker_powers_view_requires_owner(client, psyker_list, list_psyker, user):
    """Test that only the list owner can access the view."""
    # Create another user
    from django.contrib.auth import get_user_model

    User = get_user_model()
    other_user = User.objects.create_user(username="other", password="password")

    # Change list owner
    psyker_list.owner = other_user
    psyker_list.save()

    url = reverse(
        "core:list-fighter-powers-edit", args=[psyker_list.id, list_psyker.id]
    )
    response = client.get(url)
    assert response.status_code == 404


@pytest.mark.django_db
def test_psyker_powers_view_get(
    client,
    psyker_list,
    list_psyker,
    biomancy_power,
    chronomancy_power,
    telepathy_power,
):
    """Test GET request displays powers correctly."""
    url = reverse(
        "core:list-fighter-powers-edit", args=[psyker_list.id, list_psyker.id]
    )
    response = client.get(url)

    assert response.status_code == 200
    assert "list" in response.context
    assert "fighter" in response.context
    assert "current_powers" in response.context
    assert "available_disciplines" in response.context

    # Should show generic disciplines (Biomancy, Telepathy)
    content = response.content.decode()
    assert "Biomancy" in content
    assert "Telepathy" in content
    assert "Arachnosis" in content
    assert "Mind Control" in content

    # Non-generic discipline without assignment should not show
    assert "Chronomancy" not in content


# Default Power Tests


@pytest.mark.django_db
def test_default_power_display(
    client, psyker_list, list_psyker, biomancy_power, psyker_fighter
):
    """Test that default powers are displayed correctly."""
    # Add default power assignment
    ContentFighterPsykerPowerDefaultAssignment.objects.create(
        fighter=psyker_fighter,
        psyker_power=biomancy_power,
    )

    url = reverse(
        "core:list-fighter-powers-edit", args=[psyker_list.id, list_psyker.id]
    )
    response = client.get(url)

    assert response.status_code == 200

    # Check that default power shows in current powers
    current_powers = response.context["current_powers"]
    assert len(current_powers) == 1
    assert current_powers[0].psyker_power == biomancy_power
    assert current_powers[0].kind() == "default"

    # Check it's marked as default in HTML
    content = response.content.decode()
    assert "Arachnosis" in content
    assert "Default" in content


@pytest.mark.django_db
def test_disable_default_power(
    client, psyker_list, list_psyker, biomancy_power, psyker_fighter
):
    """Test disabling a default power."""
    # Add default power assignment
    default_assignment = ContentFighterPsykerPowerDefaultAssignment.objects.create(
        fighter=psyker_fighter,
        psyker_power=biomancy_power,
    )

    url = reverse(
        "core:list-fighter-powers-edit", args=[psyker_list.id, list_psyker.id]
    )

    # Disable the default power
    response = client.post(
        url,
        {
            "action": "remove",
            "psyker_power_id": biomancy_power.id,
            "assign_kind": "default",
        },
    )

    assert response.status_code == 302

    # Check that the power is now disabled
    list_psyker.refresh_from_db()
    assert default_assignment in list_psyker.disabled_pskyer_default_powers.all()

    # Verify it no longer shows as current power
    response = client.get(url)
    current_powers = response.context["current_powers"]
    assert len(current_powers) == 0


# Power Assignment Tests


@pytest.mark.django_db
def test_add_power(client, psyker_list, list_psyker, biomancy_power):
    """Test adding a power to a fighter."""
    url = reverse(
        "core:list-fighter-powers-edit", args=[psyker_list.id, list_psyker.id]
    )

    # Add the power
    response = client.post(
        url,
        {
            "action": "add",
            "psyker_power_id": biomancy_power.id,
        },
    )

    assert response.status_code == 302

    # Check that the power was added
    assert ListFighterPsykerPowerAssignment.objects.filter(
        list_fighter=list_psyker,
        psyker_power=biomancy_power,
    ).exists()

    # Verify it shows as current power
    response = client.get(url)
    current_powers = response.context["current_powers"]
    assert len(current_powers) == 1
    assert current_powers[0].psyker_power == biomancy_power
    assert current_powers[0].kind() == "assigned"


@pytest.mark.django_db
def test_remove_assigned_power(client, psyker_list, list_psyker, biomancy_power):
    """Test removing an assigned power."""
    # First add the power
    ListFighterPsykerPowerAssignment.objects.create(
        list_fighter=list_psyker,
        psyker_power=biomancy_power,
    )

    url = reverse(
        "core:list-fighter-powers-edit", args=[psyker_list.id, list_psyker.id]
    )

    # Remove the power
    response = client.post(
        url,
        {
            "action": "remove",
            "psyker_power_id": biomancy_power.id,
            "assign_kind": "assigned",
        },
    )

    assert response.status_code == 302

    # Check that the power was removed
    assert not ListFighterPsykerPowerAssignment.objects.filter(
        list_fighter=list_psyker,
        psyker_power=biomancy_power,
    ).exists()


# Search and Filter Tests


@pytest.mark.django_db
def test_search_powers(
    client,
    psyker_list,
    list_psyker,
    biomancy_power,
    telepathy_power,
):
    """Test searching for powers."""
    url = reverse(
        "core:list-fighter-powers-edit", args=[psyker_list.id, list_psyker.id]
    )

    # Search for "mind"
    response = client.get(url, {"q": "mind"})

    assert response.status_code == 200

    # Should find Mind Control
    available_disciplines = response.context["available_disciplines"]
    found_powers = []
    for disc in available_disciplines:
        found_powers.extend(disc["powers"])

    assert len(found_powers) == 1
    assert found_powers[0].psyker_power.name == "Mind Control"


@pytest.mark.django_db
def test_search_by_discipline(
    client,
    psyker_list,
    list_psyker,
    biomancy_power,
    telepathy_power,
):
    """Test searching by discipline name."""
    url = reverse(
        "core:list-fighter-powers-edit", args=[psyker_list.id, list_psyker.id]
    )

    # Search for "bio"
    response = client.get(url, {"q": "bio"})

    assert response.status_code == 200

    # Should find powers from Biomancy
    available_disciplines = response.context["available_disciplines"]
    assert len(available_disciplines) == 1
    assert available_disciplines[0]["discipline"] == "Biomancy"


@pytest.mark.django_db
def test_search_does_not_filter_current_powers(
    client, psyker_list, list_psyker, biomancy_power, telepathy_power
):
    """Test that search doesn't filter current powers section."""
    # Add both powers
    ListFighterPsykerPowerAssignment.objects.create(
        list_fighter=list_psyker,
        psyker_power=biomancy_power,
    )
    ListFighterPsykerPowerAssignment.objects.create(
        list_fighter=list_psyker,
        psyker_power=telepathy_power,
    )

    url = reverse(
        "core:list-fighter-powers-edit", args=[psyker_list.id, list_psyker.id]
    )

    # Search for "mind" (should only match telepathy power)
    response = client.get(url, {"q": "mind"})

    assert response.status_code == 200

    # Current powers should still show both
    current_powers = response.context["current_powers"]
    assert len(current_powers) == 2

    # Available powers should be empty (both are assigned)
    available_disciplines = response.context["available_disciplines"]
    assert len(available_disciplines) == 0


@pytest.mark.django_db
def test_show_restricted_powers(
    client,
    psyker_list,
    list_psyker,
    biomancy_power,
    chronomancy_discipline,
    chronomancy_power,
):
    """Test showing restricted (non-generic) disciplines."""
    url = reverse(
        "core:list-fighter-powers-edit", args=[psyker_list.id, list_psyker.id]
    )

    # Without restricted flag, non-generic discipline shouldn't show
    response = client.get(url)
    content = response.content.decode()
    assert "Chronomancy" not in content

    # With restricted flag, it should show
    response = client.get(url, {"restricted": "1"})
    content = response.content.decode()
    assert "Chronomancy" in content
    assert "Freeze Time" in content


# Edge Cases


@pytest.mark.django_db
def test_empty_disciplines_not_shown(client, psyker_list, list_psyker, biomancy_power):
    """Test that disciplines with all powers assigned are not shown."""
    # Assign the only biomancy power
    ListFighterPsykerPowerAssignment.objects.create(
        list_fighter=list_psyker,
        psyker_power=biomancy_power,
    )

    url = reverse(
        "core:list-fighter-powers-edit", args=[psyker_list.id, list_psyker.id]
    )
    response = client.get(url)

    # Biomancy should not appear in available disciplines
    available_disciplines = response.context["available_disciplines"]
    discipline_names = [d["discipline"] for d in available_disciplines]
    assert "Biomancy" not in discipline_names


@pytest.mark.django_db
def test_discipline_with_fighter_assignment(
    client,
    psyker_list,
    list_psyker,
    psyker_fighter,
    chronomancy_discipline,
    chronomancy_power,
):
    """Test that disciplines assigned to fighter are shown."""
    # Assign discipline to fighter
    ContentFighterPsykerDisciplineAssignment.objects.create(
        fighter=psyker_fighter,
        discipline=chronomancy_discipline,
    )

    url = reverse(
        "core:list-fighter-powers-edit", args=[psyker_list.id, list_psyker.id]
    )
    response = client.get(url)

    # Chronomancy should now be available
    content = response.content.decode()
    assert "Chronomancy" in content
    assert "Freeze Time" in content


@pytest.mark.django_db
def test_no_psyker_powers_message(client, psyker_list, list_psyker):
    """Test message when no powers are available."""
    # Create a list without any psyker powers in the database
    ContentPsykerPower.objects.all().delete()

    url = reverse(
        "core:list-fighter-powers-edit", args=[psyker_list.id, list_psyker.id]
    )
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()
    assert "No psyker powers assigned to this fighter" in content
    assert "No available psyker powers found" in content


@pytest.mark.django_db
def test_invalid_power_id(client, psyker_list, list_psyker):
    """Test handling of invalid power ID."""
    url = reverse(
        "core:list-fighter-powers-edit", args=[psyker_list.id, list_psyker.id]
    )

    # Try to add non-existent power
    response = client.post(
        url,
        {
            "action": "add",
            "psyker_power_id": "00000000-0000-0000-0000-000000000000",
        },
    )

    # Should get 404
    assert response.status_code == 404


@pytest.mark.django_db
def test_missing_action(client, psyker_list, list_psyker, biomancy_power):
    """Test POST without action parameter."""
    url = reverse(
        "core:list-fighter-powers-edit", args=[psyker_list.id, list_psyker.id]
    )

    response = client.post(
        url,
        {
            "psyker_power_id": biomancy_power.id,
        },
    )

    # Should render the page without error
    assert response.status_code == 200
    # Power should not be added
    assert not ListFighterPsykerPowerAssignment.objects.filter(
        list_fighter=list_psyker,
        psyker_power=biomancy_power,
    ).exists()
