from io import StringIO
from urllib.parse import parse_qs, urlparse

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth import SESSION_KEY, get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from django.urls import reverse

from gyrinx.debug_login import (
    DEBUG_AGENT_LOGIN_ERROR,
)

_debug_settings = {"DEBUG": True, "INTERNAL_IPS": []}


def _login_params(username="agent", target="/"):
    return {"user": username, "next": target}


@override_settings(**_debug_settings)
@pytest.mark.django_db
def test_agent_login_link_creates_staff_session(client):
    response = client.get(
        reverse("debug_agent_login"),
        _login_params("agent-campaign", "/n26/"),
    )

    user = get_user_model().objects.get(username="agent-campaign")
    assert response.status_code == 302
    assert response.url == "/n26/"
    assert client.session[SESSION_KEY] == str(user.pk)
    assert user.check_password("password") is True
    assert user.is_staff is True
    assert user.is_superuser is False
    assert EmailAddress.objects.get(
        user=user, email="agent-campaign@localhost"
    ).verified


@override_settings(**_debug_settings)
@pytest.mark.django_db
def test_agent_login_refuses_existing_allowed_superuser_without_changing_it(client):
    superuser = get_user_model().objects.create_superuser(
        username="agent-admin",
        email="owner@example.com",
        password="keep-this-password",
    )

    response = client.get(
        reverse("debug_agent_login"),
        _login_params("agent-admin"),
    )

    superuser.refresh_from_db()
    assert response.status_code == 400
    assert superuser.check_password("keep-this-password") is True
    assert superuser.email == "owner@example.com"
    assert superuser.is_superuser is True


@override_settings(**_debug_settings)
@pytest.mark.django_db
def test_agent_login_rejects_overlong_username(client):
    username = f"agent-{'a' * 150}"

    response = client.get(reverse("debug_agent_login"), {"user": username})

    assert response.status_code == 400
    assert response.headers["Content-Type"] == "text/plain; charset=utf-8"
    assert response.content.decode() == DEBUG_AGENT_LOGIN_ERROR
    assert get_user_model().objects.filter(username=username).exists() is False


@override_settings(**_debug_settings)
@pytest.mark.django_db
def test_agent_login_rejects_invalid_username(client):
    response = client.get(reverse("debug_agent_login"), {"user": "reviewer"})

    assert response.status_code == 400
    assert response.content.decode() == DEBUG_AGENT_LOGIN_ERROR


@override_settings(DEBUG=False)
@pytest.mark.django_db
def test_agent_login_404s_without_debug(client):
    response = client.get(reverse("debug_agent_login"), _login_params())

    assert response.status_code == 404
    assert get_user_model().objects.filter(username="agent").exists() is False


@override_settings(**_debug_settings)
@pytest.mark.django_db
def test_agent_login_rejects_external_redirect(client):
    response = client.get(
        reverse("debug_agent_login"),
        _login_params("agent", "https://example.com/not-local"),
    )

    assert response.status_code == 302
    assert response.url == "/"


@override_settings(**_debug_settings)
@pytest.mark.django_db
def test_agent_login_url_command_creates_user_and_encodes_target(monkeypatch):
    monkeypatch.setenv("DJANGO_PORT", "9317")
    stdout = StringIO()

    call_command(
        "agent_login_url",
        "/n26/gangs/?state=draft",
        username="agent-review",
        stdout=stdout,
    )

    parsed = urlparse(stdout.getvalue().strip())
    assert parsed.scheme == "http"
    assert parsed.netloc == "localhost:9317"
    assert parsed.path == reverse("debug_agent_login")
    assert parse_qs(parsed.query) == {
        "user": ["agent-review"],
        "next": ["/n26/gangs/?state=draft"],
    }
    user = get_user_model().objects.get(username="agent-review")
    password_hash = user.password
    assert user.is_superuser is False

    call_command("agent_login_url", username="agent-review", stdout=StringIO())
    user.refresh_from_db()
    assert user.password == password_hash


@override_settings(DEBUG=False)
@pytest.mark.django_db
def test_agent_login_url_command_refuses_without_debug():
    with pytest.raises(CommandError, match="only available with DEBUG enabled"):
        call_command("agent_login_url")

    assert get_user_model().objects.filter(username="agent").exists() is False
