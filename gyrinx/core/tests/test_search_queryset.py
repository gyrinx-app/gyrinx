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
