"""Tests for the search_queryset() utility."""

import pytest
from django.contrib.auth import get_user_model

from gyrinx.content.models import ContentHouse
from gyrinx.core.utils import search_queryset

User = get_user_model()


@pytest.mark.django_db
def test_partial_match():
    """Partial string matches via icontains fallback."""
    ContentHouse.objects.create(name="Scavvies")
    ContentHouse.objects.create(name="Goliath")

    results = search_queryset(ContentHouse.objects.all(), "scav", ["name"])
    names = list(results.values_list("name", flat=True))
    assert "Scavvies" in names
    assert "Goliath" not in names


@pytest.mark.django_db
def test_exact_match():
    """Exact string matches work."""
    ContentHouse.objects.create(name="Goliath")
    ContentHouse.objects.create(name="Escher")

    results = search_queryset(ContentHouse.objects.all(), "Goliath", ["name"])
    names = list(results.values_list("name", flat=True))
    assert "Goliath" in names
    assert "Escher" not in names


@pytest.mark.django_db
def test_empty_query_returns_all():
    """Empty query returns the queryset unchanged."""
    ContentHouse.objects.create(name="Goliath")
    ContentHouse.objects.create(name="Escher")

    qs = ContentHouse.objects.all()
    results = search_queryset(qs, "", ["name"])
    assert results.count() == qs.count()


@pytest.mark.django_db
def test_none_query_returns_all():
    """None query returns the queryset unchanged."""
    ContentHouse.objects.create(name="Goliath")

    qs = ContentHouse.objects.all()
    results = search_queryset(qs, None, ["name"])
    assert results.count() == qs.count()


@pytest.mark.django_db
def test_whitespace_query_returns_all():
    """Whitespace-only query is treated as empty."""
    ContentHouse.objects.create(name="Goliath")

    qs = ContentHouse.objects.all()
    results = search_queryset(qs, "   ", ["name"])
    assert results.count() == qs.count()


def test_empty_fields_raises():
    """Empty fields list raises ValueError."""
    with pytest.raises(ValueError, match="at least one field"):
        search_queryset(User.objects.none(), "test", [])


@pytest.mark.django_db
def test_multiple_fields():
    """Search matches across multiple fields."""
    ContentHouse.objects.create(name="Goliath")

    results = search_queryset(ContentHouse.objects.all(), "Goliath", ["name"])
    assert results.count() == 1


@pytest.mark.django_db
def test_no_duplicates():
    """Results don't contain duplicates even with multi-field matches."""
    ContentHouse.objects.create(name="Test House")

    results = search_queryset(ContentHouse.objects.all(), "test", ["name"])
    # Should be exactly 1, not duplicated
    assert results.count() == 1


@pytest.mark.django_db
def test_no_duplicates_with_reverse_fk_fields():
    """Searching across reverse FK fields must not produce duplicate results.

    When search_fields include reverse-FK lookups like
    ``contentweaponprofile__name``, the SQL JOINs multiply rows.  Each
    weapon profile contributes a different tsvector annotation, so
    ``SELECT DISTINCT`` over the annotated queryset sees every row as
    unique — returning the same equipment multiple times.

    This test creates one piece of equipment with several weapon
    profiles and asserts that searching returns it exactly once.
    """
    from gyrinx.content.models import (
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
    # Create multiple weapon profiles — these generate the JOINs that
    # cause duplicate rows when searching by contentweaponprofile__name.
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
    """Searching across M2M fields via a reverse FK must not duplicate results.

    This is the more extreme variant: ``contentweaponprofile__traits__name``
    traverses a reverse FK **and** an M2M, producing a Cartesian product
    of profiles × traits in the JOIN.  A weapon with 3 profiles each
    having 4 traits should still appear exactly once in search results.
    """
    from gyrinx.content.models import (
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

    # Create 3 profiles, each with all 4 traits → 3×4 = 12 joined rows
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
    """Searching by a trait name still returns the correct equipment."""
    from gyrinx.content.models import (
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

    # Searching by trait name should still return the equipment
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
