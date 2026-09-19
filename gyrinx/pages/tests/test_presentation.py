import pytest
from bs4 import BeautifulSoup
from django.contrib.auth.models import Group
from django.contrib.flatpages.models import FlatPage
from django.db import connection
from django.test.utils import CaptureQueriesContext

from gyrinx.pages.models import FlatPageOptions, FlatPageVisibility
from gyrinx.pages.presentation import (
    build_flatpage_presentation,
    parse_content,
    sanitise_flatpage_html,
)

pytestmark = pytest.mark.django_db


def make_page(site, url, title, content="<p>Body.</p>", **kwargs):
    page = FlatPage.objects.create(url=url, title=title, content=content, **kwargs)
    page.sites.add(site)
    return page


def test_parse_content_sanitises_before_adding_heading_links():
    parsed = parse_content(
        '<script>alert(1)</script><h2 onclick="bad()">Intro '
        '<a href="https://example.com">details</a></h2>'
        '<a href="javascript:bad()">Unsafe</a>'
    )
    document = BeautifulSoup(parsed.html, "html.parser")

    assert document.find("script") is None
    assert "alert(1)" not in parsed.html
    assert document.h2.get("onclick") is None
    assert document.h2.find("a", href="https://example.com") is not None
    assert (
        document.h2.find("a", class_="flatpage-heading-link")["href"]
        == "#intro-details"
    )
    assert document.find("a", string="Unsafe").get("href") is None


def test_default_page_escapes_an_authored_title(client, site):
    page = make_page(
        site,
        "/unsafe-title/",
        '<img src="x" onerror="bad()">Unsafe',
    )

    document = BeautifulSoup(client.get(page.url).content, "html.parser")

    assert document.h1.find("img") is None
    assert document.h1.get_text(strip=True).endswith("Unsafe")


def test_parse_content_replaces_authored_ids_and_deduplicates_fragments():
    parsed = parse_content(
        '<a id="setup"></a><h2 id="authored">Setup</h2><h2>Setup</h2>'
    )

    assert [heading.slug for heading in parsed.headings] == ["setup-2", "setup-3"]
    assert 'id="authored"' not in parsed.html


def test_sanitiser_retains_a_sandboxed_local_embed():
    cleaned = sanitise_flatpage_html(
        '<iframe src="/list/one/fighter/two/embed?theme=auto" '
        'title="Fighter card" width="400" height="600" '
        'sandbox="allow-scripts" onload="bad()"></iframe>'
    )
    iframe = BeautifulSoup(cleaned, "html.parser").iframe

    assert iframe["src"] == "/list/one/fighter/two/embed?theme=auto"
    assert iframe["sandbox"] == []
    assert iframe["loading"] == "lazy"
    assert iframe["title"] == "Fighter card"
    assert iframe["width"] == "400"
    assert iframe["height"] == "600"
    assert iframe.get("onload") is None
    assert iframe["class"] == ["flatpage-embed"]


@pytest.mark.parametrize(
    "src",
    ["javascript:bad()", "//evil.test/embed", r"/\\evil.test/embed"],
)
def test_sanitiser_drops_unsafe_embed_sources(src):
    cleaned = sanitise_flatpage_html(f'<iframe src="{src}"></iframe>')

    assert BeautifulSoup(cleaned, "html.parser").iframe is None


def test_sanitiser_replaces_an_external_embed_with_a_link():
    cleaned = sanitise_flatpage_html(
        '<iframe src="https://video.example/embed/1" title="Watch the video"></iframe>'
    )
    link = BeautifulSoup(cleaned, "html.parser").a

    assert link["href"] == "https://video.example/embed/1"
    assert link.get_text() == "Watch the video"


def test_presentation_builds_an_automatic_h2_h3_toc(site):
    page = make_page(
        site,
        "/guide/",
        "Guide",
        "<h1>Overview</h1><h2>Start</h2><h4>Detail</h4><h3>Next</h3>",
    )

    presentation = build_flatpage_presentation(page=page, site_id=site.pk, user=None)

    assert presentation.show_toc is True
    assert [heading.text for heading in presentation.headings] == [
        "Overview",
        "Start",
        "Detail",
        "Next",
    ]
    assert [heading.text for heading in presentation.toc] == ["Start"]
    assert [heading.text for heading in presentation.toc[0].children] == ["Next"]


def test_presentation_requires_two_eligible_headings_for_toc(site):
    page = make_page(site, "/guide/", "Guide", "<h2>Start</h2><h4>Detail</h4>")

    presentation = build_flatpage_presentation(page=page, site_id=site.pk, user=None)

    assert presentation.show_toc is False
    assert [heading.text for heading in presentation.toc] == ["Start"]


def test_presentation_sanitises_the_introduction(site):
    page = make_page(site, "/guide/", "Guide")
    FlatPageOptions.objects.create(
        page=page,
        introduction='<p onclick="bad()">Read first.</p><script>bad()</script>',
    )

    presentation = build_flatpage_presentation(page=page, site_id=site.pk, user=None)

    assert str(presentation.introduction_html) == "<p>Read first.</p>"


def test_help_tree_omits_pages_with_a_missing_ancestor(site):
    root = make_page(site, "/help/", "Help")
    make_page(site, "/help/n26/orphan/", "Orphan")

    presentation = build_flatpage_presentation(page=root, site_id=site.pk, user=None)

    assert [node.page.url for node in presentation.navigation_tree] == ["/help/"]
    assert presentation.navigation_tree[0].children == ()


def test_navigation_includes_only_accessible_top_level_pages(site):
    root = make_page(site, "/help/", "Help")
    about = make_page(site, "/about/", "About")
    restricted = make_page(site, "/private/", "Private")
    FlatPageVisibility.objects.create(page=restricted)
    make_page(site, "/private/child/", "Private child")
    make_page(site, "/members/", "Members", registration_required=True)

    presentation = build_flatpage_presentation(page=root, site_id=site.pk, user=None)

    assert [node.page for node in presentation.navigation_tree] == [about, root]


def test_help_tree_omits_a_restricted_branch_and_keeps_url_order(site):
    root = make_page(site, "/help/", "Help")
    allowed = make_page(site, "/help/a/", "Allowed")
    restricted = make_page(site, "/help/b/", "Restricted")
    make_page(site, "/help/b/child/", "Hidden child")
    gate = FlatPageVisibility.objects.create(page=restricted)
    gate.groups.add(Group.objects.create(name="Members"))

    presentation = build_flatpage_presentation(page=root, site_id=site.pk, user=None)

    assert [node.page for node in presentation.navigation_tree[0].children] == [allowed]


def test_help_context_marks_current_ancestors_and_direct_children(site):
    root = make_page(site, "/help/", "Help")
    section = make_page(site, "/help/n26/", "N26")
    current = make_page(site, "/help/n26/gangs/", "Gangs")
    child = make_page(site, "/help/n26/gangs/create/", "Create")

    presentation = build_flatpage_presentation(page=current, site_id=site.pk, user=None)

    assert presentation.ancestors == (root, section)
    assert presentation.parent == section
    assert presentation.children == (child,)
    root_node = presentation.navigation_tree[0]
    section_node = root_node.children[0]
    current_node = section_node.children[0]
    assert root_node.is_ancestor is True
    assert section_node.is_ancestor is True
    assert current_node.is_current is True


def test_non_help_context_keeps_parent_and_direct_children(site):
    parent = make_page(site, "/about/", "About")
    current = make_page(site, "/about/team/", "Team")
    child = make_page(site, "/about/team/history/", "History")
    make_page(site, "/about/team/history/early/", "Early history")

    presentation = build_flatpage_presentation(page=current, site_id=site.pk, user=None)

    assert presentation.is_help is False
    assert presentation.parent == parent
    assert presentation.children == (child,)


def test_help_tree_query_count_does_not_grow_with_pages(site):
    root = make_page(site, "/help/", "Help")
    for number in range(2):
        make_page(site, f"/help/page-{number:02d}/", f"Page {number}")

    with CaptureQueriesContext(connection) as small_queries:
        build_flatpage_presentation(
            page=FlatPage.objects.get(pk=root.pk), site_id=site.pk, user=None
        )

    for number in range(2, 20):
        make_page(site, f"/help/page-{number:02d}/", f"Page {number}")

    with CaptureQueriesContext(connection) as large_queries:
        build_flatpage_presentation(
            page=FlatPage.objects.get(pk=root.pk), site_id=site.pk, user=None
        )

    assert len(small_queries) == len(large_queries) == 3
