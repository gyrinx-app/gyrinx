import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

User = get_user_model()


@pytest.mark.django_db
def test_login_shows_error_for_incorrect_username(monkeypatch):
    """Test that login page shows error message for incorrect username."""

    # Mock the reCAPTCHA validation to always pass
    def mock_validate(self, value):
        return True

    monkeypatch.setattr(
        "django_recaptcha.fields.ReCaptchaField.validate", mock_validate
    )

    client = Client()

    # Create a test user
    User.objects.create_user(username="testuser", password="testpass123")

    # Try to login with wrong username
    response = client.post(
        reverse("account_login"),
        {"login": "wronguser", "password": "testpass123", "captcha": "dummy"},
    )

    # Check that we stay on the login page
    assert response.status_code == 200

    # Check that error message is displayed
    assert (
        b"The username and/or password you specified are not correct"
        in response.content
        or b"The login and/or password you specified are not correct"
        in response.content
        or b"The email address and/or password you specified are not correct"
        in response.content
    )


@pytest.mark.django_db
def test_login_shows_error_for_incorrect_password(monkeypatch):
    """Test that login page shows error message for incorrect password."""

    # Mock the reCAPTCHA validation to always pass
    def mock_validate(self, value):
        return True

    monkeypatch.setattr(
        "django_recaptcha.fields.ReCaptchaField.validate", mock_validate
    )

    client = Client()

    # Create a test user
    User.objects.create_user(username="testuser", password="testpass123")

    # Try to login with wrong password
    response = client.post(
        reverse("account_login"),
        {"login": "testuser", "password": "wrongpass", "captcha": "dummy"},
    )

    # Check that we stay on the login page
    assert response.status_code == 200

    # Check that error message is displayed
    assert (
        b"The username and/or password you specified are not correct"
        in response.content
        or b"The login and/or password you specified are not correct"
        in response.content
        or b"The email address and/or password you specified are not correct"
        in response.content
    )


@pytest.mark.django_db
def test_login_shows_error_for_nonexistent_user(monkeypatch):
    """Test that login page shows error message for non-existent user."""

    # Mock the reCAPTCHA validation to always pass
    def mock_validate(self, value):
        return True

    monkeypatch.setattr(
        "django_recaptcha.fields.ReCaptchaField.validate", mock_validate
    )

    client = Client()

    # Try to login with non-existent user
    response = client.post(
        reverse("account_login"),
        {"login": "nonexistent", "password": "somepass", "captcha": "dummy"},
    )

    # Check that we stay on the login page
    assert response.status_code == 200

    # Check that error message is displayed
    assert (
        b"The username and/or password you specified are not correct"
        in response.content
        or b"The login and/or password you specified are not correct"
        in response.content
        or b"The email address and/or password you specified are not correct"
        in response.content
    )


@pytest.mark.django_db
def test_login_successful_redirects(monkeypatch):
    """Test that successful login redirects properly."""

    # Mock the reCAPTCHA validation to always pass
    def mock_validate(self, value):
        return True

    monkeypatch.setattr(
        "django_recaptcha.fields.ReCaptchaField.validate", mock_validate
    )

    client = Client()

    # Create a test user
    User.objects.create_user(username="testuser", password="testpass123")

    # Login with correct credentials
    response = client.post(
        reverse("account_login"),
        {"login": "testuser", "password": "testpass123", "captcha": "dummy"},
        follow=False,
    )

    # Check that we get redirected (302 status)
    assert response.status_code == 302
