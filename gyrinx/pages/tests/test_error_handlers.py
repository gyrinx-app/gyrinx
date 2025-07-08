import pytest
from django.test import Client
from django.urls import reverse


@pytest.mark.django_db
def test_404_handler():
    """Test that 404 errors return the custom 404 page."""
    client = Client()
    response = client.get("/this-page-does-not-exist/")
    assert response.status_code == 404
    # Check that it's using our custom 404 template
    assert "404.html" in [t.name for t in response.templates]


@pytest.mark.django_db
def test_direct_404_view():
    """Test the direct 404 view."""
    client = Client()
    response = client.get(reverse("error_404"))
    assert response.status_code == 404


@pytest.mark.django_db
def test_direct_500_view():
    """Test the direct 500 view."""
    client = Client()
    response = client.get(reverse("error_500"))
    assert response.status_code == 500
