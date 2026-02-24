"""Tests for the house filter dropdown on the lists page.

Ensures that the house dropdown shows all houses for gangs that could appear
in the search results, including houses from custom content packs.
"""

import pytest
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from gyrinx.content.models import ContentHouse
from gyrinx.core.models.list import List
from gyrinx.core.models.pack import CustomContentPackItem


@pytest.mark.django_db
def test_lists_page_house_dropdown_includes_pack_houses(
    client, user, make_list, make_content_house, make_pack
):
    """Pack-defined houses should appear in the house dropdown on the lists page."""
    # Create a pack house (a house that belongs to a content pack)
    pack_house = make_content_house("Pack House")
    pack = make_pack("House Pack")
    ct = ContentType.objects.get_for_model(ContentHouse)
    CustomContentPackItem.objects.create(
        pack=pack,
        content_type=ct,
        object_id=pack_house.pk,
        owner=pack.owner,
    )

    # Create a list using the pack house
    lst = make_list("Pack Gang", content_house=pack_house)
    lst.packs.add(pack)

    client.force_login(user)
    response = client.get(reverse("core:lists"))

    # The pack house should appear in the houses context
    houses = list(response.context["houses"])
    house_names = [h.name for h in houses]
    assert "Pack House" in house_names


@pytest.mark.django_db
def test_lists_page_house_dropdown_only_shows_relevant_houses(
    client, user, content_house, make_list, make_content_house
):
    """House dropdown should only show houses that have matching lists."""
    # Create a list using content_house
    make_list("My Gang")

    # Create an unrelated house with no lists
    make_content_house("Unused House")

    client.force_login(user)
    response = client.get(reverse("core:lists"))

    houses = list(response.context["houses"])
    house_names = [h.name for h in houses]

    # content_house should appear (has a list)
    assert content_house.name in house_names

    # Unused house should NOT appear (no lists)
    assert "Unused House" not in house_names


@pytest.mark.django_db
def test_lists_page_house_filter_still_works(
    client, user, content_house, make_list, make_content_house
):
    """Filtering by house should still work correctly."""
    other_house = make_content_house("Other House")

    make_list("Gang A")
    make_list("Gang B", content_house=other_house)

    client.force_login(user)

    # Filter by content_house only
    response = client.get(
        reverse("core:lists"), {"house": str(content_house.id), "my": "1"}
    )
    lists = list(response.context["lists"])
    assert len(lists) == 1
    assert lists[0].name == "Gang A"


@pytest.mark.django_db
def test_dashboard_house_dropdown_includes_pack_houses(
    client, user, make_list, make_content_house, make_pack
):
    """Pack-defined houses should appear in the dashboard house dropdown."""
    # Create a pack house
    pack_house = make_content_house("Dashboard Pack House")
    pack = make_pack("Dashboard Pack")
    ct = ContentType.objects.get_for_model(ContentHouse)
    CustomContentPackItem.objects.create(
        pack=pack,
        content_type=ct,
        object_id=pack_house.pk,
        owner=pack.owner,
    )

    # Create a list using the pack house
    lst = make_list("Dashboard Pack Gang", content_house=pack_house)
    lst.packs.add(pack)

    client.force_login(user)
    response = client.get(reverse("core:index"))

    houses = list(response.context["houses"])
    house_names = [h.name for h in houses]
    assert "Dashboard Pack House" in house_names


@pytest.mark.django_db
def test_lists_page_public_view_shows_houses_for_public_lists(
    client, user, content_house, make_list, make_content_house, make_user
):
    """When viewing public lists, houses should include those from public lists."""
    other_house = make_content_house("Public House")
    other_user = make_user("otheruser", "password")

    # Create a public list with other_house
    List.objects.create_with_facts(
        name="Public Gang",
        content_house=other_house,
        owner=other_user,
        public=True,
    )

    client.force_login(user)
    # View public lists (my=0)
    response = client.get(reverse("core:lists"), {"my": "0"})

    houses = list(response.context["houses"])
    house_names = [h.name for h in houses]
    assert "Public House" in house_names
