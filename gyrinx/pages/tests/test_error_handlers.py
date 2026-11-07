import pytest
from django.contrib.auth.models import Group
from django.contrib.flatpages.models import FlatPage
from django.contrib.sessions.backends.db import SessionStore
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
    assert "Page not found" in response.content.decode()
    content = response.content.decode()
    assert 'data-test-id="the-joke"' in content


@pytest.mark.django_db
def test_403_handler_with_permission_denied(client, admin_user):

    site = Site.objects.get_current()
    page = FlatPage.objects.create(
        url="/restricted-page/",
        title="Restricted Page",
        content="This is restricted content",
    )
    page.sites.add(site)

    group = Group.objects.create(name="special_group")
    visibility = FlatPageVisibility.objects.create(page=page)
    visibility.groups.add(group)

    response = client.get("/restricted-page/")
    assert response.status_code == 404  # FlatPage raises 404 for anonymous users

    client.force_login(admin_user)
    response = client.get("/restricted-page/")
    assert (
        response.status_code == 404
    )  # FlatPage raises 404 for users without permission


@pytest.mark.django_db
def test_400_handler():
    # Exercise the handler directly because Django may reject malformed requests before view dispatch.

    factory = RequestFactory()
    request = factory.get("/")
    response = error_400(request)
    assert response.status_code == 400
    assert "400" in response.content.decode()
    assert "Bad Request" in response.content.decode()


@pytest.mark.django_db
def test_403_handler():

    factory = RequestFactory()
    request = factory.get("/")
    response = error_403(request)
    assert response.status_code == 403
    assert "403" in response.content.decode()
    assert "Forbidden" in response.content.decode()


@pytest.mark.django_db
def test_500_handler():

    factory = RequestFactory()
    request = factory.get("/")
    response = error_500(request)
    assert response.status_code == 500
    assert "500" in response.content.decode()
    assert "Server Error" in response.content.decode()
    assert "<!DOCTYPE html>" in response.content.decode()
    assert "Error ID:" in response.content.decode()
    import re

    uuid_pattern = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    assert re.search(uuid_pattern, response.content.decode())


@pytest.mark.django_db
def test_500_handler_shows_error_id_consistently():

    factory = RequestFactory()
    request = factory.get("/")
    response = error_500(request)

    assert response.status_code == 500

    import re

    content = response.content.decode()
    uuid_pattern = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    error_id_matches = re.findall(uuid_pattern, content)

    assert len(error_id_matches) == 1
    error_id = error_id_matches[0]

    assert "Error ID:" in content
    assert "Please include this ID when reporting the issue" in content
    assert f"<code>{error_id}</code>" in content


@pytest.mark.django_db
@override_settings(DEBUG=False)
def test_error_handlers_with_debug_false():
    client = Client()

    response = client.get("/this-page-definitely-does-not-exist/")
    assert response.status_code == 404
    assert "404" in response.content.decode()
    assert "Page not found" in response.content.decode()

    assert "Home" in response.content.decode()


@pytest.mark.django_db
def test_error_page_urls_exist(client):
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
    assert "Page not found" in response.content.decode()

    response = client.get(reverse("error_500"))
    assert response.status_code == 500
    assert "500" in response.content.decode()
    assert "Server Error" in response.content.decode()


@pytest.mark.django_db
def test_error_handlers_context():

    factory = RequestFactory()
    request = factory.get("/")
    # Provide the session used by layout context processors.
    request.session = SessionStore()

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

    response = error_404(request, exception=None)
    assert response.status_code == 404
    assert "404" in response.content.decode()
    assert "Page not found" in response.content.decode()

    response = error_500(request)
    assert response.status_code == 500
    assert "500" in response.content.decode()
    assert "Server Error" in response.content.decode()
