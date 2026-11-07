"""Redirect fallback after a flatpage lookup returns 404."""

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
    """Exercise redirect middleware after the catch-all flatpage route returns 404."""
    assert not FlatPage.objects.filter(url="/help/vehicles/").exists()
    assert client.get("/help/vehicles/").status_code == 301


@pytest.mark.django_db
def test_unknown_url_still_404s(client: Client):

    assert client.get("/help/does-not-exist/").status_code == 404


@pytest.mark.django_db
def test_empty_new_path_returns_gone(client: Client):

    site = Site.objects.get_current()
    Redirect.objects.create(site=site, old_path="/help/retired/", new_path="")
    assert client.get("/help/retired/").status_code == 410


@pytest.mark.django_db
def test_redirect_does_not_match_when_a_query_string_is_present(
    client: Client, moved_help_page
):
    """Match the full request path, including its query string.

    A redirect stored for the bare URL does not match that URL with a query.
    """
    assert client.get("/help/vehicles/?from=nav").status_code == 404
