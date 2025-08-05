import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from gyrinx.content.models import ContentHouse
from gyrinx.core.models import List


@pytest.mark.django_db
def test_new_list_form_errors_display():
    """Test that form validation errors are displayed to the user in the new_list view"""
    # Create a user
    User.objects.create_user(username="testuser", password="testpass")

    # Create a house
    house = ContentHouse.objects.create(name="Test House")

    # Login
    client = Client()
    client.login(username="testuser", password="testpass")

    # Test 1: Submit form without required fields
    response = client.post(
        reverse("core:lists-new"),
        {},  # Empty form data - should trigger validation errors
    )

    # Check that we stay on the same page (no redirect)
    assert response.status_code == 200

    # Check that form errors are present in the response
    assert "form" in response.context
    form = response.context["form"]
    assert form.errors  # Form should have errors

    # Check specific field errors
    assert "name" in form.errors
    assert "content_house" in form.errors

    # Test 2: Check that Django's form error rendering works
    # The template should display errors via {{ form }} which includes field errors
    content = response.content.decode()

    # Django's form rendering includes error messages
    # Check for the presence of error indicators
    assert "errorlist" in content or "invalid-feedback" in content

    # Test 3: Submit form with only name (missing content_house)
    response = client.post(
        reverse("core:lists-new"),
        {
            "name": "Test List",
            # missing content_house
        },
    )

    assert response.status_code == 200
    form = response.context["form"]
    assert "content_house" in form.errors
    assert "name" not in form.errors  # Name should be valid

    # Test 4: Valid form submission should redirect
    response = client.post(
        reverse("core:lists-new"),
        {
            "name": "Valid List",
            "content_house": house.id,
            "public": False,
            "show_stash": True,
        },
    )

    # Should redirect on success
    assert response.status_code == 302

    # Verify list was created
    assert List.objects.filter(name="Valid List").exists()


@pytest.mark.django_db
def test_new_list_form_field_specific_errors():
    """Test that field-specific errors are accessible in the template"""
    User.objects.create_user(username="testuser", password="testpass")

    client = Client()
    client.login(username="testuser", password="testpass")

    # Submit form with invalid content_house ID
    response = client.post(
        reverse("core:lists-new"),
        {
            "name": "Test List",
            "content_house": "999999",  # Non-existent ID
            "public": False,
        },
    )

    assert response.status_code == 200
    form = response.context["form"]

    # Check that content_house has an error
    assert "content_house" in form.errors

    # The form should be re-rendered with the error
    # Django's form rendering will display this error near the field
    content = response.content.decode()

    # The error should be present in the rendered form
    # (exact text depends on Django's validation message)
    assert form.errors["content_house"][0] in content
