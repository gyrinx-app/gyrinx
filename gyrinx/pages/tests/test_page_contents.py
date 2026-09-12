"""Tests for flat page headings, the contents block and the child listing (#2540)."""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.flatpages.models import FlatPage
from django.template import Context, Template
from django.test import Client, RequestFactory

from gyrinx.pages.admin import FlatPageAdmin, FlatPageOptionsInline
from gyrinx.pages.models import FlatPageOptions
from gyrinx.pages.templatetags.pages import (
    add_heading_links,
    nest_headings,
    parse_headings,
)

User = get_user_model()


def make_page(site, url, title, content="<p>Body.</p>"):
    page = FlatPage.objects.create(url=url, title=title, content=content)
    page.sites.add(site)
    return page


# --- parse_headings -----------------------------------------------------------


def test_parse_headings_returns_html_and_headings_in_document_order():
    parsed = parse_headings("<h2>Intro</h2><p>x</p><h3>Setup</h3>")

    assert [(h.level, h.text, h.slug) for h in parsed.headings] == [
        (2, "Intro", "intro"),
        (3, "Setup", "setup"),
    ]
    assert '<h2 id="intro">' in parsed.html
    assert 'href="#setup"' in parsed.html


def test_parse_headings_deduplicates_slugs_with_numeric_suffixes():
    parsed = parse_headings("<h2>Setup</h2><h2>Setup</h2><h3>Setup</h3>")

    assert [h.slug for h in parsed.headings] == ["setup", "setup-2", "setup-3"]
    assert '<h2 id="setup-2">' in parsed.html
    assert 'href="#setup-3"' in parsed.html


def test_parse_headings_skips_empty_headings_from_the_list_but_still_ids_them():
    parsed = parse_headings("<h2></h2><h2>Real</h2>")

    assert [h.slug for h in parsed.headings] == ["real"]
    assert '<h2 id="section">' in parsed.html


def test_heading_anchor_has_no_hover_underline_class():
    html = add_heading_links("<h2>Intro</h2>")

    assert "link-underline-opacity-75-hover" not in html
    assert 'class="link-underline link-underline-opacity-0 text-reset"' in html


def test_heading_link_icon_is_hidden_from_assistive_tech():
    html = add_heading_links("<h2>Intro</h2>")

    assert (
        '<i aria-hidden="true" class="bi-link-45deg ms-2 text-body-secondary">' in html
    )


def test_nest_headings_nests_by_level():
    parsed = parse_headings(
        "<h2>A</h2><h3>A1</h3><h4>A1a</h4><h3>A2</h3><h2>B</h2><h4>B-deep</h4>"
    )
    tree = nest_headings(parsed.headings)

    def shape(nodes):
        return [(n.slug, shape(n.children)) for n in nodes]

    assert shape(tree) == [
        ("a", [("a1", [("a1a", [])]), ("a2", [])]),
        # A skipped level (h4 straight after h2) still nests under the h2.
        ("b", [("b-deep", [])]),
    ]


def test_nest_headings_does_not_mutate_the_flat_list():
    parsed = parse_headings("<h2>A</h2><h3>A1</h3>")
    nest_headings(parsed.headings)

    assert all(h.children == [] for h in parsed.headings)


# --- page_contents tag --------------------------------------------------------


CONTENT = "<h2>Intro</h2><p>x</p><h3>Setup</h3><h3>Setup</h3><h2>Outro</h2>"


def render_contents(page):
    template = Template("{% load pages %}{% page_contents flatpage %}")
    return template.render(Context({"flatpage": page}))


@pytest.mark.django_db
def test_page_contents_is_off_by_default(site):
    page = make_page(site, "/guide/", "Guide", CONTENT)

    assert render_contents(page).strip() == ""


@pytest.mark.django_db
def test_page_contents_is_off_when_options_exist_but_unticked(site):
    page = make_page(site, "/guide/", "Guide", CONTENT)
    FlatPageOptions.objects.create(page=page, show_contents=False)

    assert render_contents(page).strip() == ""


@pytest.mark.django_db
def test_page_contents_renders_nested_list_with_deduplicated_links(site):
    page = make_page(site, "/guide/", "Guide", CONTENT)
    FlatPageOptions.objects.create(page=page, show_contents=True)

    html = render_contents(page)

    assert 'aria-labelledby="page-contents-heading"' in html
    assert "Contents" in html
    assert 'href="#intro"' in html
    assert 'href="#setup"' in html
    assert 'href="#setup-2"' in html
    assert 'href="#outro"' in html
    # Nested: the two h3s sit inside the first h2's <li>.
    intro = html.index('href="#intro"')
    setup2 = html.index('href="#setup-2"')
    outro = html.index('href="#outro"')
    assert intro < setup2 < outro
    assert html.count("<ol") == 2


@pytest.mark.django_db
def test_page_contents_renders_nothing_for_a_page_without_headings(site):
    page = make_page(site, "/guide/", "Guide", "<p>No headings here.</p>")
    FlatPageOptions.objects.create(page=page, show_contents=True)

    assert render_contents(page).strip() == ""


@pytest.mark.django_db
def test_flat_page_view_shows_contents_only_when_ticked(site):
    page = make_page(site, "/guide/", "Guide", CONTENT)
    client = Client()

    off = client.get(page.url).content.decode()
    assert "flatpage-contents" not in off
    # The body's heading ids are there whether or not the contents block is.
    assert 'id="setup-2"' in off

    FlatPageOptions.objects.create(page=page, show_contents=True)
    on = client.get(page.url).content.decode()
    assert "flatpage-contents" in on
    assert on.index("flatpage-contents") < on.index('id="intro"')


# --- get_child_pages ----------------------------------------------------------


@pytest.mark.django_db
def test_get_child_pages_returns_direct_children_only(site):
    make_page(site, "/help/", "Help")
    make_page(site, "/help/n23/", "N23")
    make_page(site, "/help/n23/gangs/", "N23 gangs")
    make_page(site, "/help/n26/", "N26")
    make_page(site, "/helpers/", "Helpers")

    template = Template(
        "{% load pages %}{% get_child_pages '/help/' as children %}"
        "{% for p in children %}{{ p.url }} {% endfor %}"
    )
    out = template.render(Context({"request": RequestFactory().get("/help/")}))

    assert out.split() == ["/help/n23/", "/help/n26/"]


@pytest.mark.django_db
def test_get_child_pages_accepts_a_prefix_without_trailing_slash(site):
    make_page(site, "/help/", "Help")
    make_page(site, "/help/n23/", "N23")

    template = Template(
        "{% load pages %}{% get_child_pages '/help' as children %}"
        "{% for p in children %}{{ p.url }} {% endfor %}"
    )
    out = template.render(Context({"request": RequestFactory().get("/help/")}))

    assert out.split() == ["/help/n23/"]


@pytest.mark.django_db
def test_flat_page_view_lists_direct_children_only(site):
    help_page = make_page(site, "/help/", "Help")
    make_page(site, "/help/n23/", "N23")
    make_page(site, "/help/n23/gangs/", "N23 gangs")

    html = Client().get(help_page.url).content.decode()

    listing = html[html.index("In Help:") :]
    assert 'href="/help/n23/"' in listing
    assert 'href="/help/n23/gangs/"' not in listing


@pytest.mark.django_db
def test_flat_page_view_has_no_child_listing_for_a_leaf(site):
    make_page(site, "/help/", "Help")
    leaf = make_page(site, "/help/n23/", "N23")

    html = Client().get(leaf.url).content.decode()

    assert "In N23:" not in html


# --- admin inline -------------------------------------------------------------


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser(
        username="admin", email="admin@test.com", password="testpass"
    )


def test_flat_page_admin_has_the_options_inline():
    assert FlatPageOptionsInline in FlatPageAdmin.inlines
    assert FlatPageOptionsInline.max_num == 1


@pytest.mark.django_db
def test_flat_page_change_page_renders_show_contents_checkbox(site, admin_user):
    page = make_page(site, "/guide/", "Guide")
    client = Client()
    client.force_login(admin_user)

    html = client.get(f"/admin/flatpages/flatpage/{page.pk}/change/").content.decode()

    assert 'name="options-0-show_contents"' in html
    assert "Show a list of the page's headings above the content." in html


@pytest.mark.django_db
def test_flat_page_change_page_saves_show_contents(site, admin_user):
    page = make_page(site, "/guide/", "Guide", CONTENT)
    client = Client()
    client.force_login(admin_user)

    data = {
        "url": page.url,
        "title": page.title,
        "content": page.content,
        "sites": [str(site.pk)],
        "template_name": "",
        "options-TOTAL_FORMS": "1",
        "options-INITIAL_FORMS": "0",
        "options-MIN_NUM_FORMS": "0",
        "options-MAX_NUM_FORMS": "1",
        "options-0-page": str(page.pk),
        "options-0-show_contents": "on",
        "flatpagevisibility_set-TOTAL_FORMS": "0",
        "flatpagevisibility_set-INITIAL_FORMS": "0",
        "flatpagevisibility_set-MIN_NUM_FORMS": "0",
        "flatpagevisibility_set-MAX_NUM_FORMS": "1000",
    }
    response = client.post(f"/admin/flatpages/flatpage/{page.pk}/change/", data)

    assert response.status_code == 302, response.content.decode()[:2000]
    assert FlatPageOptions.objects.get(page=page).show_contents is True
    assert "flatpage-contents" in Client().get(page.url).content.decode()
