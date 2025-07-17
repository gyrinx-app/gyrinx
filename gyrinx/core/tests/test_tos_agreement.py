import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from gyrinx.core.models.auth import UserProfile


@pytest.mark.django_db
def test_signup_form_has_tos_checkbox():
    """Test that the signup form includes the ToS agreement checkbox."""
    client = Client()
    response = client.get(reverse("account_signup"))
    assert response.status_code == 200
    assert "tos_agreement" in response.context["form"].fields
    assert "Terms of Use" in response.content.decode()


@pytest.mark.django_db
def test_signup_requires_tos_agreement(monkeypatch):
    """Test that signing up requires agreeing to the ToS."""

    # Mock the reCAPTCHA validation to always pass
    def mock_validate(self, value):
        return True

    monkeypatch.setattr(
        "django_recaptcha.fields.ReCaptchaField.validate", mock_validate
    )

    client = Client()
    data = {
        "username": "testuser",
        "email": "test@example.com",
        "password1": "complex_password_123!",
        "password2": "complex_password_123!",
        "captcha": "dummy",  # Any value will work with our mock
        # Intentionally not including tos_agreement
    }
    response = client.post(reverse("account_signup"), data, follow=True)

    # Should not create user without ToS agreement
    User = get_user_model()
    assert User.objects.filter(username="testuser").count() == 0
    assert "You must agree to the Terms of Use" in response.content.decode()


@pytest.mark.django_db
def test_signup_with_tos_agreement_creates_profile(settings, monkeypatch):
    """Test that agreeing to ToS creates user profile with timestamp."""

    # Mock the reCAPTCHA validation to always pass
    def mock_validate(self, value):
        return True

    monkeypatch.setattr(
        "django_recaptcha.fields.ReCaptchaField.validate", mock_validate
    )

    client = Client()
    before_signup = timezone.now()

    data = {
        "username": "testuser",
        "email": "test@example.com",
        "password1": "complex_password_123!",
        "password2": "complex_password_123!",
        "tos_agreement": "on",  # Checkbox is checked
        "captcha": "dummy",  # Any value will work with our mock
    }

    response = client.post(reverse("account_signup"), data, follow=True)

    # Check if there are form errors
    if hasattr(response, "context") and "form" in response.context:
        form = response.context["form"]
        if form.errors:
            print(f"Form errors: {form.errors}")
            print(f"Response status: {response.status_code}")
            print(f"Response content: {response.content.decode()[:500]}")

    # User should be created
    User = get_user_model()
    users = User.objects.filter(username="testuser")
    assert users.count() == 1, f"Expected 1 user, found {users.count()}"
    user = users.first()

    # Profile should be created with ToS agreement timestamp
    assert hasattr(user, "profile")
    assert user.profile.tos_agreed_at is not None
    assert user.profile.tos_agreed_at >= before_signup
    assert user.profile.tos_agreed_at <= timezone.now()


@pytest.mark.django_db
def test_user_profile_str_method():
    """Test the UserProfile __str__ method."""
    User = get_user_model()
    user = User.objects.create_user(username="testuser", email="test@example.com")
    profile = UserProfile.objects.create(user=user)

    assert str(profile) == "testuser profile"


@pytest.mark.django_db
def test_record_tos_agreement_method():
    """Test the record_tos_agreement method."""
    User = get_user_model()
    user = User.objects.create_user(username="testuser", email="test@example.com")
    profile = UserProfile.objects.create(user=user)

    # Initially no agreement
    assert profile.tos_agreed_at is None

    # Record agreement
    before = timezone.now()
    profile.record_tos_agreement()
    after = timezone.now()

    # Should have timestamp
    profile.refresh_from_db()
    assert profile.tos_agreed_at is not None
    assert before <= profile.tos_agreed_at <= after
