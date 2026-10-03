"""The Share button on the gang sheet.

<c-n26.share> is a link to the page itself, so it works with no script.
React takes the click once it has mounted. The edit page carries none.
"""

import json

import pytest
from bs4 import BeautifulSoup
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core import icons
from n26.core.models import Gang
from n26.core.templatetags.share import share_host_class, share_props

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


def share_host(body, url):
    """The island whose fallback link shares `url`, or None."""
    soup = BeautifulSoup(body, "html.parser")
    for host in soup.select("[data-react-fallback]"):
        props_tag = soup.find(id=host.get("data-react-props"))
        if props_tag is None or not props_tag.string:
            continue
        props = json.loads(props_tag.string)
        link = host.find("a", href=url)
        if props.get("url") == url and link is not None:
            return host, props, link
    return None


def test_share_props_keep_the_link_and_known_button_shape():
    assert share_props(url="/sheet/", message="Copied.", size="sm", variant="text") == {
        "url": "/sheet/",
        "message": "Copied.",
        "size": "sm",
        "variant": "text",
    }
    assert share_props(url=None, message=None, size="huge", variant="nope") == {
        "url": "",
        "message": "Link copied.",
        "size": "xs",
        "variant": "ghost",
    }
    assert share_host_class("ml-2") == "inline-flex items-center gap-2 ml-2"
    assert share_host_class("  ") == "inline-flex items-center gap-2"


def test_the_sheet_offers_its_owner_a_share_link(client, owner, gang):
    client.force_login(owner)
    url = reverse("n26-gang", args=[gang.pk])

    body = client.get(url).content.decode()
    found = share_host(body, url)

    assert found is not None
    host, props, link = found
    assert props["message"] == "Link copied."
    assert props["size"] == "xs"
    assert props["variant"] == "ghost"
    assert host["class"] == ["inline-flex", "items-center", "gap-2"]
    assert "x-data" not in host.decode_contents()
    assert link["aria-label"] == "Share"
    assert "clicked($event)" not in body
    assert str(icons.resolve("share-2").body) in body
    assert "Link copied." in body


def test_a_visitor_gets_the_same_share_link(client, gang):
    url = reverse("n26-gang", args=[gang.pk])

    body = client.get(url).content.decode()

    assert share_host(body, url) is not None


def test_the_edit_page_has_no_share_button(client, owner, gang):
    client.force_login(owner)

    body = client.get(reverse("n26-edit-gang", args=[gang.pk])).content.decode()

    assert "clicked($event)" not in body
    assert str(icons.resolve("share-2").body) not in body
