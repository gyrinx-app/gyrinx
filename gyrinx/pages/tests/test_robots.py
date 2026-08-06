import re
import uuid

import pytest
from django.urls import Resolver404, resolve


@pytest.mark.django_db
def test_robots_txt_served_as_plain_text(client):
    response = client.get("/robots.txt")
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/plain")


@pytest.mark.django_db
def test_robots_txt_policy(client):
    """Amazonbot and Bytespider are excluded entirely; fighter detail pages,
    print views, accounts, and admin are disallowed for every agent."""
    body = client.get("/robots.txt").content.decode()
    sections = body.split("\n\n")
    assert "User-agent: Amazonbot\nDisallow: /" in sections
    assert "User-agent: Bytespider\nDisallow: /" in sections
    general = [s for s in sections if s.startswith("User-agent: *")][0]
    assert "Disallow: /n23/list/*/fighter/" in general
    assert "Disallow: /n23/list/*/print" in general
    assert "Disallow: /accounts/" in general
    assert "Disallow: /admin/" in general


@pytest.mark.django_db
def test_every_disallowed_edition_path_resolves_to_a_real_view(client):
    """Each edition Disallow must name a path this site actually serves.

    The previous version of this test asserted the literal string
    ``Disallow: /list/*/fighter/`` was present. When the edition moved under
    ``/n23/`` (#2110) that rule stopped matching any real URL, but the string was
    still in the file, so the test kept passing — and every fighter and print
    page silently became crawlable. Asserting the text says nothing about whether
    the rule does anything.

    So substitute a real id for each wildcard and require the path to resolve. A
    Disallow that resolves nowhere is protecting nothing.
    """
    body = client.get("/robots.txt").content.decode()
    general = [s for s in body.split("\n\n") if s.startswith("User-agent: *")][0]

    paths = re.findall(r"^Disallow: (\S+)$", general, re.M)
    assert paths, "expected Disallow rules for the catch-all agent"

    # /accounts/ and /admin/ are third-party URLconfs mounted at a prefix; the
    # bare prefix is not itself a route, so they are checked by the policy test
    # above rather than resolved here.
    edition_paths = [p for p in paths if p.startswith("/n23/")]
    assert edition_paths, "expected the edition paths to be covered"

    unresolved = []
    for path in edition_paths:
        probe = path.replace("*", str(uuid.uuid4()))
        try:
            resolve(probe if probe.endswith("/") else probe + "/")
        except Resolver404:
            unresolved.append(path)

    assert not unresolved, (
        f"robots.txt Disallow rules matching no route: {unresolved}. "
        "A rule that resolves nowhere protects nothing — check these against "
        "n23/core/urls/__init__.py."
    )
