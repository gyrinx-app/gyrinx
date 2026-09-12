import asyncio

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import override_settings

from scripts import screenshot


def test_server_url_uses_worktree_port(monkeypatch):
    monkeypatch.setenv("DJANGO_PORT", "8322")

    assert screenshot.get_server_port() == 8322
    assert screenshot.get_server_url() == "http://localhost:8322"


def test_server_url_defaults_to_port_8000(monkeypatch):
    monkeypatch.delenv("DJANGO_PORT", raising=False)

    assert screenshot.get_server_url() == "http://localhost:8000"


def test_capture_uses_requested_username(monkeypatch, tmp_path):
    captured = {}

    class FakeCapture:
        def __init__(self, server_url=None, username="agent"):
            captured["username"] = username

        async def capture_screenshot(self, **kwargs):
            return True

    monkeypatch.setattr(screenshot, "ScreenshotCapture", FakeCapture)

    success = asyncio.run(
        screenshot.capture_screenshots(
            "core:campaign",
            output_dir=tmp_path,
            username="reviewer",
        )
    )

    assert success is True
    assert captured["username"] == "reviewer"


def test_after_only_comparison_has_complete_document(tmp_path):
    capture = screenshot.ScreenshotCapture()

    capture._update_comparison_markdown(
        tmp_path,
        "core:campaign",
        "after",
        "campaign_after.png",
        "mobile",
    )

    comparison = tmp_path / "core_campaign_mobile_comparison.md"
    assert comparison.read_text() == (
        "# core:campaign UI changes\n\n"
        "**Viewport:** mobile\n\n"
        "## After\n"
        "![After](./campaign_after.png)\n\n"
    )


@pytest.mark.django_db(transaction=True)
@override_settings(DEBUG=True)
def test_authenticate_creates_local_staff_user():
    capture = screenshot.ScreenshotCapture(username="screenshot-reviewer")

    cookie = asyncio.run(capture.authenticate())

    user = get_user_model().objects.get(username="screenshot-reviewer")
    assert user.is_staff is True
    assert user.is_superuser is True
    assert cookie["name"] == settings.SESSION_COOKIE_NAME
