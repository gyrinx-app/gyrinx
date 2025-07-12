import pytest
from django.contrib.auth.models import User
from django.template import Context, Template

from gyrinx.content.models import ContentBadge
from gyrinx.core.models import CoreUserBadgeAssignment


@pytest.mark.django_db
def test_content_badge_creation():
    """Test creating a ContentBadge."""
    badge = ContentBadge.objects.create(
        name="Premium Supporter",
        display_text="Premium",
        color_class="text-bg-warning",
        icon_class="bi-star-fill",
        description="Premium supporter badge",
    )

    assert badge.name == "Premium Supporter"
    assert badge.display_text == "Premium"
    assert badge.color_class == "text-bg-warning"
    assert badge.icon_class == "bi-star-fill"
    assert badge.active is True
    assert str(badge) == "Premium Supporter"


@pytest.mark.django_db
def test_user_badge_assignment():
    """Test assigning a badge to a user."""
    user = User.objects.create_user(username="testuser", password="testpass")
    badge = ContentBadge.objects.create(
        name="VIP",
        display_text="VIP",
        color_class="text-bg-primary",
    )

    assignment = CoreUserBadgeAssignment.objects.create(
        user=user,
        badge=badge,
        is_active=True,
    )

    assert assignment.user == user
    assert assignment.badge == badge
    assert assignment.is_active is True
    assert str(assignment) == "testuser - VIP"


@pytest.mark.django_db
def test_only_one_active_badge_per_user():
    """Test that only one badge can be active per user at a time."""
    user = User.objects.create_user(username="testuser", password="testpass")
    badge1 = ContentBadge.objects.create(name="Badge1", display_text="B1")
    badge2 = ContentBadge.objects.create(name="Badge2", display_text="B2")

    # Create first badge assignment as active
    assignment1 = CoreUserBadgeAssignment.objects.create(
        user=user,
        badge=badge1,
        is_active=True,
    )

    # Create second badge assignment as active
    assignment2 = CoreUserBadgeAssignment.objects.create(
        user=user,
        badge=badge2,
        is_active=True,
    )

    # Refresh the first assignment from database
    assignment1.refresh_from_db()

    # First assignment should now be inactive
    assert assignment1.is_active is False
    assert assignment2.is_active is True


@pytest.mark.django_db
def test_badge_unique_constraint():
    """Test that a user cannot have the same badge assigned twice."""
    user = User.objects.create_user(username="testuser", password="testpass")
    badge = ContentBadge.objects.create(name="Badge", display_text="B")

    CoreUserBadgeAssignment.objects.create(user=user, badge=badge)

    # Should raise integrity error
    with pytest.raises(Exception):  # IntegrityError
        CoreUserBadgeAssignment.objects.create(user=user, badge=badge)


@pytest.mark.django_db
def test_user_badge_template_tag():
    """Test the user_badge template tag."""
    user = User.objects.create_user(username="testuser", password="testpass")
    badge = ContentBadge.objects.create(
        name="Premium",
        display_text="PRO",
        color_class="text-bg-success",
        icon_class="bi-gem",
    )

    # No badge assigned yet
    template = Template("{% load badge_tags %}{{ user.username }}{% user_badge user %}")
    rendered = template.render(Context({"user": user}))
    assert rendered == "testuser"

    # Assign inactive badge
    CoreUserBadgeAssignment.objects.create(user=user, badge=badge, is_active=False)
    rendered = template.render(Context({"user": user}))
    assert rendered == "testuser"

    # Make badge active
    assignment = CoreUserBadgeAssignment.objects.get(user=user, badge=badge)
    assignment.is_active = True
    assignment.save()

    rendered = template.render(Context({"user": user}))
    assert "PRO" in rendered
    assert "text-bg-success" in rendered
    assert "bi-gem" in rendered
    assert "rounded-pill" in rendered


@pytest.mark.django_db
def test_user_badges_template_tag():
    """Test the user_badges template tag for profile display."""
    user = User.objects.create_user(username="testuser", password="testpass")
    badge1 = ContentBadge.objects.create(
        name="Badge1",
        display_text="B1",
        color_class="text-bg-primary",
    )
    badge2 = ContentBadge.objects.create(
        name="Badge2",
        display_text="B2",
        color_class="text-bg-secondary",
    )

    # Assign both badges
    CoreUserBadgeAssignment.objects.create(user=user, badge=badge1, is_active=True)
    CoreUserBadgeAssignment.objects.create(user=user, badge=badge2, is_active=False)

    template = Template("{% load badge_tags %}{% user_badges user %}")
    rendered = template.render(Context({"user": user}))

    # Both badges should be displayed
    assert "B1" in rendered
    assert "B2" in rendered
    assert "text-bg-primary" in rendered
    assert "text-bg-secondary" in rendered
    # Active badge should have star indicator
    assert "bi-star-fill" in rendered


@pytest.mark.django_db
def test_user_with_badge_inclusion_tag():
    """Test the user_with_badge inclusion tag."""
    user = User.objects.create_user(username="testuser", password="testpass")
    badge = ContentBadge.objects.create(
        name="Special",
        display_text="SPL",
        color_class="text-bg-danger",
    )

    CoreUserBadgeAssignment.objects.create(user=user, badge=badge, is_active=True)

    # Test with link
    template = Template("{% load badge_tags %}{% user_with_badge user %}")
    rendered = template.render(Context({"user": user}))
    assert "/user/testuser" in rendered  # Should have link
    assert "testuser" in rendered
    assert "SPL" in rendered

    # Test without link
    template = Template("{% load badge_tags %}{% user_with_badge user link=False %}")
    rendered = template.render(Context({"user": user}))
    assert "/user/testuser" not in rendered  # Should not have link
    assert "testuser" in rendered
    assert "SPL" in rendered


@pytest.mark.django_db
def test_badge_admin_filter():
    """Test that only active badges appear in admin form."""
    active_badge = ContentBadge.objects.create(
        name="Active Badge",
        display_text="ACT",
        active=True,
    )
    inactive_badge = ContentBadge.objects.create(
        name="Inactive Badge",
        display_text="INA",
        active=False,
    )

    # The form should only show active badges
    from gyrinx.core.admin.user import CoreUserBadgeAssignmentForm

    form = CoreUserBadgeAssignmentForm()
    badge_queryset = form.fields["badge"].queryset

    assert active_badge in badge_queryset
    assert inactive_badge not in badge_queryset
