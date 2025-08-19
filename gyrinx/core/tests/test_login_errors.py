import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

User = get_user_model()


@pytest.mark.django_db
def test_login_shows_error_for_incorrect_username():
    """Test that login page shows error message for incorrect username."""
    client = Client()

    # Create a test user
    User.objects.create_user(username="testuser", password="testpass123")

    # Try to login with wrong username
    response = client.post(
        reverse("account_login"),
        {"login": "wronguser", "password": "testpass123"},
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
def test_login_shows_error_for_incorrect_password():
    """Test that login page shows error message for incorrect password."""
    client = Client()

    # Create a test user
    User.objects.create_user(username="testuser", password="testpass123")

    # Try to login with wrong password
    response = client.post(
        reverse("account_login"),
        {"login": "testuser", "password": "wrongpass"},
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
def test_login_shows_error_for_nonexistent_user():
    """Test that login page shows error message for non-existent user."""
    client = Client()

    # Try to login with non-existent user
    response = client.post(
        reverse("account_login"),
        {"login": "nonexistent", "password": "somepass"},
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
def test_login_successful_redirects():
    """Test that successful login redirects properly."""
    client = Client()

    # Create a test user
    User.objects.create_user(username="testuser", password="testpass123")

    # Login with correct credentials
    response = client.post(
        reverse("account_login"),
        {"login": "testuser", "password": "testpass123"},
        follow=False,
    )

    # Check that we get redirected (302 status)
    assert response.status_code == 302
