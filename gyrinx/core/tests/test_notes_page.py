"""Tests for the Notes page feature."""

import pytest
from django.urls import reverse

from gyrinx.core.models.list import List


@pytest.mark.django_db
def test_notes_page_loads(client, user, make_list):
    """Test that the notes page loads successfully."""
    lst = make_list("Test Gang")
    response = client.get(reverse("core:list-notes", args=[lst.id]))
    assert response.status_code == 200
    assert "Test Gang" in response.content.decode()


@pytest.mark.django_db
def test_notes_page_shows_gang_notes(client, user, make_list):
    """Test that gang-level notes are displayed on the notes page."""
    lst = make_list("Test Gang")
    lst.notes = "<p>These are gang notes.</p>"
    lst.save()

    response = client.get(reverse("core:list-notes", args=[lst.id]))
    content = response.content.decode()
    assert "These are gang notes." in content


@pytest.mark.django_db
def test_notes_page_shows_fighter_notes(client, user, make_list, make_list_fighter):
    """Test that fighter-level notes are displayed on the notes page."""
    lst = make_list("Test Gang")
    fighter = make_list_fighter(lst, "Test Fighter")
    fighter.private_notes = "<p>Fighter notes here.</p>"
    fighter.save()

    response = client.get(reverse("core:list-notes", args=[lst.id]))
    content = response.content.decode()
    assert "Fighter notes here." in content


@pytest.mark.django_db
def test_notes_page_empty_state(client, user, make_list):
    """Test empty state when no notes exist."""
    lst = make_list("Test Gang")
    client.force_login(user)

    response = client.get(reverse("core:list-notes", args=[lst.id]))
    content = response.content.decode()
    assert "No notes added yet." in content


@pytest.mark.django_db
def test_notes_page_edit_link_for_owner(client, user, make_list):
    """Test that edit link is shown for the owner."""
    lst = make_list("Test Gang")
    lst.notes = "<p>Some notes</p>"
    lst.save()
    client.force_login(user)

    response = client.get(reverse("core:list-notes", args=[lst.id]))
    content = response.content.decode()
    assert "Edit" in content


@pytest.mark.django_db
def test_notes_page_no_edit_link_for_non_owner(client, user, make_user, make_list):
    """Test that edit link is not shown for non-owners."""
    lst = make_list("Test Gang")
    lst.notes = "<p>Some notes</p>"
    lst.save()

    other_user = make_user("otheruser", "password")
    client.force_login(other_user)

    response = client.get(reverse("core:list-notes", args=[lst.id]))
    content = response.content.decode()
    # The Edit button should not be present for non-owners
    assert "bi-pencil" not in content


@pytest.mark.django_db
def test_notes_field_in_edit_list_form(client, user, make_list):
    """Test that the notes field appears in the edit list form."""
    lst = make_list("Test Gang")
    client.force_login(user)

    response = client.get(reverse("core:list-edit", args=[lst.id]))
    content = response.content.decode()
    assert "Notes" in content


@pytest.mark.django_db
def test_edit_list_saves_notes(client, user, make_list):
    """Test that editing the list saves the notes field."""
    lst = make_list("Test Gang")
    client.force_login(user)

    response = client.post(
        reverse("core:list-edit", args=[lst.id]),
        {
            "name": "Test Gang",
            "narrative": "",
            "notes": "<p>New gang notes.</p>",
            "public": True,
            "theme_color": "",
        },
    )
    assert response.status_code == 302

    lst.refresh_from_db()
    assert lst.notes == "<p>New gang notes.</p>"


@pytest.mark.django_db
def test_fighter_notes_edit_page_loads(client, user, make_list, make_list_fighter):
    """Test that the fighter notes edit page loads."""
    lst = make_list("Test Gang")
    fighter = make_list_fighter(lst, "Test Fighter")
    client.force_login(user)

    response = client.get(
        reverse("core:list-fighter-notes-edit", args=[lst.id, fighter.id])
    )
    assert response.status_code == 200
    assert "Notes" in response.content.decode()


@pytest.mark.django_db
def test_fighter_notes_edit_saves(client, user, make_list, make_list_fighter):
    """Test that editing fighter notes saves the private_notes field."""
    lst = make_list("Test Gang")
    fighter = make_list_fighter(lst, "Test Fighter")
    client.force_login(user)

    response = client.post(
        reverse("core:list-fighter-notes-edit", args=[lst.id, fighter.id]),
        {"private_notes": "<p>Updated fighter notes.</p>"},
    )
    assert response.status_code == 302

    fighter.refresh_from_db()
    assert fighter.private_notes == "<p>Updated fighter notes.</p>"


@pytest.mark.django_db
def test_fighter_notes_edit_requires_login(client, make_list, make_list_fighter, user):
    """Test that fighter notes edit requires authentication."""
    lst = make_list("Test Gang")
    fighter = make_list_fighter(lst, "Test Fighter")

    response = client.get(
        reverse("core:list-fighter-notes-edit", args=[lst.id, fighter.id])
    )
    assert response.status_code == 302  # Redirect to login


@pytest.mark.django_db
def test_fighter_notes_edit_requires_owner(
    client, user, make_user, make_list, make_list_fighter
):
    """Test that only the list owner can edit fighter notes."""
    lst = make_list("Test Gang")
    fighter = make_list_fighter(lst, "Test Fighter")

    other_user = make_user("otheruser", "password")
    client.force_login(other_user)

    response = client.get(
        reverse("core:list-fighter-notes-edit", args=[lst.id, fighter.id])
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_list_header_shows_about_and_notes_links(client, user, make_list):
    """Test that both About and Notes links appear in the list header when content exists."""
    lst = make_list("Test Gang")
    lst.narrative = "<p>Some narrative</p>"
    lst.save()
    client.force_login(user)

    response = client.get(reverse("core:list", args=[lst.id]))
    content = response.content.decode()
    assert "About" in content
    assert "Notes" in content


@pytest.mark.django_db
def test_list_header_shows_links_with_notes_only(client, user, make_list):
    """Test that About and Notes links appear when only notes exist."""
    lst = make_list("Test Gang")
    lst.notes = "<p>Some notes</p>"
    lst.save()
    client.force_login(user)

    response = client.get(reverse("core:list", args=[lst.id]))
    content = response.content.decode()
    assert "About" in content
    assert "Notes" in content


@pytest.mark.django_db
def test_notes_page_has_navigation_to_about(client, user, make_list):
    """Test that the notes page has a link to the about page."""
    lst = make_list("Test Gang")

    response = client.get(reverse("core:list-notes", args=[lst.id]))
    content = response.content.decode()
    about_url = reverse("core:list-about", args=[lst.id])
    assert about_url in content


@pytest.mark.django_db
def test_about_page_has_navigation_to_notes(client, user, make_list):
    """Test that the about page has a link to the notes page."""
    lst = make_list("Test Gang")

    response = client.get(reverse("core:list-about", args=[lst.id]))
    content = response.content.decode()
    notes_url = reverse("core:list-notes", args=[lst.id])
    assert notes_url in content


@pytest.mark.django_db
def test_notes_model_field_exists():
    """Test that the notes field exists on the List model."""
    field = List._meta.get_field("notes")
    assert field is not None
    assert field.blank is True
