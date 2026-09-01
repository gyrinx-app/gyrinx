"""Redirects: an old URL keeps working after a page moves.

Worth testing rather than trusting, because the pieces only work together by
convention. `RedirectFallbackMiddleware` acts on a 404 response, our flatpage
route is a catch-all regex that swallows every path ending in a slash, and the
middleware has to sit last in MIDDLEWARE to see the 404 before anything else
does. Any one of those changing breaks redirects silently — an old link starts
404ing and nothing fails.
"""

import pytest
from django.contrib.flatpages.models import FlatPage
from django.contrib.redirects.models import Redirect
from django.contrib.sites.models import Site
from django.test import Client


@pytest.fixture
def moved_help_page(db):
    """A help page that has moved under /help/n23/, with a redirect behind it."""
    site = Site.objects.get_current()
    page = FlatPage.objects.create(
        url="/help/n23/vehicles/",
        title="Using Vehicles",
        content="<p>Drivers, start your engines.</p>",
    )
    page.sites.add(site)
    Redirect.objects.create(
        site=site, old_path="/help/vehicles/", new_path="/help/n23/vehicles/"
    )
    return page


@pytest.mark.django_db
def test_old_url_redirects_to_the_new_one(client: Client, moved_help_page):
    response = client.get("/help/vehicles/")
    assert response.status_code == 301
    assert response.headers["Location"] == "/help/n23/vehicles/"


@pytest.mark.django_db
def test_the_new_url_serves_the_page(client: Client, moved_help_page):
    response = client.get("/help/n23/vehicles/")
    assert response.status_code == 200
    assert b"start your engines" in response.content


@pytest.mark.django_db
def test_redirect_survives_the_flatpage_catch_all(client: Client, moved_help_page):
    """The catch-all route matches /help/vehicles/ before the middleware sees it.

    It has to 404 for the middleware to do anything, so this asserts the
    interaction rather than the middleware in isolation.
    """
    assert not FlatPage.objects.filter(url="/help/vehicles/").exists()
    assert client.get("/help/vehicles/").status_code == 301


@pytest.mark.django_db
def test_unknown_url_still_404s(client: Client):
    """No redirect row means the 404 is left alone."""
    assert client.get("/help/does-not-exist/").status_code == 404


@pytest.mark.django_db
def test_empty_new_path_returns_gone(client: Client):
    """A blank new_path retires a URL properly instead of leaving a bare 404."""
    site = Site.objects.get_current()
    Redirect.objects.create(site=site, old_path="/help/retired/", new_path="")
    assert client.get("/help/retired/").status_code == 410


@pytest.mark.django_db
def test_redirect_does_not_match_when_a_query_string_is_present(
    client: Client, moved_help_page
):
    """Documents a real edge: matching uses the full path, query string included.

    So a bookmarked `/help/vehicles/?from=nav` does NOT hit the redirect. Pinned
    here so the behaviour is a known limitation rather than a surprise — if this
    ever needs fixing it wants a custom middleware subclass, not a config change.
    """
    assert client.get("/help/vehicles/?from=nav").status_code == 404


DISCORD_INVITE = "https://discord.gg/WnJFKfyEuj"


@pytest.fixture
def discord_redirect(db):
    """The /discord/ vanity URL. Tests rebuild the DB with --nomigrations,
    so the 0008 data migration never runs here — seed the same row."""
    site = Site.objects.get_current()
    return Redirect.objects.create(
        site=site, old_path="/discord/", new_path=DISCORD_INVITE
    )


@pytest.mark.django_db
def test_discord_path_redirects_to_the_invite(client: Client, discord_redirect):
    response = client.get("/discord/")
    assert response.status_code == 301
    assert response.headers["Location"] == DISCORD_INVITE


@pytest.mark.django_db
def test_discord_path_without_slash_goes_straight_to_the_invite(
    client: Client, discord_redirect
):
    """gyrinx.app/discord is the URL people will type.

    RedirectFallbackMiddleware sits last and acts on the 404 before
    CommonMiddleware's APPEND_SLASH can hop to /discord/. It then looks up
    the slashed old_path itself, so this is one 301, not two.
    """
    response = client.get("/discord")
    assert response.status_code == 301
    assert response.headers["Location"] == DISCORD_INVITE
