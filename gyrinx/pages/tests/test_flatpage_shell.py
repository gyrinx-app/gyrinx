"""Shared documentation chrome keeps the reader's edition and account state."""

from copy import deepcopy
from unittest.mock import patch

import pytest
from bs4 import BeautifulSoup
from django.contrib.flatpages.models import FlatPage
from django.template.loader import render_to_string
from django.test import RequestFactory

from gyrinx.editions import COOKIE_NAME

pytestmark = pytest.mark.django_db


@pytest.fixture
def shell_page(site):
    page = FlatPage.objects.create(
        url="/help/n26/shell-test/",
        title="Shared help",
        content="<h2>First section</h2><p>Text.</p><h2>Second section</h2>",
    )
    page.sites.add(site)
    return page


@pytest.mark.parametrize("edition", ["n23", "n26"])
def test_flatpage_shell_preserves_remembered_edition(client, user, shell_page, edition):
    client.force_login(user)
    client.cookies[COOKIE_NAME] = edition
    response = client.get(shell_page.url)
    assert response.status_code == 200
    assert COOKIE_NAME not in response.cookies
    document = BeautifulSoup(response.content, "html.parser")
    toggle = document.find(attrs={"aria-label": "Edition"})
    assert (
        toggle.find(attrs={"aria-current": "true"}).get_text(strip=True)
        == edition.upper()
    )
    classic = toggle.find("a", string="N23")
    assert classic["href"] == ("/?edition=n23" if edition == "n26" else "/")
    assert document.select_one(".n26-site-brand")["href"] == "/"
    assert not document.find(string="Your gangs")
    assert b"designsystem/app.css" in response.content
    assert b"core/css/screen.css" not in response.content


def test_anonymous_flatpage_has_login_return_and_no_edition_toggle(client, shell_page):
    response = client.get(shell_page.url)
    document = BeautifulSoup(response.content, "html.parser")
    assert document.find(attrs={"aria-label": "Edition"}) is None
    login = document.find("a", string=lambda text: text and text.strip() == "Sign in")
    assert "next=" in login["href"]
    assert shell_page.url in login["href"]


def test_shared_shell_does_not_draw_n26_write_pause(user):
    request = RequestFactory().get("/help/")
    request.user = user
    request.edition = "n23"
    html = render_to_string(
        "flatpages/shell.html",
        {"user": user, "write_pause": {"state": "PAUSED", "reason": "Pause test"}},
        request=request,
    )
    assert "Changes paused for maintenance" not in html
    assert "Pause test" not in html
    assert "Your account" in html
    assert "Notifications" in html


def configure_custom_template(settings, tmp_path, shell_page, source):
    (tmp_path / "custom.html").write_text(source)
    templates = deepcopy(settings.TEMPLATES)
    templates[0]["DIRS"] = [str(tmp_path), *templates[0]["DIRS"]]
    settings.TEMPLATES = templates
    shell_page.template_name = "custom.html"
    shell_page.save()


def test_custom_template_extending_default_receives_presentation(
    client, settings, tmp_path, shell_page
):
    configure_custom_template(
        settings,
        tmp_path,
        shell_page,
        '{% extends "flatpages/default.html" %}',
    )

    response = client.get(shell_page.url)
    document = BeautifulSoup(response.content, "html.parser")

    assert response.status_code == 200
    assert document.select_one(".flatpage-prose #first-section") is not None
    assert document.select_one(".flatpage-toc a")["href"] == "#first-section"


def test_standalone_custom_template_keeps_safe_html_without_building_presentation(
    client, settings, tmp_path, shell_page
):
    shell_page.title = "<em>Custom title</em>"
    configure_custom_template(
        settings,
        tmp_path,
        shell_page,
        "{{ flatpage.title }}{{ flatpage.content }}",
    )

    with patch("gyrinx.pages.views.build_flatpage_presentation") as builder:
        response = client.get(shell_page.url)

    assert response.status_code == 200
    assert response.content.decode() == shell_page.title + shell_page.content
    builder.assert_not_called()


def test_missing_custom_template_falls_back_to_the_default(client, shell_page):
    shell_page.template_name = "missing-custom-flatpage.html"
    shell_page.save()

    response = client.get(shell_page.url)
    document = BeautifulSoup(response.content, "html.parser")

    assert response.status_code == 200
    assert document.select_one(".flatpage-prose #first-section") is not None
