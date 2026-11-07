"""Security outcomes must be visible without copying request secrets to logs."""

from unittest.mock import Mock, patch

import pytest
from allauth.mfa.totp.internal import auth as totp_auth
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.storage.fallback import FallbackStorage
from django.http import HttpResponseForbidden, HttpResponseRedirect
from django.test import Client, RequestFactory, override_settings

from gyrinx.adapter import CustomAccountAdapter
from gyrinx.middleware import SecurityTelemetryMiddleware
from gyrinx.security_events import record_security_event
from gyrinx.views_csrf import csrf_failure


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("path", "data", "action"),
    [
        ("/accounts/login/", {"login": "nobody", "password": "secret"}, "login"),
        ("/accounts/signup/", {"username": "bad!", "password1": "secret"}, "signup"),
    ],
)
def test_rejected_account_forms_emit_bounded_audit(monkeypatch, path, data, action):
    monkeypatch.setattr(
        "django_recaptcha.fields.ReCaptchaField.validate", lambda self, value: True
    )
    with patch("gyrinx.security_events.track") as audit:
        response = Client(HTTP_USER_AGENT="Googlebot").post(path, data)

    assert response.status_code == 200
    audit.assert_called_once()
    (name,) = audit.call_args.args
    labels = audit.call_args.kwargs
    assert name == "security_request"
    assert labels["action"] == action
    assert labels["outcome"] == "rejected"
    assert labels["reason"] == "form_rejected"
    assert labels["route"] != "unresolved"
    assert labels["request_id"]
    assert "secret" not in str(labels)
    assert "nobody" not in str(labels)


@pytest.mark.django_db
def test_failed_mfa_reauthentication_is_audited():
    user = get_user_model().objects.create_user(
        username="mfa-user", password="password"
    )
    totp_auth.TOTP.activate(user, totp_auth.generate_totp_secret())
    client = Client()
    client.force_login(user)

    with patch("gyrinx.security_events.track") as audit:
        response = client.post("/accounts/2fa/reauthenticate/", {"code": "000000"})

    assert response.status_code == 200
    assert audit.call_args.kwargs["action"] == "mfa"
    assert audit.call_args.kwargs["actor_id"] == str(user.pk)
    assert "000000" not in str(audit.call_args)


def test_permission_response_is_audited_without_user_input():
    request = RequestFactory().get("/private/?token=secret")
    request.user = AnonymousUser()
    middleware = SecurityTelemetryMiddleware(lambda request: HttpResponseForbidden())

    with patch("gyrinx.security_events.track") as audit:
        middleware(request)

    assert audit.call_args.kwargs["action"] == "permission"
    assert "secret" not in str(audit.call_args)


def test_login_required_redirect_is_audited_without_next_url():
    request = RequestFactory().get("/private/?token=secret")
    request.user = AnonymousUser()
    middleware = SecurityTelemetryMiddleware(
        lambda request: HttpResponseRedirect(
            "/accounts/login/?next=%2Fprivate%2F%3Ftoken%3Dsecret"
        )
    )

    with patch("gyrinx.security_events.track") as audit:
        middleware(request)

    assert audit.call_args.kwargs["reason"] == "login_required"
    assert "secret" not in str(audit.call_args)


@pytest.mark.django_db
def test_disallowed_host_is_audited_without_echoing_host():
    with patch("gyrinx.security_events.track") as audit:
        response = Client(HTTP_HOST="forged.example").get("/")

    assert response.status_code == 400
    assert audit.call_args.kwargs["reason"] == "invalid_host"
    assert "forged.example" not in str(audit.call_args)


def test_trace_context_is_validated_and_request_id_is_generated():
    request = RequestFactory().post(
        "/accounts/login/",
        HTTP_X_CLOUD_TRACE_CONTEXT="0123456789abcdef0123456789abcdef/1;o=1",
    )
    request.user = AnonymousUser()

    with patch("gyrinx.security_events.track") as audit:
        record_security_event(request, "login", "form_rejected")

    assert audit.call_args.kwargs["trace_id"] == "0123456789abcdef0123456789abcdef"
    assert len(audit.call_args.kwargs["request_id"]) == 32


@override_settings(TRUSTED_X_FORWARDED_FOR_HOPS=2)
def test_allauth_uses_trusted_client_ip_entry():
    request = RequestFactory().get(
        "/accounts/login/",
        HTTP_X_FORWARDED_FOR="203.0.113.9, 192.0.2.5, 10.0.0.1",
    )
    assert CustomAccountAdapter().get_client_ip(request) == "192.0.2.5"


def test_anonymous_csrf_redirect_is_audited():
    request = RequestFactory().post("/accounts/login/")
    request.user = AnonymousUser()
    request.session = {}
    request._messages = FallbackStorage(request)

    with patch("gyrinx.security_events.track") as audit:
        response = csrf_failure(request, reason="token=secret")

    assert response.status_code == 302
    assert audit.call_args.kwargs["action"] == "csrf"
    assert audit.call_args.kwargs["reason"] == "token_or_origin_rejected"
    assert "secret" not in str(audit.call_args)


def test_pool_timeout_has_explicit_event():
    from psycopg_pool import PoolTimeout

    request = RequestFactory().get("/n23/lists/")
    middleware = SecurityTelemetryMiddleware(lambda request: None)

    with patch("gyrinx.middleware.track") as telemetry:
        assert middleware.process_exception(request, PoolTimeout()) is None

    assert telemetry.call_args.args == ("db_pool_timeout",)
    assert telemetry.call_args.kwargs["request_id"]


def test_pool_stats_use_existing_pool_without_opening_connection(monkeypatch):
    pool = Mock()
    pool.get_stats.return_value = {"pool_size": 6, "pool_available": 0}
    db = Mock()
    db._connection_pools = {"default": pool}
    monkeypatch.setattr("gyrinx.middleware.connections", {"default": db})
    monkeypatch.setattr(SecurityTelemetryMiddleware, "_last_pool_stats", 0.0)
    monkeypatch.setattr("gyrinx.middleware.monotonic", lambda: 120.0)

    with patch("gyrinx.middleware.track") as telemetry:
        SecurityTelemetryMiddleware._emit_pool_stats()

    telemetry.assert_called_once_with("db_pool_stats", pool_size=6, pool_available=0)
