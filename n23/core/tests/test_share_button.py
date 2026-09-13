"""The Share button on the gang and campaign pages.

The control is a link to the page itself, so it works with no script; the
[data-share-url] hook is what index.js takes over. Edit pages carry none.
"""

import re

import pytest
from django.urls import reverse

UNLISTED = "This gang is unlisted, so only people with the link can open it."


def share_link(body, url):
    """The <a> carrying data-share-url for `url`, or None."""
    match = re.search(rf'<a\s[^>]*data-share-url="{re.escape(url)}"[^>]*>', body)
    return match.group(0) if match else None


@pytest.mark.django_db
def test_gang_page_share_is_a_link_to_the_gang(client, user, make_list):
    lst = make_list("Sump Rats", public=True)
    client.force_login(user)
    url = reverse("core:list", args=[lst.id])

    body = client.get(url).content.decode()

    link = share_link(body, url)
    assert link is not None
    assert f'href="{url}"' in link
    assert "Link copied." in body
    assert UNLISTED not in body


@pytest.mark.django_db
def test_unlisted_gang_says_so_when_the_link_is_copied(client, user, make_list):
    lst = make_list("Sump Rats", public=False)
    client.force_login(user)
    url = reverse("core:list", args=[lst.id])

    body = client.get(url).content.decode()

    assert share_link(body, url) is not None
    assert UNLISTED in body


@pytest.mark.django_db
def test_a_visitor_to_a_public_gang_gets_the_share_link(client, make_list):
    lst = make_list("Sump Rats", public=True)
    url = reverse("core:list", args=[lst.id])

    body = client.get(url).content.decode()

    assert share_link(body, url) is not None


@pytest.mark.django_db
def test_gang_edit_page_has_no_share_button(client, user, make_list):
    lst = make_list("Sump Rats", public=True)
    client.force_login(user)

    body = client.get(reverse("core:list-edit", args=[lst.id])).content.decode()

    assert "data-share-url" not in body


@pytest.mark.django_db
def test_gang_share_link_carries_a_card_override(
    client, user, make_list, make_list_fighter
):
    """A ?set_<fighter_id>= address shows a particular card for that fighter
    and is meant to be passed around, so the share link keeps it."""
    lst = make_list("Sump Rats", public=True)
    fighter = make_list_fighter(lst, "Vex")
    client.force_login(user)
    url = reverse("core:list", args=[lst.id])

    body = client.get(f"{url}?set_{fighter.id}=default").content.decode()

    link = share_link(body, f"{url}?set_{fighter.id}=default")
    assert link is not None
    assert f'href="{url}?set_{fighter.id}=default"' in link


@pytest.mark.django_db
def test_gang_share_link_drops_other_query_noise(client, user, make_list):
    """Only the card overrides travel; a flash marker or an unknown key
    is not part of what the page shows."""
    lst = make_list("Sump Rats", public=True)
    client.force_login(user)
    url = reverse("core:list", args=[lst.id])

    body = client.get(f"{url}?flash=abc&set_nonsense=1").content.decode()

    assert share_link(body, url) is not None
    assert "flash=abc" not in body.split("data-share-url")[1][:200]


@pytest.mark.django_db
def test_gang_print_page_has_no_share_button(client, user, make_list):
    """The printable sheet renders the same include with print set, and a
    share link on paper is a link to nowhere."""
    lst = make_list("Sump Rats", public=True)
    client.force_login(user)

    body = client.get(reverse("core:list-print", args=[lst.id])).content.decode()

    assert "data-share-url" not in body
    assert "Link copied." not in body


@pytest.mark.django_db
def test_campaign_page_share_is_a_link_to_the_campaign(client, user, make_campaign):
    campaign = make_campaign("Dust Falls", public=True)
    client.force_login(user)
    url = reverse("core:campaign", args=[campaign.id])

    body = client.get(url).content.decode()

    link = share_link(body, url)
    assert link is not None
    assert f'href="{url}"' in link
    assert "Link copied." in body


@pytest.mark.django_db
def test_a_visitor_to_a_public_campaign_gets_the_share_link(client, make_campaign):
    campaign = make_campaign("Dust Falls", public=True)
    url = reverse("core:campaign", args=[campaign.id])

    body = client.get(url).content.decode()

    assert share_link(body, url) is not None


@pytest.mark.django_db
def test_campaign_edit_page_has_no_share_button(client, user, make_campaign):
    campaign = make_campaign("Dust Falls", public=True)
    client.force_login(user)

    body = client.get(
        reverse("core:campaign-edit", args=[campaign.id])
    ).content.decode()

    assert "data-share-url" not in body
