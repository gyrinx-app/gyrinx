import json
from unittest.mock import patch

import pytest
from django.http import HttpRequest
from django.test import RequestFactory
from nacl.signing import SigningKey

from gyrinx.api.views import (
    DISCORD_APPLICATION_COMMAND,
    DISCORD_DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE,
    DISCORD_PING,
    DISCORD_PONG,
    discord_interactions,
)


@pytest.fixture
def discord_signing_key():
    """Generate an Ed25519 signing key for test Discord signatures."""
    return SigningKey.generate()


@pytest.fixture
def discord_public_key(discord_signing_key):
    """Return the hex-encoded public key."""
    return discord_signing_key.verify_key.encode().hex()


def make_discord_request(
    factory: RequestFactory,
    signing_key: SigningKey,
    body: dict,
) -> HttpRequest:
    """Create a signed Discord interaction request."""
    body_bytes = json.dumps(body).encode()
    timestamp = "1234567890"
    message = timestamp.encode() + body_bytes
    signed = signing_key.sign(message)
    signature = signed.signature.hex()

    request = factory.post(
        "/api/v1/discord/interactions",
        data=body_bytes,
        content_type="application/json",
    )
    request.META["HTTP_X_SIGNATURE_ED25519"] = signature
    request.META["HTTP_X_SIGNATURE_TIMESTAMP"] = timestamp
    return request


@pytest.mark.django_db
def test_discord_ping_returns_pong(discord_signing_key, discord_public_key):
    """Discord PING should return PONG for endpoint verification."""
    factory = RequestFactory()
    body = {"type": DISCORD_PING}
    request = make_discord_request(factory, discord_signing_key, body)

    with patch("gyrinx.api.views.settings") as mock_settings:
        mock_settings.DISCORD_PUBLIC_KEY = discord_public_key
        mock_settings.DISCORD_APPLICATION_ID = "test-app-id"
        mock_settings.DEBUG = False
        response = discord_interactions(request)

    assert response.status_code == 200
    data = json.loads(response.content)
    assert data["type"] == DISCORD_PONG


def test_discord_missing_signature_returns_401():
    """Request without signature headers should return 401."""
    factory = RequestFactory()
    request = factory.post(
        "/api/v1/discord/interactions",
        data=json.dumps({"type": 1}),
        content_type="application/json",
    )

    with patch("gyrinx.api.views.settings") as mock_settings:
        mock_settings.DISCORD_PUBLIC_KEY = "a" * 64
        response = discord_interactions(request)

    assert response.status_code == 401


def test_discord_invalid_signature_returns_401(discord_signing_key):
    """Request with invalid signature should return 401."""
    factory = RequestFactory()
    body_bytes = json.dumps({"type": 1}).encode()
    request = factory.post(
        "/api/v1/discord/interactions",
        data=body_bytes,
        content_type="application/json",
    )
    request.META["HTTP_X_SIGNATURE_ED25519"] = "00" * 64
    request.META["HTTP_X_SIGNATURE_TIMESTAMP"] = "1234567890"

    # Use a different key's public key to ensure mismatch
    wrong_key = SigningKey.generate()
    wrong_public_key = wrong_key.verify_key.encode().hex()

    with patch("gyrinx.api.views.settings") as mock_settings:
        mock_settings.DISCORD_PUBLIC_KEY = wrong_public_key
        response = discord_interactions(request)

    assert response.status_code == 401


def test_discord_no_public_key_returns_503():
    """Missing DISCORD_PUBLIC_KEY should return 503."""
    factory = RequestFactory()
    request = factory.post(
        "/api/v1/discord/interactions",
        data=json.dumps({"type": 1}),
        content_type="application/json",
    )

    with patch("gyrinx.api.views.settings") as mock_settings:
        mock_settings.DISCORD_PUBLIC_KEY = ""
        response = discord_interactions(request)

    assert response.status_code == 503


def test_discord_get_returns_405():
    """GET requests should return 405."""
    factory = RequestFactory()
    request = factory.get("/api/v1/discord/interactions")

    with patch("gyrinx.api.views.settings") as mock_settings:
        mock_settings.DISCORD_PUBLIC_KEY = "a" * 64
        response = discord_interactions(request)

    assert response.status_code == 405


@pytest.mark.django_db
def test_discord_command_enqueues_task(discord_signing_key, discord_public_key):
    """A valid Create Issue command should enqueue the task and return deferred."""
    factory = RequestFactory()
    body = {
        "type": DISCORD_APPLICATION_COMMAND,
        "id": "interaction-id-123",
        "token": "interaction-token-abc",  # nosec B105
        "channel_id": "channel-123",
        "guild_id": "guild-456",
        "member": {
            "user": {"username": "testuser"},
        },
        "data": {
            "name": "Create Issue",
            "type": 3,
            "target_id": "msg-789",
            "resolved": {
                "messages": {
                    "msg-789": {
                        "id": "msg-789",
                        "content": "This is a bug report",
                        "author": {"username": "reporter"},
                    }
                }
            },
        },
    }
    request = make_discord_request(factory, discord_signing_key, body)

    with (
        patch("gyrinx.api.views.settings") as mock_settings,
        patch("gyrinx.api.views._handle_discord_command") as mock_handle,
    ):
        mock_settings.DISCORD_PUBLIC_KEY = discord_public_key
        mock_settings.DEBUG = False
        mock_handle.return_value = __import__(
            "django.http", fromlist=["JsonResponse"]
        ).JsonResponse(
            {
                "type": DISCORD_DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE,
                "data": {"flags": 64},
            }
        )
        response = discord_interactions(request)

    assert response.status_code == 200
    data = json.loads(response.content)
    assert data["type"] == DISCORD_DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE


@pytest.mark.django_db
def test_discord_command_stores_webhook_request(
    discord_signing_key, discord_public_key
):
    """Discord commands should be stored in WebhookRequest for audit."""
    from gyrinx.api.models import WebhookRequest

    factory = RequestFactory()
    body = {
        "type": DISCORD_APPLICATION_COMMAND,
        "id": "interaction-id-123",
        "token": "interaction-token-abc",  # nosec B105
        "channel_id": "channel-123",
        "guild_id": "guild-456",
        "member": {"user": {"username": "testuser"}},
        "data": {
            "name": "Create Issue",
            "type": 3,
            "target_id": "msg-789",
            "resolved": {
                "messages": {
                    "msg-789": {
                        "id": "msg-789",
                        "content": "Bug here",
                        "author": {"username": "reporter"},
                    }
                }
            },
        },
    }
    request = make_discord_request(factory, discord_signing_key, body)

    with (
        patch("gyrinx.api.views.settings") as mock_settings,
        patch("gyrinx.core.tasks.trigger_discord_issue_action") as mock_task,
    ):
        mock_settings.DISCORD_PUBLIC_KEY = discord_public_key
        mock_settings.DISCORD_APPLICATION_ID = "test-app-id"
        mock_settings.DEBUG = False
        mock_task.enqueue = lambda **kwargs: None
        response = discord_interactions(request)

    assert response.status_code == 200
    wr = WebhookRequest.objects.filter(source="discord").first()
    assert wr is not None
    assert wr.event == "command:Create Issue"
    assert wr.payload["data"]["target_id"] == "msg-789"
