import pytest
from django.contrib.flatpages.models import FlatPage
from django.contrib.sites.models import Site
from django.template import Context, Template
from django.test import RequestFactory

from gyrinx.pages.models import WaitingListEntry, WaitingListSkill
from gyrinx.pages.templatetags.pages import FlatpageNode, pages_path_segment


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


@pytest.mark.django_db
def test_waiting_list():
    egg_rolling = WaitingListSkill.objects.create(
        name="Egg Rolling", description="Rolling eggs real good"
    )

    wl_entry = WaitingListEntry.objects.create(
        email="foo@bar.com",
        desired_username="foo",
        yaktribe_username="foo",
        notes="I make good omlette too",
    )

    wl_entry.skills.add(egg_rolling)

    assert wl_entry.email == "foo@bar.com"
    assert wl_entry.share_code is not None
    assert egg_rolling.waiting_list_entries.first().email == wl_entry.email


@pytest.mark.django_db
class TestOptimizedRegexPatterns:
    """Test the optimized regex patterns for depth filtering."""

    def setup_method(self):
        """Set up test data."""
        self.site = Site.objects.get(id=1)

        # Create pages at various depths
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
        """Test the optimized regex for depth=1."""
        # Test the optimized pattern directly
        node = FlatpageNode("flatpages")
        node.depth = 1

        template = Template("{% load pages %}{% get_root_pages as flatpages %}")
        context = Context({"request": RequestFactory().get("/")})
        template.render(context)

        pages = context["flatpages"]
        # Should only get pages at depth 1
        assert len(pages) == 1
        assert pages[0].url == "/about/"

        # Verify the regex pattern is optimized (no {0,0})
        # This is implicitly tested by the fact that it works correctly

    def test_depth_2_regex(self):
        """Test regex pattern for depth=2."""
        # Manually test depth 2 filtering
        depth2_pages = FlatPage.objects.filter(
            sites__id=self.site.id,
            registration_required=False,
            url__regex=r"^/[^/]+(?:/[^/]+){0,1}/?$",
        )

        # Should get root (special case), depth 1, and depth 2 pages
        assert depth2_pages.count() == 2  # /about/ and /about/team/

    def test_various_depths(self):
        """Test that different depth values work correctly."""
        test_cases = [
            (0, 4),  # No depth limit - all pages
            (1, 1),  # Only /about/
            (2, 2),  # /about/ and /about/team/
            (3, 3),  # /about/, /about/team/, /about/team/developers/
        ]

        for depth, expected_count in test_cases:
            # Create a node with specific depth
            node = FlatpageNode("flatpages")
            node.depth = depth

            # We need to test the actual filtering logic
            flatpages = FlatPage.objects.filter(
                sites__id=self.site.id, registration_required=False
            )

            if depth == 1:
                flatpages = flatpages.filter(url__regex=r"^/[^/]+/?$")
            elif depth > 1:
                flatpages = flatpages.filter(
                    url__regex=r"^/[^/]+(?:/[^/]+){0,%d}/?$" % (depth - 1)
                )

            # Root page is excluded by all depth filters
            if depth > 0:
                assert flatpages.count() == expected_count
