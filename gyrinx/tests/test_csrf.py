"""CSRF failure redirects, messages and destination validation."""

import pytest
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import Client
from django.urls import reverse

pytestmark = pytest.mark.core


@pytest.mark.django_db
def test_csrf_failure_redirects_with_message(client: Client):

    form_url = reverse("core:lists-new")

    response = client.get(form_url)
    assert response.status_code == 302  # Should redirect to login

    from django.contrib.auth import get_user_model

    User = get_user_model()
    user = User.objects.create_user(username="testuser", password="password")
    client.force_login(user)

    response = client.get(form_url + "?skip_packs=1")
    assert response.status_code == 200

    # Call the failure view directly to isolate its response from middleware token checking.

    from django.test import RequestFactory

    from gyrinx.views_csrf import csrf_failure

    factory = RequestFactory()
    request = factory.post(form_url, data={"name": "Test List"})
    request.META["HTTP_REFERER"] = form_url
    request.session = client.session

    request._messages = FallbackStorage(request)

    response = csrf_failure(request, reason="CSRF token missing or incorrect")

    assert response.status_code == 302
    assert response.url == form_url

    messages = list(get_messages(request))
    assert len(messages) == 1
    assert "Your session has expired" in str(messages[0])


@pytest.mark.django_db
def test_csrf_failure_redirects_to_home_without_referer(client: Client):

    from django.test import RequestFactory

    from gyrinx.views_csrf import csrf_failure

    factory = RequestFactory()
    request = factory.post("/some-url/", data={})
    request.session = client.session

    request._messages = FallbackStorage(request)

    response = csrf_failure(request, reason="CSRF token missing")

    # Assert the shared root literally so the fallback does not depend on an edition route.
    assert response.status_code == 302
    assert response.url == "/"


@pytest.mark.django_db
def test_csrf_failure_view_is_csrf_exempt():

    from gyrinx.views_csrf import csrf_failure

    assert getattr(csrf_failure, "csrf_exempt", False) is True


@pytest.mark.django_db
def test_csrf_failure_with_malicious_referer(client: Client):

    from django.test import RequestFactory
    from django.urls import reverse

    from gyrinx.views_csrf import csrf_failure

    factory = RequestFactory()
    request = factory.post("/some-url/", data={})
    request.META["HTTP_REFERER"] = "https://evil.com/steal-data"
    request.session = client.session

    request._messages = FallbackStorage(request)

    response = csrf_failure(request, reason="CSRF token missing")

    assert response.status_code == 302
    assert response.url == reverse("core:index")


def test_csrf_failure_view_setting():

    from django.conf import settings

    assert hasattr(settings, "CSRF_FAILURE_VIEW")
    assert settings.CSRF_FAILURE_VIEW == "gyrinx.views_csrf.csrf_failure"
