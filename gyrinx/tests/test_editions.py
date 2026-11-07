"""Edition cookies, root redirects and navigation on shared pages."""

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
    """Shared pages preserve the remembered edition."""
    client.force_login(user)
    client.cookies[COOKIE_NAME] = "n26"
    response = client.get("/notifications/")
    assert response.status_code == 200
    assert COOKIE_NAME not in response.cookies


def test_the_memory_is_not_rewritten_when_it_already_says_so(client, user):
    """Avoid redundant Set-Cookie headers when the edition already matches."""
    client.force_login(user)
    client.cookies[COOKIE_NAME] = "n23"
    assert COOKIE_NAME not in client.get("/").cookies


def test_the_root_sends_an_n26_reader_back_to_n26(client, user):
    client.force_login(user)
    client.cookies[COOKIE_NAME] = "n26"
    response = client.get("/")
    assert response.status_code == 302
    assert response["Location"] == "/n26/"
    # Root responses depend on the edition cookie.
    assert "Cookie" in response.get("Vary", "")


def test_the_root_stays_put_for_a_classic_reader(client, user):
    client.force_login(user)
    client.cookies[COOKIE_NAME] = "n23"
    assert client.get("/").status_code == 200


def test_a_reader_with_no_memory_gets_the_classic_app(client, user):
    client.force_login(user)
    assert client.get("/").status_code == 200


def test_a_cookie_naming_no_edition_is_ignored(client, user):
    """Ignore unknown edition cookies when choosing the root destination."""
    client.force_login(user)
    client.cookies[COOKIE_NAME] = "n99"
    assert client.get("/").status_code == 200


def test_saying_so_explicitly_is_how_a_reader_leaves_n26(client, user):
    """Use an explicit root choice to return from N26 to N23."""
    client.force_login(user)
    client.cookies[COOKIE_NAME] = "n26"
    response = client.get("/?edition=n23")
    assert response.status_code == 302
    assert remembered(response) == "n23"
    assert client.get("/").status_code == 200


def test_the_choice_does_not_stay_in_the_address(client, user):
    """Remove the edition instruction before the URL can be bookmarked or shared."""
    client.force_login(user)
    client.cookies[COOKIE_NAME] = "n26"
    response = client.get("/?edition=n23")
    assert response.status_code == 302
    assert response["Location"] == "/"


def test_the_rest_of_the_address_survives_the_choice_being_taken_out(client, user):
    client.force_login(user)
    response = client.get("/?edition=n23&q=ashen")
    assert response.status_code == 302
    assert response["Location"] == "/?q=ashen"


def test_the_word_edition_is_only_the_sites_at_the_root(client, user):
    """Interpret the edition parameter only at the site root, preserving page-specific uses elsewhere."""
    client.force_login(user)
    client.cookies[COOKIE_NAME] = "n26"
    response = client.get("/notifications/?edition=n23")
    assert response.status_code == 200
    assert COOKIE_NAME not in response.cookies


def test_the_choice_lands_somewhere_rather_than_bouncing_for_ever(client, user):
    """An explicit edition choice must resolve without a redirect loop."""
    client.force_login(user)
    client.cookies[COOKIE_NAME] = "n26"
    assert client.get("/?edition=n23", follow=True).status_code == 200


def test_a_visitor_is_neither_remembered_nor_redirected(client):
    """Anonymous readers receive neither an edition cookie nor an edition redirect."""
    client.cookies[COOKIE_NAME] = "n26"
    response = client.get("/")
    assert response.status_code == 200
    assert COOKIE_NAME not in response.cookies


def test_the_pill_on_a_shared_page_shows_the_remembered_edition(client, user):
    """Use the remembered edition for navigation on shared pages."""
    client.force_login(user)
    client.cookies[COOKIE_NAME] = "n26"
    body = client.get("/notifications/").content.decode()
    assert 'aria-current="true">N26</a>' in body
    assert 'href="/?edition=n23"' in body


def test_the_pill_on_a_shared_page_falls_back_to_the_classic_app(client, user):
    client.force_login(user)
    body = client.get("/notifications/").content.decode()
    assert 'aria-current="true">N23</a>' in body
    assert 'href="/?edition=n23"' not in body


def test_the_classic_bar_marks_itself_current_inside_the_edition(client, user):
    client.force_login(user)
    body = client.get("/n23/lists/").content.decode()
    assert 'aria-current="true">N23</a>' in body
