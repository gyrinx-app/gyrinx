import pytest

from gyrinx.content.models import ContentBadge


@pytest.mark.django_db
def test_content_badge_model():
    """Test ContentBadge model creation and validation."""
    badge = ContentBadge.objects.create(
        name="Test Badge",
        display_text="TEST",
        color_class="text-bg-primary",
        icon_class="bi-award",
        description="A test badge",
    )

    assert badge.name == "Test Badge"
    assert badge.display_text == "TEST"
    assert badge.color_class == "text-bg-primary"
    assert badge.icon_class == "bi-award"
    assert badge.description == "A test badge"
    assert badge.active is True


@pytest.mark.django_db
def test_content_badge_str_representation():
    """Test string representation of ContentBadge."""
    badge = ContentBadge.objects.create(
        name="Gold Member",
        display_text="GOLD",
    )

    assert str(badge) == "Gold Member"


@pytest.mark.django_db
def test_content_badge_unique_name():
    """Test that badge names must be unique."""
    ContentBadge.objects.create(
        name="Unique Badge",
        display_text="UNQ",
    )

    # Should raise integrity error for duplicate name
    with pytest.raises(Exception):  # IntegrityError
        ContentBadge.objects.create(
            name="Unique Badge",
            display_text="UNQ2",
        )


@pytest.mark.django_db
def test_content_badge_default_values():
    """Test default values for ContentBadge."""
    badge = ContentBadge.objects.create(
        name="Default Badge",
        display_text="DEF",
    )

    assert badge.color_class == "text-bg-secondary"
    assert badge.icon_class == ""
    assert badge.description == ""
    assert badge.active is True


@pytest.mark.django_db
def test_content_badge_color_class_choices():
    """Test that all allowed color classes work."""
    color_classes = [
        "text-bg-primary",
        "text-bg-secondary",
        "text-bg-success",
        "text-bg-danger",
        "text-bg-warning",
        "text-bg-info",
        "text-bg-light",
        "text-bg-dark",
    ]

    for i, color_class in enumerate(color_classes):
        badge = ContentBadge.objects.create(
            name=f"Badge {i}",
            display_text=f"B{i}",
            color_class=color_class,
        )
        assert badge.color_class == color_class


@pytest.mark.django_db
def test_content_badge_ordering():
    """Test that badges are ordered by name."""
    badge_c = ContentBadge.objects.create(name="C Badge", display_text="C")
    badge_a = ContentBadge.objects.create(name="A Badge", display_text="A")
    badge_b = ContentBadge.objects.create(name="B Badge", display_text="B")

    badges = ContentBadge.objects.all()
    assert list(badges) == [badge_a, badge_b, badge_c]
