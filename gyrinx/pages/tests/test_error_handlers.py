import pytest
from django.contrib.auth.models import Group
from django.contrib.flatpages.models import FlatPage
from django.contrib.sites.models import Site
from django.test import Client, RequestFactory, override_settings
from django.urls import reverse

from gyrinx.pages.models import FlatPageVisibility
from gyrinx.pages.views import error_400, error_403, error_404, error_500


@pytest.mark.django_db
@override_settings(DEBUG=False)
def test_404_handler(client):
    response = client.get("/this-page-definitely-does-not-exist/")
    assert response.status_code == 404
    assert "404" in response.content.decode()
    assert "Page Not Found" in response.content.decode()
    # Check that one of the jokes appears in the response
    content = response.content.decode()
    assert 'data-test-id="the-joke"' in content


@pytest.mark.django_db
def test_403_handler_with_permission_denied(client, admin_user):
    # Test by accessing a flatpage that requires permissions

    # Create a flatpage with restricted visibility
    site = Site.objects.get_current()
    page = FlatPage.objects.create(
        url="/restricted-page/",
        title="Restricted Page",
        content="This is restricted content",
    )
    page.sites.add(site)

    # Create a group and add visibility restriction
    group = Group.objects.create(name="special_group")
    visibility = FlatPageVisibility.objects.create(page=page)
    visibility.groups.add(group)

    # Try to access as anonymous user
    response = client.get("/restricted-page/")
    assert response.status_code == 404  # FlatPage raises 404 for anonymous users

    # Try to access as user without the group
    client.force_login(admin_user)
    response = client.get("/restricted-page/")
    assert (
        response.status_code == 404
    )  # FlatPage raises 404 for users without permission


@pytest.mark.django_db
def test_400_handler():
    # Testing 400 errors is tricky because Django handles most bad requests
    # before they reach our handler. We'll test the view directly.

    factory = RequestFactory()
    request = factory.get("/")
    response = error_400(request)
    assert response.status_code == 400
    assert "400" in response.content.decode()
    assert "Bad Request" in response.content.decode()


@pytest.mark.django_db
def test_403_handler():
    # Test the 403 handler directly

    factory = RequestFactory()
    request = factory.get("/")
    response = error_403(request)
    assert response.status_code == 403
    assert "403" in response.content.decode()
    assert "Forbidden" in response.content.decode()


@pytest.mark.django_db
def test_500_handler():
    # Testing 500 errors requires DEBUG=False
    # We'll test the view directly

    factory = RequestFactory()
    request = factory.get("/")
    response = error_500(request)
    assert response.status_code == 500
    assert "500" in response.content.decode()
    assert "Server Error" in response.content.decode()
    # Verify it's a standalone template (doesn't extend base)
    assert "<!DOCTYPE html>" in response.content.decode()
    # Verify error ID is displayed
    assert "Error ID:" in response.content.decode()
    # Check that a UUID-like pattern is present
    import re

    uuid_pattern = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    assert re.search(uuid_pattern, response.content.decode())


@pytest.mark.django_db
def test_500_handler_shows_error_id_consistently():
    # Test that the error ID shown to user matches what would be logged

    factory = RequestFactory()
    request = factory.get("/")
    response = error_500(request)

    assert response.status_code == 500

    # Extract the error ID from the response
    import re

    content = response.content.decode()
    uuid_pattern = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    error_id_matches = re.findall(uuid_pattern, content)

    # Should have exactly one error ID
    assert len(error_id_matches) == 1
    error_id = error_id_matches[0]

    # Verify the error ID is displayed in the user-friendly message
    assert "Error ID:" in content
    assert "Please include this ID when reporting the issue" in content
    assert f"<code>{error_id}</code>" in content


@pytest.mark.django_db
@override_settings(DEBUG=False)
def test_error_handlers_with_debug_false():
    # This tests that the handlers work when DEBUG=False
    client = Client()

    # Test 404
    response = client.get("/this-page-definitely-does-not-exist/")
    assert response.status_code == 404
    assert "404" in response.content.decode()
    assert "Page Not Found" in response.content.decode()

    # Test that the error pages use the correct template
    assert "Go Home" in response.content.decode()


@pytest.mark.django_db
def test_error_page_urls_exist(client):
    # Test that we can access the error pages directly (useful for testing)
    response = client.get(reverse("error_400"))
    assert response.status_code == 400
    assert "400" in response.content.decode()
    assert "Bad Request" in response.content.decode()

    response = client.get(reverse("error_403"))
    assert response.status_code == 403
    assert "403" in response.content.decode()
    assert "Forbidden" in response.content.decode()

    response = client.get(reverse("error_404"))
    assert response.status_code == 404
    assert "404" in response.content.decode()
    assert "Page Not Found" in response.content.decode()

    response = client.get(reverse("error_500"))
    assert response.status_code == 500
    assert "500" in response.content.decode()
    assert "Server Error" in response.content.decode()


@pytest.mark.django_db
def test_error_handlers_context():
    # Test that the views pass the correct context

    factory = RequestFactory()
    request = factory.get("/")

    # Test 400 and 403 handlers (these use the generic error template)
    handlers = [
        (error_400, 400, "Bad Request"),
        (error_403, 403, "Forbidden"),
    ]

    for handler, code, message in handlers:
        response = handler(request, exception=None)
        assert response.status_code == code
        content = response.content.decode()
        assert str(code) in content
        assert message in content

    # Test 404 handler (uses custom template with jokes)
    response = error_404(request, exception=None)
    assert response.status_code == 404
    assert "404" in response.content.decode()
    assert "Page Not Found" in response.content.decode()

    # Test 500 handler (uses standalone template)
    response = error_500(request)
    assert response.status_code == 500
    assert "500" in response.content.decode()
    assert "Server Error" in response.content.decode()


@pytest.mark.django_db
def test_robots_txt(client):
    """Test that robots.txt is served correctly via template."""
    response = client.get("/robots.txt")
    assert response.status_code == 200
    assert response["Content-Type"] == "text/plain"

    content = response.content.decode()
    assert "User-agent: *" in content
    assert "Disallow: /admin/" in content
