"""The default flat-page template renders responsive documentation chrome."""

import pytest
from bs4 import BeautifulSoup
from django.contrib.flatpages.models import FlatPage

from gyrinx.pages.models import FlatPageOptions

pytestmark = pytest.mark.django_db


def make_page(site, *, url, title="Guide", content="<p>Body.</p>"):
    page = FlatPage.objects.create(url=url, title=title, content=content)
    page.sites.add(site)
    return page


def get_document(client, page):
    response = client.get(page.url)
    assert response.status_code == 200
    return BeautifulSoup(response.content, "html.parser")


@pytest.mark.parametrize(
    ("heading_html", "legacy_show_contents", "shows_toc"),
    [
        ("<h2>Only section</h2>", True, False),
        ("<h2>First section</h2><h2>Second section</h2>", False, True),
    ],
)
def test_toc_uses_automatic_heading_threshold_and_ignores_legacy_flag(
    client, site, heading_html, legacy_show_contents, shows_toc
):
    page = make_page(site, url="/guide/", content=heading_html)
    FlatPageOptions.objects.create(
        page=page,
        show_contents=legacy_show_contents,
    )

    document = get_document(client, page)

    assert (document.select_one("aside.flatpage-toc") is not None) is shows_toc
    layout = document.select_one(".flatpage-layout")
    assert ("flatpage-layout--with-toc" in layout.get("class", [])) is shows_toc


@pytest.mark.parametrize(
    ("url", "content", "is_help", "shows_toc"),
    [
        ("/guide/", "<p>Body.</p>", False, False),
        ("/guide/", "<h2>One</h2><h2>Two</h2>", False, True),
        ("/help/", "<p>Body.</p>", True, False),
        ("/help/", "<h2>One</h2><h3>Two</h3>", True, True),
    ],
)
def test_layout_only_renders_navigation_columns_with_content(
    client, site, url, content, is_help, shows_toc
):
    page = make_page(site, url=url, content=content)

    document = get_document(client, page)

    assert document.select_one("aside.flatpage-help-nav") is not None
    assert (document.select_one("aside.flatpage-toc") is not None) is shows_toc
    trigger = document.select_one(
        '.flatpage-heading button[aria-label="Help & documentation"]'
    )
    assert trigger is not None
    assert not trigger.get_text(strip=True)


def test_default_page_has_one_main_landmark(client, site):
    page = make_page(site, url="/help/", content="<h2>One</h2><h2>Two</h2>")

    document = get_document(client, page)

    assert len(document.find_all("main")) == 1
    assert document.select_one("main article.flatpage-main") is not None


@pytest.mark.parametrize("current_url", ["/help/", "/about/"])
def test_top_level_navigation_is_shared_by_sidebar_drawer_and_noscript(
    client, site, current_url
):
    pages = {
        url: make_page(site, url=url, title=title)
        for url, title in [
            ("/about/", "About"),
            ("/help/", "Help"),
            ("/help/n26/", "N26 Help"),
            ("/getinvolved/", "Get involved"),
        ]
    }
    document = get_document(client, pages[current_url])

    for navigation in document.select('nav[aria-label="Help and documentation"]') + [
        document.select_one("aside.flatpage-help-nav")
    ]:
        assert {link["href"] for link in navigation.select("a")} == set(pages)
        assert navigation.select_one('a[aria-current="page"]')["href"] == current_url


@pytest.mark.parametrize("url", ["/help/", "/guide/"])
def test_noscript_toc_is_outside_alpine_teleport_templates(client, site, url):
    page = make_page(site, url=url, content="<h2>One</h2><h2>Two</h2>")

    document = get_document(client, page)

    fallbacks = document.select("article.flatpage-main noscript")
    assert len(fallbacks) == 1
    assert fallbacks[0].find_parent("template") is None
    assert "On this page" in fallbacks[0].get_text(" ", strip=True)
    assert "Help & documentation" in fallbacks[0].get_text(" ", strip=True)


def test_authored_content_is_sanitised_before_reaching_the_layout(client, site):
    page = make_page(
        site,
        url="/guide/",
        content=(
            '<script>alert("bad")</script>'
            '<h2 onclick="alert(1)">Safe heading</h2>'
            "<h2>Second heading</h2>"
            "<p>Safe body.</p>"
        ),
    )

    document = get_document(client, page)
    article = document.select_one("article.flatpage-main")
    safe_heading = article.select_one("h2#safe-heading")

    assert article.find("script", string=lambda value: value and "bad" in value) is None
    assert safe_heading.get_text(" ", strip=True).startswith("Safe heading")
    assert not safe_heading.has_attr("onclick")
    assert article.find("p", string="Safe body.") is not None
