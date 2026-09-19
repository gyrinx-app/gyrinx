"""Shared documentation chrome keeps the reader's edition and account state."""

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
