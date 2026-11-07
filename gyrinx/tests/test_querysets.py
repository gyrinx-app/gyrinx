"""Full-text and substring search across scalar and related fields."""

import pytest
from django.contrib.auth import get_user_model

from gyrinx.querysets import search_queryset
from n23.content.models import ContentHouse

User = get_user_model()


@pytest.mark.django_db
def test_partial_match():

    ContentHouse.objects.create(name="Scavvies")
    ContentHouse.objects.create(name="Goliath")

    results = search_queryset(ContentHouse.objects.all(), "scav", ["name"])
    names = list(results.values_list("name", flat=True))
    assert "Scavvies" in names
    assert "Goliath" not in names


@pytest.mark.django_db
def test_exact_match():

    ContentHouse.objects.create(name="Goliath")
    ContentHouse.objects.create(name="Escher")

    results = search_queryset(ContentHouse.objects.all(), "Goliath", ["name"])
    names = list(results.values_list("name", flat=True))
    assert "Goliath" in names
    assert "Escher" not in names


@pytest.mark.django_db
def test_empty_query_returns_all():

    ContentHouse.objects.create(name="Goliath")
    ContentHouse.objects.create(name="Escher")

    qs = ContentHouse.objects.all()
    results = search_queryset(qs, "", ["name"])
    assert results.count() == qs.count()


@pytest.mark.django_db
def test_none_query_returns_all():

    ContentHouse.objects.create(name="Goliath")

    qs = ContentHouse.objects.all()
    results = search_queryset(qs, None, ["name"])
    assert results.count() == qs.count()


@pytest.mark.django_db
def test_whitespace_query_returns_all():

    ContentHouse.objects.create(name="Goliath")

    qs = ContentHouse.objects.all()
    results = search_queryset(qs, "   ", ["name"])
    assert results.count() == qs.count()


def test_empty_fields_raises():

    with pytest.raises(ValueError, match="at least one field"):
        search_queryset(User.objects.none(), "test", [])


@pytest.mark.django_db
def test_multiple_fields():

    ContentHouse.objects.create(name="Goliath")

    results = search_queryset(ContentHouse.objects.all(), "Goliath", ["name"])
    assert results.count() == 1


@pytest.mark.django_db
def test_no_duplicates():

    ContentHouse.objects.create(name="Test House")

    results = search_queryset(ContentHouse.objects.all(), "test", ["name"])
    assert results.count() == 1


@pytest.mark.django_db
def test_no_duplicates_with_reverse_fk_fields():
    """Return equipment once even when related weapon profiles multiply search joins.

    Full-row DISTINCT cannot deduplicate per-profile search-vector annotations.
    """
    from n23.content.models import (
        ContentEquipment,
        ContentEquipmentCategory,
        ContentWeaponProfile,
    )

    category = ContentEquipmentCategory.objects.create(
        name="Test Weapons", group="Weapons & Ammo"
    )
    shotgun = ContentEquipment.objects.create(
        name="Shotgun", category=category, cost="20"
    )
    for profile_name in ["Short Range", "Long Range", "Template"]:
        ContentWeaponProfile.objects.create(
            equipment=shotgun, name=profile_name, cost=0
        )

    results = search_queryset(
        ContentEquipment.objects.all(),
        "shotgun",
        ["name", "category__name", "contentweaponprofile__name"],
    )
    assert list(results.values_list("id", flat=True)).count(shotgun.id) == 1
    assert results.count() == 1


@pytest.mark.django_db
def test_no_duplicates_with_m2m_through_reverse_fk():
    """Return equipment once when profiles and their traits multiply the joined rows."""
    from n23.content.models import (
        ContentEquipment,
        ContentEquipmentCategory,
        ContentWeaponProfile,
        ContentWeaponTrait,
    )

    category = ContentEquipmentCategory.objects.create(
        name="Test Heavy Weapons", group="Weapons & Ammo"
    )
    launcher = ContentEquipment.objects.create(
        name="Grenade Launcher", category=category, cost="55"
    )

    traits = [
        ContentWeaponTrait.objects.create(name=name)
        for name in ['Blast (3")', "Knockback", "Rapid Fire (1)", "Scarce"]
    ]

    # Three profiles with four traits produce twelve joined records.
    for profile_name in ["Frag", "Krak", "Smoke"]:
        profile = ContentWeaponProfile.objects.create(
            equipment=launcher, name=profile_name, cost=0
        )
        profile.traits.set(traits)

    results = search_queryset(
        ContentEquipment.objects.all(),
        "grenade",
        [
            "name",
            "category__name",
            "contentweaponprofile__name",
            "contentweaponprofile__traits__name",
        ],
    )
    assert list(results.values_list("id", flat=True)).count(launcher.id) == 1
    assert results.count() == 1


@pytest.mark.django_db
def test_search_across_related_fields_still_finds_matches():

    from n23.content.models import (
        ContentEquipment,
        ContentEquipmentCategory,
        ContentWeaponProfile,
        ContentWeaponTrait,
    )

    category = ContentEquipmentCategory.objects.create(
        name="Test Pistols", group="Weapons & Ammo"
    )
    pistol = ContentEquipment.objects.create(
        name="Stub Gun", category=category, cost="5"
    )
    profile = ContentWeaponProfile.objects.create(equipment=pistol, name="", cost=0)
    knockback = ContentWeaponTrait.objects.create(name="Knockback Test")
    profile.traits.add(knockback)

    results = search_queryset(
        ContentEquipment.objects.all(),
        "knockback",
        [
            "name",
            "category__name",
            "contentweaponprofile__name",
            "contentweaponprofile__traits__name",
        ],
    )
    assert results.count() == 1
    assert results.first().id == pistol.id
