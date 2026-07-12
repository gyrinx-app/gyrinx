"""Shared fixtures for core app tests.

Fixtures here are scoped to ``gyrinx/core/tests/``. Root-level fixtures live in
``gyrinx/conftest.py`` and are available everywhere; this file adds fixtures
that are only useful inside core-app tests so we don't have to repeat them in
every file.
"""

import pytest
from django.test import Client

from gyrinx.content.models import ContentEquipmentCategory


@pytest.fixture
def logged_in_client(user):
    """A test client logged in as the canonical ``user`` fixture.

    Use this instead of the bare ``client`` fixture (which is anonymous by
    default) for views that require authentication.
    """
    c = Client()
    c.force_login(user)
    return c


@pytest.fixture
def weapon_category(db):
    """The shared "Basic Weapons" equipment category.

    Several tests need a weapon category to attach equipment to but don't care
    about its specifics. Tests that need a *distinct* category (e.g. to avoid
    collisions with other fixtures) should define their own local fixture.
    """
    cat, _ = ContentEquipmentCategory.objects.get_or_create(
        name="Basic Weapons",
        defaults={"group": "Weapons & Ammo"},
    )
    return cat
