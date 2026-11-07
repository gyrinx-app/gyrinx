import pytest
from django.contrib.flatpages.models import FlatPage
from django.contrib.sites.models import Site
from django.template import Context, Template
from django.test import RequestFactory

from gyrinx.pages.templatetags.pages import (
    FlatpageNode,
    active_flatpage,
    active_flatpage_aria,
    pages_path_segment,
)


@pytest.mark.django_db
def test_gyrinx_site():
    site = Site.objects.get(id=1)
    assert site.domain == "gyrinx.app"
    assert site.name == "gyrinx.app"


def test_pages_path_segment():
    assert pages_path_segment("/foo/bar/baz/", 1) == "/foo/"
    assert pages_path_segment("/foo/bar/baz/", 2) == "/foo/bar/"
    assert pages_path_segment("/foo/bar/baz/", 3) == "/foo/bar/baz/"
    assert pages_path_segment("/foo/bar/baz/", 4) == "/foo/bar/baz/"
    assert pages_path_segment("/foo/bar/baz/", 0) == "/"
    assert pages_path_segment("/foo/bar/baz/", -1) == "/"


def test_active_flatpage_returns_active_when_path_matches():

    factory = RequestFactory()
    request = factory.get("/help/")
    context = Context({"request": request})

    result = active_flatpage(context, "/help/")
    assert result == "active"


def test_active_flatpage_returns_empty_when_path_does_not_match():

    factory = RequestFactory()
    request = factory.get("/about/")
    context = Context({"request": request})

    result = active_flatpage(context, "/help/")
    assert result == ""


def test_active_flatpage_normalizes_url_without_trailing_slash():

    factory = RequestFactory()
    request = factory.get("/help/")
    context = Context({"request": request})

    result = active_flatpage(context, "/help")
    assert result == "active"


def test_active_flatpage_normalizes_request_path_without_trailing_slash():

    factory = RequestFactory()
    request = factory.get("/help")
    context = Context({"request": request})

    result = active_flatpage(context, "/help/")
    assert result == "active"


def test_active_flatpage_aria_normalizes_request_path_without_trailing_slash():

    factory = RequestFactory()
    request = factory.get("/help")
    context = Context({"request": request})

    result = active_flatpage_aria(context, "/help/")
    assert result == 'aria-current="page"'


def test_active_flatpage_returns_empty_when_no_request():

    context = Context({})

    result = active_flatpage(context, "/help/")
    assert result == ""


def test_active_flatpage_aria_returns_aria_when_path_matches():

    factory = RequestFactory()
    request = factory.get("/help/")
    context = Context({"request": request})

    result = active_flatpage_aria(context, "/help/")
    assert result == 'aria-current="page"'


def test_active_flatpage_aria_returns_empty_when_path_does_not_match():

    factory = RequestFactory()
    request = factory.get("/about/")
    context = Context({"request": request})

    result = active_flatpage_aria(context, "/help/")
    assert result == ""


def test_active_flatpage_aria_returns_empty_when_no_request():

    context = Context({})

    result = active_flatpage_aria(context, "/help/")
    assert result == ""


@pytest.mark.django_db
class TestOptimizedRegexPatterns:
    """Filter flatpages by URL depth without including root pages."""

    def setup_method(self):
        """Create root and nested pages through depth three."""
        self.site = Site.objects.get(id=1)

        self.root_page = FlatPage.objects.create(
            url="/",
            title="Root",
            content="Root content",
            registration_required=False,
        )
        self.root_page.sites.add(self.site)

        self.depth1_page = FlatPage.objects.create(
            url="/about/",
            title="About",
            content="About content",
            registration_required=False,
        )
        self.depth1_page.sites.add(self.site)

        self.depth2_page = FlatPage.objects.create(
            url="/about/team/",
            title="Team",
            content="Team content",
            registration_required=False,
        )
        self.depth2_page.sites.add(self.site)

        self.depth3_page = FlatPage.objects.create(
            url="/about/team/developers/",
            title="Developers",
            content="Developers content",
            registration_required=False,
        )
        self.depth3_page.sites.add(self.site)

    def test_depth_1_regex_optimization(self):

        node = FlatpageNode("flatpages")
        node.depth = 1

        template = Template("{% load pages %}{% get_root_pages as flatpages %}")
        context = Context({"request": RequestFactory().get("/")})
        template.render(context)

        pages = context["flatpages"]
        assert len(pages) == 1
        assert pages[0].url == "/about/"

    def test_depth_2_regex(self):

        depth2_pages = FlatPage.objects.filter(
            sites__id=self.site.id,
            registration_required=False,
            url__regex=r"^/[^/]+(?:/[^/]+){0,1}/?$",
        )

        assert depth2_pages.count() == 2  # /about/ and /about/team/

    def test_various_depths(self):

        test_cases = [
            (0, 4),  # No depth limit - all pages
            (1, 1),  # Only /about/
            (2, 2),  # /about/ and /about/team/
            (3, 3),  # /about/, /about/team/, /about/team/developers/
        ]

        for depth, expected_count in test_cases:
            node = FlatpageNode("flatpages")
            node.depth = depth

            flatpages = FlatPage.objects.filter(
                sites__id=self.site.id, registration_required=False
            )

            if depth == 1:
                flatpages = flatpages.filter(url__regex=r"^/[^/]+/?$")
            elif depth > 1:
                flatpages = flatpages.filter(
                    url__regex=r"^/[^/]+(?:/[^/]+){0,%d}/?$" % (depth - 1)  # noqa: UP031 - percent-format keeps the regex readable; an f-string needs {{}} doubling
                )

            # Exclude the root page whenever a positive depth filter is applied.
            if depth > 0:
                assert flatpages.count() == expected_count
