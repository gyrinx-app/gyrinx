"""Tests for the lightweight fighter switcher / minimal active-fighter query."""

import pytest

from gyrinx.content.models import FighterCategoryChoices


@pytest.mark.django_db
def test_active_fighters_minimal_cached_returns_names(
    make_list, make_list_fighter, content_fighter
):
    lst = make_list("Test Gang")
    f1 = make_list_fighter(lst, "Alpha")
    f2 = make_list_fighter(lst, "Bravo")

    rows = lst.active_fighters_minimal_cached

    assert isinstance(rows, list)
    ids = {row["id"] for row in rows}
    assert ids == {f1.id, f2.id}

    by_id = {row["id"]: row for row in rows}
    assert by_id[f1.id]["name"] == "Alpha"
    # content_fighter_name mirrors ContentFighter.name ("Type (Category)").
    expected = (
        f"{content_fighter.type} "
        f"({FighterCategoryChoices[content_fighter.category].label})"
    )
    assert by_id[f1.id]["content_fighter_name"] == expected


@pytest.mark.django_db
def test_active_fighters_minimal_cached_excludes_archived_and_stash(
    make_list, make_list_fighter, make_content_fighter, content_house
):
    lst = make_list("Test Gang")
    active = make_list_fighter(lst, "Active")
    archived = make_list_fighter(lst, "Archived")
    archived.archived = True
    archived.save()

    stash_cf = make_content_fighter(
        type="Stash",
        category=FighterCategoryChoices.STASH,
        house=content_house,
        base_cost=0,
        is_stash=True,
    )
    make_list_fighter(lst, "Stash", content_fighter=stash_cf)

    ids = {row["id"] for row in lst.active_fighters_minimal_cached}
    assert ids == {active.id}


@pytest.mark.django_db
def test_fighter_switcher_renders_minimal(client, user, make_list, make_list_fighter):
    lst = make_list("Test Gang")
    f1 = make_list_fighter(lst, "Alpha")
    f2 = make_list_fighter(lst, "Bravo")

    client.force_login(user)
    resp = client.get(f"/list/{lst.id}/fighter/{f1.id}")
    assert resp.status_code == 200
    content = resp.content.decode()
    # Switcher dropdown shows both fighter names.
    assert "Alpha" in content
    assert "Bravo" in content
    assert str(f2.id) in content
