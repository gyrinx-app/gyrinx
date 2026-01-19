"""Tests for ContentAvailabilityPreset model."""

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import Client
from django.urls import reverse

from gyrinx.content.models import (
    ContentAvailabilityPreset,
    ContentFighter,
    ContentHouse,
)
from gyrinx.core.models.list import List, ListFighter
from gyrinx.models import FighterCategoryChoices

User = get_user_model()


@pytest.fixture
def house():
    """Create a house with can_buy_any=True."""
    return ContentHouse.objects.create(name="Test House", can_buy_any=True)


@pytest.fixture
def other_house():
    """Create another house."""
    return ContentHouse.objects.create(name="Other House", can_buy_any=True)


@pytest.fixture
def leader_fighter(house):
    """Create a leader fighter."""
    return ContentFighter.objects.create(
        type="Test Leader",
        house=house,
        category=FighterCategoryChoices.LEADER,
        base_cost=150,
        movement="5",
        weapon_skill="3+",
        ballistic_skill="3+",
        strength="3",
        toughness="3",
        wounds="2",
        initiative="3+",
        attacks="2",
        leadership="6+",
        cool="6+",
        willpower="7+",
        intelligence="7+",
    )


@pytest.fixture
def champion_fighter(house):
    """Create a champion fighter."""
    return ContentFighter.objects.create(
        type="Test Champion",
        house=house,
        category=FighterCategoryChoices.CHAMPION,
        base_cost=100,
        movement="5",
        weapon_skill="3+",
        ballistic_skill="3+",
        strength="3",
        toughness="3",
        wounds="2",
        initiative="3+",
        attacks="2",
        leadership="6+",
        cool="6+",
        willpower="7+",
        intelligence="7+",
    )


@pytest.mark.django_db
class TestAvailabilityPresetMatching:
    """Tests for ContentAvailabilityPreset.get_preset_for() matching logic."""

    def test_no_presets_returns_none(self, leader_fighter, house):
        """When no presets exist, get_preset_for returns None."""
        result = ContentAvailabilityPreset.get_preset_for(
            fighter=leader_fighter,
            category=FighterCategoryChoices.LEADER,
            house=house,
        )
        assert result is None

    def test_category_only_preset_matches(self, leader_fighter, house):
        """A category-only preset matches fighters of that category."""
        preset = ContentAvailabilityPreset.objects.create(
            category=FighterCategoryChoices.LEADER,
            availability_types=["C", "R"],
            max_availability_level=11,
        )

        result = ContentAvailabilityPreset.get_preset_for(
            fighter=leader_fighter,
            category=FighterCategoryChoices.LEADER,
            house=house,
        )

        assert result == preset
        assert result.availability_types_list == ["C", "R"]
        assert result.max_availability_level == 11

    def test_house_only_preset_matches(self, leader_fighter, house):
        """A house-only preset matches fighters in that house."""
        preset = ContentAvailabilityPreset.objects.create(
            house=house,
            availability_types=["C"],
            max_availability_level=8,
        )

        result = ContentAvailabilityPreset.get_preset_for(
            fighter=leader_fighter,
            category=FighterCategoryChoices.LEADER,
            house=house,
        )

        assert result == preset

    def test_fighter_only_preset_matches(self, leader_fighter, house):
        """A fighter-specific preset matches that specific fighter."""
        preset = ContentAvailabilityPreset.objects.create(
            fighter=leader_fighter,
            availability_types=["C", "R", "I"],
            max_availability_level=15,
        )

        result = ContentAvailabilityPreset.get_preset_for(
            fighter=leader_fighter,
            category=FighterCategoryChoices.LEADER,
            house=house,
        )

        assert result == preset

    def test_category_house_preset_matches(self, leader_fighter, house):
        """A category+house preset matches fighters of that category in that house."""
        preset = ContentAvailabilityPreset.objects.create(
            category=FighterCategoryChoices.LEADER,
            house=house,
            availability_types=["C", "R"],
            max_availability_level=12,
        )

        result = ContentAvailabilityPreset.get_preset_for(
            fighter=leader_fighter,
            category=FighterCategoryChoices.LEADER,
            house=house,
        )

        assert result == preset

    def test_specificity_fighter_beats_category(self, leader_fighter, house):
        """Fighter-specific preset beats category-only preset."""
        ContentAvailabilityPreset.objects.create(
            category=FighterCategoryChoices.LEADER,
            availability_types=["C"],
            max_availability_level=8,
        )

        fighter_preset = ContentAvailabilityPreset.objects.create(
            fighter=leader_fighter,
            availability_types=["C", "R", "I"],
            max_availability_level=15,
        )

        result = ContentAvailabilityPreset.get_preset_for(
            fighter=leader_fighter,
            category=FighterCategoryChoices.LEADER,
            house=house,
        )

        assert result == fighter_preset

    def test_specificity_category_house_beats_category(self, leader_fighter, house):
        """Category+house preset beats category-only preset."""
        ContentAvailabilityPreset.objects.create(
            category=FighterCategoryChoices.LEADER,
            availability_types=["C"],
            max_availability_level=8,
        )

        category_house_preset = ContentAvailabilityPreset.objects.create(
            category=FighterCategoryChoices.LEADER,
            house=house,
            availability_types=["C", "R"],
            max_availability_level=12,
        )

        result = ContentAvailabilityPreset.get_preset_for(
            fighter=leader_fighter,
            category=FighterCategoryChoices.LEADER,
            house=house,
        )

        assert result == category_house_preset

    def test_specificity_three_fields_beats_two(self, leader_fighter, house):
        """Fighter+category+house preset beats category+house preset."""
        ContentAvailabilityPreset.objects.create(
            category=FighterCategoryChoices.LEADER,
            house=house,
            availability_types=["C", "R"],
            max_availability_level=12,
        )

        full_preset = ContentAvailabilityPreset.objects.create(
            fighter=leader_fighter,
            category=FighterCategoryChoices.LEADER,
            house=house,
            availability_types=["C", "R", "I", "E"],
            max_availability_level=20,
        )

        result = ContentAvailabilityPreset.get_preset_for(
            fighter=leader_fighter,
            category=FighterCategoryChoices.LEADER,
            house=house,
        )

        assert result == full_preset

    def test_higher_specificity_wins(self, leader_fighter, house, other_house):
        """Higher specificity preset wins over lower specificity preset."""
        # Create category-only preset (specificity=1)
        ContentAvailabilityPreset.objects.create(
            category=FighterCategoryChoices.LEADER,
            availability_types=["C"],
            max_availability_level=5,
        )

        # Create category+house preset (specificity=2)
        more_specific_preset = ContentAvailabilityPreset.objects.create(
            category=FighterCategoryChoices.LEADER,
            house=house,
            availability_types=["C", "R"],
            max_availability_level=10,
        )

        # Also create house-only (specificity=1, same as category-only)
        # but for a different house so it won't match
        ContentAvailabilityPreset.objects.create(
            house=other_house,
            availability_types=["I"],
            max_availability_level=3,
        )

        result = ContentAvailabilityPreset.get_preset_for(
            fighter=leader_fighter,
            category=FighterCategoryChoices.LEADER,
            house=house,
        )

        # category+house (specificity=2) beats category-only (specificity=1)
        assert result == more_specific_preset

    def test_no_match_when_category_differs(self, champion_fighter, house):
        """Category-specific preset doesn't match different category."""
        ContentAvailabilityPreset.objects.create(
            category=FighterCategoryChoices.LEADER,
            availability_types=["C", "R"],
            max_availability_level=11,
        )

        result = ContentAvailabilityPreset.get_preset_for(
            fighter=champion_fighter,
            category=FighterCategoryChoices.CHAMPION,
            house=house,
        )

        # Should not match since preset is for LEADER, not CHAMPION
        assert result is None

    def test_no_match_when_house_differs(self, leader_fighter, house, other_house):
        """House-specific preset doesn't match different house."""
        ContentAvailabilityPreset.objects.create(
            house=other_house,
            availability_types=["C", "R"],
            max_availability_level=11,
        )

        result = ContentAvailabilityPreset.get_preset_for(
            fighter=leader_fighter,
            category=FighterCategoryChoices.LEADER,
            house=house,
        )

        # Should not match since preset is for other_house
        assert result is None


@pytest.mark.django_db
class TestAvailabilityPresetConstraints:
    """Tests for ContentAvailabilityPreset uniqueness constraints."""

    def test_unique_together_constraint(self, leader_fighter, house):
        """Cannot create duplicate presets with same fighter/category/house."""
        ContentAvailabilityPreset.objects.create(
            fighter=leader_fighter,
            category=FighterCategoryChoices.LEADER,
            house=house,
            availability_types=["C", "R"],
        )

        with pytest.raises(IntegrityError):
            ContentAvailabilityPreset.objects.create(
                fighter=leader_fighter,
                category=FighterCategoryChoices.LEADER,
                house=house,
                availability_types=["C"],
            )

    def test_different_combinations_allowed(self, leader_fighter, house):
        """Different field combinations are allowed."""
        # Category only
        ContentAvailabilityPreset.objects.create(
            category=FighterCategoryChoices.LEADER,
            availability_types=["C", "R"],
        )

        # House only
        ContentAvailabilityPreset.objects.create(
            house=house,
            availability_types=["C"],
        )

        # Category + house
        ContentAvailabilityPreset.objects.create(
            category=FighterCategoryChoices.LEADER,
            house=house,
            availability_types=["C", "R"],
        )

        # All should exist
        assert ContentAvailabilityPreset.objects.count() == 3

    def test_all_null_fields_rejected(self):
        """Cannot create preset with all null fields (fighter, category, house)."""
        from django.core.exceptions import ValidationError

        preset = ContentAvailabilityPreset(availability_types=["C", "R"])
        with pytest.raises(ValidationError) as exc_info:
            preset.full_clean()
        assert "At least one of fighter, category, or house" in str(exc_info.value)


@pytest.mark.django_db
class TestAvailabilityPresetViewIntegration:
    """Tests for view integration with availability presets."""

    def test_redirect_includes_preset_values(self, house, leader_fighter):
        """When redirecting can_buy_any house, preset values are in redirect URL."""
        user = User.objects.create_user(username="testuser", password="password")

        # Create a preset for leaders
        ContentAvailabilityPreset.objects.create(
            category=FighterCategoryChoices.LEADER,
            availability_types=["C", "R"],
            max_availability_level=11,
        )

        # Create list and fighter
        lst = List.objects.create(
            owner=user,
            name="Test List",
            content_house=house,
        )
        list_fighter = ListFighter.objects.create(
            list=lst,
            content_fighter=leader_fighter,
            name="Test Leader",
            owner=user,
        )

        client = Client()
        client.login(username="testuser", password="password")

        url = reverse("core:list-fighter-gear-edit", args=[lst.id, list_fighter.id])
        response = client.get(url)

        # Redirect includes filter=all and preset values
        assert response.status_code == 302
        assert "filter=all" in response.url
        assert "al=C" in response.url
        assert "al=R" in response.url
        assert "mal=11" in response.url

    def test_redirect_without_preset_uses_default(self, house, leader_fighter):
        """When no preset exists, redirect only includes filter=all."""
        user = User.objects.create_user(username="testuser2", password="password")

        lst = List.objects.create(
            owner=user,
            name="Test List",
            content_house=house,
        )
        list_fighter = ListFighter.objects.create(
            list=lst,
            content_fighter=leader_fighter,
            name="Test Leader",
            owner=user,
        )

        client = Client()
        client.login(username="testuser2", password="password")

        url = reverse("core:list-fighter-gear-edit", args=[lst.id, list_fighter.id])
        response = client.get(url)

        assert response.status_code == 302
        # Only filter=all, no al or mal
        assert response.url == f"{url}?filter=all"

    def test_explicit_filters_override_preset(self, house, leader_fighter):
        """User-provided al/mal filters are preserved, not overwritten by preset."""
        user = User.objects.create_user(username="testuser3", password="password")

        # Create a preset
        ContentAvailabilityPreset.objects.create(
            category=FighterCategoryChoices.LEADER,
            availability_types=["C", "R"],
            max_availability_level=11,
        )

        lst = List.objects.create(
            owner=user,
            name="Test List",
            content_house=house,
        )
        list_fighter = ListFighter.objects.create(
            list=lst,
            content_fighter=leader_fighter,
            name="Test Leader",
            owner=user,
        )

        client = Client()
        client.login(username="testuser3", password="password")

        # Access with explicit al parameter
        url = reverse("core:list-fighter-gear-edit", args=[lst.id, list_fighter.id])
        response = client.get(url, {"al": "I"})

        assert response.status_code == 302
        # User's al=I should be preserved in redirect, not overwritten
        assert "al=I" in response.url
        # Preset values should NOT be added since user provided explicit al
        assert "mal=11" not in response.url


@pytest.mark.django_db
class TestAvailabilityPresetStr:
    """Tests for __str__ representation."""

    def test_str_category_only(self):
        """Category-only preset has correct string representation."""
        preset = ContentAvailabilityPreset.objects.create(
            category=FighterCategoryChoices.LEADER,
            availability_types=["C", "R"],
            max_availability_level=11,
        )
        assert "Category: Leader" in str(preset)
        assert "C, R" in str(preset)
        assert "max level 11" in str(preset)

    def test_str_house_only(self):
        """House-only preset has correct string representation."""
        house = ContentHouse.objects.create(name="Test House")
        preset = ContentAvailabilityPreset.objects.create(
            house=house,
            availability_types=["C"],
        )
        assert "House: Test House" in str(preset)

    def test_str_combined(self):
        """Combined preset has correct string representation."""
        house = ContentHouse.objects.create(name="Test House")
        preset = ContentAvailabilityPreset.objects.create(
            category=FighterCategoryChoices.CHAMPION,
            house=house,
            availability_types=["C", "R", "I"],
            max_availability_level=10,
        )
        assert "Category: Champion" in str(preset)
        assert "House: Test House" in str(preset)
        assert "C, R, I" in str(preset)
        assert "max level 10" in str(preset)
