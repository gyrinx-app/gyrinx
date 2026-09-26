import asyncio
import sys

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import NoReverseMatch, reverse

from scripts import screenshot


def test_resolve_url_path_accepts_spurious_n26_namespace():
    path, resolved = screenshot.resolve_url_path("n26:authoring-create", ["pickable"])
    expected = reverse("authoring-create", args=["pickable"])

    assert resolved == "authoring-create"
    assert path == expected
    assert path.endswith("/authoring/pickable/new/")


def test_resolve_url_path_keeps_real_namespaces():
    campaign_id = "00000000-0000-0000-0000-000000000000"
    campaign_path, campaign_name = screenshot.resolve_url_path(
        "core:campaign", [campaign_id]
    )
    gallery_path, gallery_name = screenshot.resolve_url_path("designsystem:index")

    assert campaign_name == "core:campaign"
    assert campaign_path == reverse("core:campaign", args=[campaign_id])
    assert gallery_name == "designsystem:index"
    assert gallery_path == reverse("designsystem:index")


def test_resolve_url_path_unknown_n26_name_tries_bare_name():
    with pytest.raises(
        NoReverseMatch, match=r"no URL namespace; also tried 'not-a-real-view'"
    ):
        screenshot.resolve_url_path("n26:not-a-real-view")


def test_resolve_url_path_strips_n26_from_nested_designsystem_name():
    path, resolved = screenshot.resolve_url_path("n26:designsystem:index")

    assert resolved == "designsystem:index"
    assert path == reverse("designsystem:index")


def test_server_url_uses_worktree_port(monkeypatch):
    monkeypatch.setenv("DJANGO_PORT", "8322")

    assert screenshot.get_server_port() == 8322
    assert screenshot.get_server_url() == "http://localhost:8322"


def test_server_url_defaults_to_port_8000(monkeypatch):
    monkeypatch.delenv("DJANGO_PORT", raising=False)

    assert screenshot.get_server_url() == "http://localhost:8000"


def test_main_rejects_non_agent_username_without_traceback(monkeypatch, capsys):
    monkeypatch.setattr(
        sys,
        "argv",
        ["screenshot.py", "core:campaign", "--username", "reviewer"],
    )

    with pytest.raises(SystemExit) as error:
        screenshot.main()

    assert error.value.code == 2
    assert "'agent' or 'agent-<purpose>'" in capsys.readouterr().err


def test_capture_uses_requested_username_and_reports_folder(
    monkeypatch, tmp_path, capsys
):
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
            username="agent-reviewer",
        )
    )

    assert success is True
    assert captured["username"] == "agent-reviewer"
    assert f"Screenshot folder: {tmp_path.resolve()}" in capsys.readouterr().out


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
    capture = screenshot.ScreenshotCapture(username="agent-screenshots")

    cookie = asyncio.run(capture.authenticate())

    user = get_user_model().objects.get(username="agent-screenshots")
    assert user.is_staff is True
    assert user.is_superuser is False
    assert user.check_password("password") is True
    assert cookie["name"] == settings.SESSION_COOKIE_NAME
