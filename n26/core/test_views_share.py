"""The Share button on the gang sheet.

<c-n26.share> is a link to the page itself, so it works with no script;
Alpine takes the click over. The edit page carries none.
"""

import re

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core import icons
from n26.core.models import Gang

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner(db):
    return User.objects.create_user("player")


@pytest.fixture
def gang(gang_type, owner):
    return Gang.objects.create(
        name="The Ashen Choir",
        owner=owner,
        gang_type=gang_type,
        starting_credits=1000,
        credits=340,
    )


def share_link(body, url):
    """The <a> that shares `url` on click, or None."""
    for match in re.finditer(rf'<a\s[^>]*href="{re.escape(url)}"[^>]*>', body):
        if "clicked($event)" in match.group(0):
            return match.group(0)
    return None


def test_the_sheet_offers_its_owner_a_share_link(client, owner, gang):
    client.force_login(owner)
    url = reverse("n26-gang", args=[gang.pk])

    body = client.get(url).content.decode()

    assert share_link(body, url) is not None
    assert icons.ICONS["share"][0] in body
    assert "Link copied." in body


def test_a_visitor_gets_the_same_share_link(client, gang):
    url = reverse("n26-gang", args=[gang.pk])

    body = client.get(url).content.decode()

    assert share_link(body, url) is not None


def test_the_edit_page_has_no_share_button(client, owner, gang):
    client.force_login(owner)

    body = client.get(reverse("n26-edit-gang", args=[gang.pk])).content.decode()

    assert "clicked($event)" not in body
    assert icons.ICONS["share"][0] not in body
