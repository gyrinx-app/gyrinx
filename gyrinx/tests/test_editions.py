"""The site remembers which edition a reader is in.

Two editions, and a handful of pages both share — the inbox, the account
settings, the site root. An edition page says which edition it is by its own
address; a shared page cannot. So the last edition an address named is kept in a
cookie: the root sends a signed-in reader back to it, and the edition pill on a
shared page shows it.
"""

import pytest

from gyrinx.editions import COOKIE_NAME

pytestmark = pytest.mark.django_db


def remembered(response):
    """The edition the response asks the browser to remember, if it asks."""
    morsel = response.cookies.get(COOKIE_NAME)
    return morsel.value if morsel else None


def test_the_root_is_remembered_as_the_classic_app(client, user):
    client.force_login(user)
    assert remembered(client.get("/")) == "n23"


def test_a_classic_address_is_remembered(client, user):
    client.force_login(user)
    assert remembered(client.get("/n23/lists/")) == "n23"


def test_an_n26_address_is_remembered(client, user):
    client.force_login(user)
    assert remembered(client.get("/n26/")) == "n26"


def test_a_shared_page_leaves_the_memory_alone(client, user):
    """The inbox and the account settings belong to neither edition. If
    opening one moved the memory, every reader would be pinned to whichever
    edition they happened to be in the first time they looked at their
    account, and never moved again."""
    client.force_login(user)
    client.cookies[COOKIE_NAME] = "n26"
    response = client.get("/notifications/")
    assert response.status_code == 200
    assert COOKIE_NAME not in response.cookies


def test_the_memory_is_not_rewritten_when_it_already_says_so(client, user):
    """Otherwise every page of the edition ships a Set-Cookie header saying
    what the browser already knows."""
    client.force_login(user)
    client.cookies[COOKIE_NAME] = "n23"
    assert COOKIE_NAME not in client.get("/").cookies


def test_the_root_sends_an_n26_reader_back_to_n26(client, user):
    client.force_login(user)
    client.cookies[COOKIE_NAME] = "n26"
    response = client.get("/")
    assert response.status_code == 302
    assert response["Location"] == "/n26/"
    # The root answers two different ways depending on the cookie.
    assert "Cookie" in response.get("Vary", "")


def test_the_root_stays_put_for_a_classic_reader(client, user):
    client.force_login(user)
    client.cookies[COOKIE_NAME] = "n23"
    assert client.get("/").status_code == 200


def test_a_reader_with_no_memory_gets_the_classic_app(client, user):
    client.force_login(user)
    assert client.get("/").status_code == 200


def test_a_cookie_naming_no_edition_is_ignored(client, user):
    """A stale or hand-edited value must not be able to send anyone
    anywhere."""
    client.force_login(user)
    client.cookies[COOKIE_NAME] = "n99"
    assert client.get("/").status_code == 200


def test_saying_so_explicitly_is_how_a_reader_leaves_n26(client, user):
    """The way out of n26 is a link to the site root, which is the very
    address the memory sends an n26 reader back from. The parameter is the
    link saying the reader means it."""
    client.force_login(user)
    client.cookies[COOKIE_NAME] = "n26"
    response = client.get("/?edition=n23")
    assert response.status_code == 200
    assert remembered(response) == "n23"
    # And it sticks: the next plain visit to the root stays there.
    assert client.get("/").status_code == 200


def test_a_visitor_is_neither_remembered_nor_redirected(client):
    """The pill is a signed-in reader's control, so a visitor collects no
    cookie they have no use for — and is never bounced by one."""
    client.cookies[COOKIE_NAME] = "n26"
    response = client.get("/")
    assert response.status_code == 200
    assert COOKIE_NAME not in response.cookies


def test_the_pill_on_a_shared_page_shows_the_remembered_edition(client, user):
    """The inbox is drawn in the site's own chrome, which names no edition.
    The pill is what says where the reader is, and the way back into it."""
    client.force_login(user)
    client.cookies[COOKIE_NAME] = "n26"
    body = client.get("/notifications/").content.decode()
    assert 'aria-current="true">N26</a>' in body
    # And the way out of n26 says the reader means it.
    assert 'href="/?edition=n23"' in body


def test_the_pill_on_a_shared_page_falls_back_to_the_classic_app(client, user):
    client.force_login(user)
    body = client.get("/notifications/").content.decode()
    assert 'aria-current="true">N23</a>' in body
    # Already there, so the link to it carries no choice to make.
    assert 'href="/?edition=n23"' not in body


def test_the_classic_bar_marks_itself_current_inside_the_edition(client, user):
    client.force_login(user)
    body = client.get("/n23/lists/").content.decode()
    assert 'aria-current="true">N23</a>' in body
