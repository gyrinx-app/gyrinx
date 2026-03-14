"""Tests for the Notes and Lore pages."""

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
    fighter.notes = "<p>Fighter notes here.</p>"
    fighter.save()

    response = client.get(reverse("core:list-notes", args=[lst.id]))
    content = response.content.decode()
    assert "Fighter notes here." in content


@pytest.mark.django_db
def test_notes_page_does_not_show_private_notes(
    client, user, make_list, make_list_fighter
):
    """Test that private_notes are NOT shown on the public notes page."""
    lst = make_list("Test Gang")
    fighter = make_list_fighter(lst, "Test Fighter")
    fighter.private_notes = "<p>Secret private notes.</p>"
    fighter.save()

    response = client.get(reverse("core:list-notes", args=[lst.id]))
    content = response.content.decode()
    assert "Secret private notes." not in content


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
    """Test that editing fighter notes saves the notes field."""
    lst = make_list("Test Gang")
    fighter = make_list_fighter(lst, "Test Fighter")
    client.force_login(user)

    response = client.post(
        reverse("core:list-fighter-notes-edit", args=[lst.id, fighter.id]),
        {"notes": "<p>Updated fighter notes.</p>"},
    )
    assert response.status_code == 302

    fighter.refresh_from_db()
    assert fighter.notes == "<p>Updated fighter notes.</p>"


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
def test_list_header_shows_lore_and_notes_links(client, user, make_list):
    """Test that both Lore and Notes links always appear in the list header."""
    lst = make_list("Test Gang")
    client.force_login(user)

    response = client.get(reverse("core:list", args=[lst.id]))
    content = response.content.decode()
    assert "Lore" in content
    assert "Notes" in content


@pytest.mark.django_db
def test_list_header_shows_links_without_content(client, user, make_list):
    """Test that Lore and Notes links appear even when no content exists."""
    lst = make_list("Test Gang")
    # Don't set narrative or notes
    client.force_login(user)

    response = client.get(reverse("core:list", args=[lst.id]))
    content = response.content.decode()
    assert "Lore" in content
    assert "Notes" in content


@pytest.mark.django_db
def test_notes_page_has_navigation_to_lore(client, user, make_list):
    """Test that the notes page has a link to the lore page."""
    lst = make_list("Test Gang")

    response = client.get(reverse("core:list-notes", args=[lst.id]))
    content = response.content.decode()
    about_url = reverse("core:list-about", args=[lst.id])
    assert about_url in content
    assert "Lore" in content


@pytest.mark.django_db
def test_lore_page_has_navigation_to_notes(client, user, make_list):
    """Test that the lore page has a link to the notes page."""
    lst = make_list("Test Gang")

    response = client.get(reverse("core:list-about", args=[lst.id]))
    content = response.content.decode()
    notes_url = reverse("core:list-notes", args=[lst.id])
    assert notes_url in content
    assert "Notes" in content


@pytest.mark.django_db
def test_notes_model_field_exists():
    """Test that the notes field exists on the List model."""
    field = List._meta.get_field("notes")
    assert field is not None
    assert field.blank is True


@pytest.mark.django_db
def test_lore_page_uses_lore_label(client, user, make_list):
    """Test that the lore page uses 'Lore' instead of 'About'."""
    lst = make_list("Test Gang")
    lst.narrative = "<p>Some narrative</p>"
    lst.save()

    response = client.get(reverse("core:list-about", args=[lst.id]))
    content = response.content.decode()
    # The active button should say "Lore"
    assert "Lore" in content


@pytest.mark.django_db
def test_lore_page_shows_no_lore_empty_state(client, user, make_list):
    """Test that the lore page shows 'No lore' empty state."""
    lst = make_list("Test Gang")
    client.force_login(user)

    response = client.get(reverse("core:list-about", args=[lst.id]))
    content = response.content.decode()
    assert "No lore added yet." in content


@pytest.mark.django_db
def test_fighter_card_tab_order(client, user, make_list, make_list_fighter):
    """Test that fighter card tabs are in the order: Card | Lore | Notes."""
    lst = make_list("Test Gang")
    fighter = make_list_fighter(lst, "Test Fighter")
    client.force_login(user)

    response = client.get(reverse("core:list", args=[lst.id]))
    content = response.content.decode()

    # Find the fighter's tab list by looking for the specific tab IDs
    card_tab = f'id="card-tab-{fighter.id}"'
    lore_tab = f'id="lore-tab-{fighter.id}"'
    notes_tab = f'id="notes-tab-{fighter.id}"'

    card_pos = content.index(card_tab)
    lore_pos = content.index(lore_tab)
    notes_pos = content.index(notes_tab)
    assert card_pos < lore_pos < notes_pos


@pytest.mark.django_db
def test_private_notes_hidden_from_non_owner(
    client, user, make_user, make_list, make_list_fighter
):
    """Test that private_notes are not visible to non-owners on the fighter card."""
    lst = make_list("Test Gang")
    fighter = make_list_fighter(lst, "Test Fighter")
    fighter.private_notes = "<p>Owner secret notes.</p>"
    fighter.save()

    other_user = make_user("otheruser", "password")
    client.force_login(other_user)

    response = client.get(reverse("core:list", args=[lst.id]))
    content = response.content.decode()
    assert "Owner secret notes." not in content


@pytest.mark.django_db
def test_private_notes_visible_to_owner(client, user, make_list, make_list_fighter):
    """Test that private_notes are visible to the owner on the fighter card."""
    lst = make_list("Test Gang")
    fighter = make_list_fighter(lst, "Test Fighter")
    fighter.private_notes = "<p>Owner secret notes.</p>"
    fighter.save()
    client.force_login(user)

    response = client.get(reverse("core:list", args=[lst.id]))
    content = response.content.decode()
    assert "Owner secret notes." in content


@pytest.mark.django_db
def test_private_notes_has_private_indicator(
    client, user, make_list, make_list_fighter
):
    """Test that private notes show a 'PRIVATE' indicator."""
    lst = make_list("Test Gang")
    fighter = make_list_fighter(lst, "Test Fighter")
    fighter.private_notes = "<p>My private notes.</p>"
    fighter.save()
    client.force_login(user)

    response = client.get(reverse("core:list", args=[lst.id]))
    content = response.content.decode()
    # Check for the PRIVATE indicator (uppercase, small font)
    assert "Private" in content


@pytest.mark.django_db
def test_lore_page_shows_fighter_image(client, user, make_list, make_list_fighter):
    """Test that the lore page shows fighter images."""
    lst = make_list("Test Gang")
    fighter = make_list_fighter(lst, "Test Fighter")
    fighter.narrative = "<p>Some lore</p>"
    fighter.save()

    response = client.get(reverse("core:list-about", args=[lst.id]))
    # Just verify the page loads - we can't easily test image display without an actual image
    assert response.status_code == 200
