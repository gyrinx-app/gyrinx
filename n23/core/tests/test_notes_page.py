"""Tests for the Notes and Lore pages."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from n23.core.models.list import List


@pytest.mark.django_db
def test_notes_page_shows_gang_and_fighter_notes(client, make_list, make_list_fighter):
    lst = make_list("Test Gang")
    lst.notes = "<p>These are gang notes.</p>"
    lst.save()
    fighter = make_list_fighter(lst, "Test Fighter")
    fighter.notes = "<p>Fighter notes here.</p>"
    fighter.save()

    response = client.get(reverse("core:list-notes", args=[lst.id]))
    assert response.status_code == 200
    content = response.content.decode()
    assert lst.name in content
    assert "These are gang notes." in content
    assert "Fighter notes here." in content
    assert reverse("core:list-about", args=[lst.id]) in content
    assert "Lore" in content


@pytest.mark.django_db
def test_notes_page_shows_private_notes_to_owner(
    client, user, make_list, make_list_fighter
):
    """Test that private_notes are shown to the owner on the notes page."""
    lst = make_list("Test Gang")
    fighter = make_list_fighter(lst, "Test Fighter")
    fighter.private_notes = "<p>Secret private notes.</p>"
    fighter.save()
    client.force_login(user)

    response = client.get(reverse("core:list-notes", args=[lst.id]))
    assert response.status_code == 200
    content = response.content.decode()
    assert "Secret private notes." in content
    assert "Private" in content


@pytest.mark.django_db
def test_notes_page_hides_private_notes_from_non_owner(
    client, user, make_user, make_list, make_list_fighter
):
    """Test that private_notes are NOT shown to non-owners on the notes page."""
    lst = make_list("Test Gang")
    fighter = make_list_fighter(lst, "Test Fighter")
    fighter.private_notes = "<p>Secret private notes.</p>"
    fighter.save()

    other_user = make_user("otheruser", "password")
    client.force_login(other_user)

    response = client.get(reverse("core:list-notes", args=[lst.id]))
    content = response.content.decode()
    assert "Secret private notes." not in content


@pytest.mark.django_db
def test_notes_page_hides_private_notes_from_anonymous(
    client, user, make_list, make_list_fighter
):
    """Test that private_notes are NOT shown to anonymous users on the notes page."""
    lst = make_list("Test Gang")
    fighter = make_list_fighter(lst, "Test Fighter")
    fighter.private_notes = "<p>Secret private notes.</p>"
    fighter.save()
    client.logout()

    response = client.get(reverse("core:list-notes", args=[lst.id]))
    content = response.content.decode()
    assert "Secret private notes." not in content


@pytest.mark.django_db
def test_notes_page_shows_fighter_with_only_private_notes_to_owner(
    client, user, make_list, make_list_fighter
):
    """Test that fighters with only private notes (no public notes) appear for the owner."""
    lst = make_list("Test Gang")
    fighter = make_list_fighter(lst, "Test Fighter")
    fighter.private_notes = "<p>Only private notes.</p>"
    fighter.save()
    client.force_login(user)

    response = client.get(reverse("core:list-notes", args=[lst.id]))
    content = response.content.decode()
    assert "Only private notes." in content
    assert fighter.name in content


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
    assert reverse("core:list-edit", args=[lst.id]) not in content


@pytest.mark.django_db
def test_edit_list_saves_notes(client, user, make_list):
    """Test that editing the list saves the notes field."""
    lst = make_list("Test Gang")
    client.force_login(user)

    response = client.get(reverse("core:list-edit", args=[lst.id]))
    assert response.status_code == 200
    assert "notes" in response.context["form"].fields

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
def test_fighter_notes_edit_saves(client, user, make_list, make_list_fighter):
    """Test that editing fighter notes saves the notes field."""
    lst = make_list("Test Gang")
    fighter = make_list_fighter(lst, "Test Fighter")
    client.force_login(user)

    response = client.get(
        reverse("core:list-fighter-notes-edit", args=[lst.id, fighter.id])
    )
    assert response.status_code == 200
    assert "notes" in response.context["form"].fields

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
def test_list_header_shows_links_without_content(client, user, make_list):
    """Test that Lore and Notes links appear even when no content exists."""
    lst = make_list("Test Gang")
    # Don't set narrative or notes
    client.force_login(user)

    response = client.get(reverse("core:list", args=[lst.id]))
    content = response.content.decode()
    assert reverse("core:list-about", args=[lst.id]) in content
    assert reverse("core:list-notes", args=[lst.id]) in content


@pytest.mark.django_db
def test_lore_page_shows_gang_and_fighter_lore_with_navigation(
    client, make_list, make_list_fighter
):
    lst = make_list("Test Gang")
    lst.narrative = "<p>Gang lore.</p>"
    lst.save()
    fighter = make_list_fighter(lst, "Test Fighter")
    fighter.narrative = "<p>Fighter lore.</p>"
    fighter.save()

    response = client.get(reverse("core:list-about", args=[lst.id]))
    assert response.status_code == 200
    content = response.content.decode()
    notes_url = reverse("core:list-notes", args=[lst.id])
    assert notes_url in content
    assert "Notes" in content
    assert "Lore" in content
    assert "Gang lore." in content
    assert "Fighter lore." in content


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
    assert "Private" in content


@pytest.mark.django_db
def test_fighter_save_touches_list_modified(make_list, make_list_fighter):
    """Test that saving a fighter bumps the parent list's modified timestamp."""
    lst = make_list("Test Gang")
    fighter = make_list_fighter(lst, "Test Fighter")

    # Force a known old timestamp to avoid sleep-based flakiness
    old_time = timezone.now() - timedelta(hours=2)
    List.objects.filter(pk=lst.pk).update(modified=old_time)

    fighter.notes = "<p>Updated notes.</p>"
    fighter.save()

    lst.refresh_from_db()
    assert lst.modified > old_time


@pytest.mark.django_db
def test_fighter_narrative_save_touches_list_modified(make_list, make_list_fighter):
    """Test that saving a fighter's narrative bumps the parent list's modified timestamp."""
    lst = make_list("Test Gang")
    fighter = make_list_fighter(lst, "Test Fighter")

    old_time = timezone.now() - timedelta(hours=2)
    List.objects.filter(pk=lst.pk).update(modified=old_time)

    fighter.narrative = "<p>Updated narrative.</p>"
    fighter.save()

    lst.refresh_from_db()
    assert lst.modified > old_time


@pytest.mark.django_db
def test_fighter_notes_edit_shows_validation_errors(
    client, user, make_list, make_list_fighter
):
    """An invalid submission re-renders the form with field errors visible."""
    lst = make_list("Test Gang")
    fighter = make_list_fighter(lst, "Test Fighter")
    client.force_login(user)

    response = client.post(
        reverse("core:list-fighter-notes-edit", args=[lst.id, fighter.id]),
        {"save_roll": "x" * 11},
    )
    assert response.status_code == 200
    assert "Ensure this value has at most 10 characters" in response.content.decode()


@pytest.mark.django_db
def test_fighter_notes_edit_rejects_unsafe_return_url(
    client, user, make_list, make_list_fighter
):
    """An unsafe return_url is never rendered into the page or redirected to."""
    lst = make_list("Test Gang")
    fighter = make_list_fighter(lst, "Test Fighter")
    client.force_login(user)
    url = reverse("core:list-fighter-notes-edit", args=[lst.id, fighter.id])
    default_url = reverse("core:list-notes", args=[lst.id]) + f"#notes-{fighter.id}"

    response = client.get(f"{url}?return_url=https://evil.example.com/")
    assert response.status_code == 200
    content = response.content.decode()
    assert "evil.example.com" not in content
    assert default_url in content

    response = client.post(
        url,
        {"notes": "<p>Safe.</p>", "return_url": "https://evil.example.com/"},
    )
    assert response.status_code == 302
    assert response.url == default_url
