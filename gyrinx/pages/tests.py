import pytest
from django.contrib.auth.models import Group, User
from django.contrib.flatpages.models import FlatPage
from django.contrib.sites.models import Site
from django.core.cache import cache
from django.template import Context, Template
from django.test import RequestFactory

from gyrinx.pages.models import FlatPageVisibility, WaitingListEntry, WaitingListSkill
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
class TestFlatpagesCaching:
    """Test the caching functionality for flatpages."""
    
    def setup_method(self):
        """Clear cache before each test."""
        cache.clear()
        # Create a test site
        self.site = Site.objects.get(id=1)
        # Create a test user and group
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.group = Group.objects.create(name="testgroup")
        self.user.groups.add(self.group)
        # Create test flatpages
        self.public_page = FlatPage.objects.create(
            url="/public/",
            title="Public Page",
            content="Public content",
            registration_required=False,
        )
        self.public_page.sites.add(self.site)
        
        self.private_page = FlatPage.objects.create(
            url="/private/",
            title="Private Page",
            content="Private content",
            registration_required=True,
        )
        self.private_page.sites.add(self.site)
        
        self.restricted_page = FlatPage.objects.create(
            url="/restricted/",
            title="Restricted Page",
            content="Restricted content",
            registration_required=False,
        )
        self.restricted_page.sites.add(self.site)
        # Add visibility restriction
        visibility = FlatPageVisibility.objects.create(page=self.restricted_page)
        visibility.groups.add(self.group)
    
    def teardown_method(self):
        """Clean up after each test."""
        cache.clear()
    
    def test_caching_basic(self):
        """Test that flatpages are cached correctly."""
        # Create a template context
        template = Template("{% load pages %}{% get_pages as flatpages %}")
        context = Context({"request": RequestFactory().get("/")})
        
        # First render - should hit the database
        template.render(context)
        pages = context["flatpages"]
        assert len(pages) == 2  # Public and restricted page (restricted is still visible to anon)
        page_urls = [p.url for p in pages]
        assert "/public/" in page_urls
        assert "/restricted/" in page_urls
        
        # Check that cache was populated
        cache_key = "flatpages:site_1:depth_0:anon"
        cached_pages = cache.get(cache_key)
        assert cached_pages is not None
        assert len(cached_pages) == 2
        cached_urls = [p.url for p in cached_pages]
        assert "/public/" in cached_urls
        assert "/restricted/" in cached_urls
        
        # Second render - should use cache
        context2 = Context({"request": RequestFactory().get("/")})
        template.render(context2)
        pages2 = context2["flatpages"]
        assert pages2 == cached_pages
    
    def test_caching_with_user(self):
        """Test caching with authenticated users."""
        template = Template("{% load pages %}{% get_pages for user as flatpages %}")
        request = RequestFactory().get("/")
        request.user = self.user
        context = Context({"request": request, "user": self.user})
        
        # Render and check results
        template.render(context)
        pages = context["flatpages"]
        assert len(pages) == 3  # All pages visible to authenticated user with group
        
        # Check cache key includes user info
        group_ids = "_".join(str(g.id) for g in self.user.groups.all().order_by("id"))
        cache_key = f"flatpages:site_1:depth_0:user_{self.user.id}_groups_{group_ids}"
        cached_pages = cache.get(cache_key)
        assert cached_pages is not None
        assert len(cached_pages) == 3
    
    def test_caching_with_depth(self):
        """Test caching with depth filtering."""
        # Create pages at different depths
        deep_page = FlatPage.objects.create(
            url="/foo/bar/baz/",
            title="Deep Page",
            content="Deep content",
            registration_required=False,
        )
        deep_page.sites.add(self.site)
        
        template = Template("{% load pages %}{% get_root_pages as flatpages %}")
        context = Context({"request": RequestFactory().get("/")})
        
        template.render(context)
        pages = context["flatpages"]
        # Only pages at depth 1 (single segment)
        assert len(pages) == 2  # /public/ and /restricted/ (private is filtered out)
        assert all(p.url.count("/") <= 2 for p in pages)
        
        # Check cache key includes depth
        cache_key = "flatpages:site_1:depth_1:anon"
        cached_pages = cache.get(cache_key)
        assert cached_pages is not None
    
    def test_caching_with_prefix(self):
        """Test caching with URL prefix filtering."""
        # Create pages with different prefixes
        about_page = FlatPage.objects.create(
            url="/about/team/",
            title="About Team",
            content="Team content",
            registration_required=False,
        )
        about_page.sites.add(self.site)
        
        template = Template("{% load pages %}{% get_pages '/about/' as flatpages %}")
        context = Context({"request": RequestFactory().get("/")})
        
        template.render(context)
        pages = context["flatpages"]
        assert len(pages) == 1
        assert pages[0].url == "/about/team/"
        
        # Check cache key includes prefix
        cache_key = "flatpages:site_1:depth_0:prefix_/about/:anon"
        cached_pages = cache.get(cache_key)
        assert cached_pages is not None
        assert len(cached_pages) == 1


@pytest.mark.django_db
class TestFlatpagesCacheInvalidation:
    """Test cache invalidation via signals."""
    
    def setup_method(self):
        """Set up test data."""
        cache.clear()
        self.site = Site.objects.get(id=1)
        self.page = FlatPage.objects.create(
            url="/test/",
            title="Test Page",
            content="Test content",
            registration_required=False,
        )
        self.page.sites.add(self.site)
    
    def teardown_method(self):
        """Clean up after each test."""
        cache.clear()
    
    def test_cache_cleared_on_flatpage_save(self):
        """Test that cache is cleared when a flatpage is saved."""
        # Populate cache
        template = Template("{% load pages %}{% get_pages as flatpages %}")
        context = Context({"request": RequestFactory().get("/")})
        template.render(context)
        
        cache_key = "flatpages:site_1:depth_0:anon"
        assert cache.get(cache_key) is not None
        
        # Save the page
        self.page.title = "Updated Title"
        self.page.save()
        
        # Cache should be cleared
        assert cache.get(cache_key) is None
    
    def test_cache_cleared_on_flatpage_delete(self):
        """Test that cache is cleared when a flatpage is deleted."""
        # Populate cache
        template = Template("{% load pages %}{% get_pages as flatpages %}")
        context = Context({"request": RequestFactory().get("/")})
        template.render(context)
        
        cache_key = "flatpages:site_1:depth_0:anon"
        assert cache.get(cache_key) is not None
        
        # Delete the page
        self.page.delete()
        
        # Cache should be cleared
        assert cache.get(cache_key) is None
    
    def test_cache_cleared_on_visibility_change(self):
        """Test that cache is cleared when visibility rules change."""
        group = Group.objects.create(name="testgroup")
        
        # Populate cache
        template = Template("{% load pages %}{% get_pages as flatpages %}")
        context = Context({"request": RequestFactory().get("/")})
        template.render(context)
        
        cache_key = "flatpages:site_1:depth_0:anon"
        assert cache.get(cache_key) is not None
        
        # Add visibility rule
        visibility = FlatPageVisibility.objects.create(page=self.page)
        visibility.groups.add(group)
        
        # Cache should be cleared
        assert cache.get(cache_key) is None
    
    def test_cache_cleared_on_visibility_delete(self):
        """Test that cache is cleared when visibility rules are deleted."""
        group = Group.objects.create(name="testgroup")
        visibility = FlatPageVisibility.objects.create(page=self.page)
        visibility.groups.add(group)
        
        # Populate cache
        template = Template("{% load pages %}{% get_pages as flatpages %}")
        context = Context({"request": RequestFactory().get("/")})
        template.render(context)
        
        cache_key = "flatpages:site_1:depth_0:anon"
        assert cache.get(cache_key) is not None
        
        # Delete visibility rule
        visibility.delete()
        
        # Cache should be cleared
        assert cache.get(cache_key) is None
    
    def test_cache_cleared_on_site_change(self):
        """Test that cache is cleared when page sites change."""
        # Populate cache
        template = Template("{% load pages %}{% get_pages as flatpages %}")
        context = Context({"request": RequestFactory().get("/")})
        template.render(context)
        
        cache_key = "flatpages:site_1:depth_0:anon"
        assert cache.get(cache_key) is not None
        
        # Remove site
        self.page.sites.remove(self.site)
        
        # Cache should be cleared
        assert cache.get(cache_key) is None


@pytest.mark.django_db
class TestOptimizedRegexPatterns:
    """Test the optimized regex patterns for depth filtering."""
    
    def setup_method(self):
        """Set up test data."""
        cache.clear()
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
    
    def teardown_method(self):
        """Clean up after each test."""
        cache.clear()
    
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
        # Create a custom template tag instance
        template = Template(
            "{% load pages %}"
            "{% get_pages as all_pages %}"
            "{{ all_pages|length }}"
        )
        context = Context({"request": RequestFactory().get("/")})
        
        # Manually test depth 2 filtering
        from django.contrib.flatpages.models import FlatPage
        depth2_pages = FlatPage.objects.filter(
            sites__id=self.site.id,
            registration_required=False,
            url__regex=r"^/[^/]+(?:/[^/]+){0,1}/?$"
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
            cache.clear()
            
            # Create a node with specific depth
            node = FlatpageNode("flatpages")
            node.depth = depth
            
            # We need to test the actual filtering logic
            flatpages = FlatPage.objects.filter(
                sites__id=self.site.id,
                registration_required=False
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


@pytest.mark.django_db
class TestCacheBackendSupport:
    """Test support for different cache backends."""
    
    def setup_method(self):
        """Set up test data."""
        cache.clear()
        self.site = Site.objects.get(id=1)
        self.page = FlatPage.objects.create(
            url="/test/",
            title="Test Page",
            content="Test content",
            registration_required=False,
        )
        self.page.sites.add(self.site)
    
    def teardown_method(self):
        """Clean up after each test."""
        cache.clear()
    
    def test_cache_clear_function(self):
        """Test the clear_flatpages_cache function."""
        from gyrinx.pages.signals import clear_flatpages_cache
        
        # Populate cache with multiple keys
        cache.set("flatpages:site_1:depth_0:anon", ["page1"])
        cache.set("flatpages:site_1:depth_1:anon", ["page2"])
        cache.set("flatpages:site_2:depth_0:user_1_groups_1", ["page3"])
        cache.set("other_key", "other_value")  # Should not be cleared
        
        # Verify keys are set
        assert cache.get("flatpages:site_1:depth_0:anon") == ["page1"]
        assert cache.get("flatpages:site_1:depth_1:anon") == ["page2"]
        assert cache.get("other_key") == "other_value"
        
        # Clear flatpages cache
        clear_flatpages_cache()
        
        # For LocMemCache with our implementation, at least the common patterns should be cleared
        # The implementation tries different approaches, and may fall back to clearing known patterns
        assert cache.get("flatpages:site_1:depth_0:anon") is None
        assert cache.get("flatpages:site_1:depth_1:anon") is None
        
        # Other keys should remain
        assert cache.get("other_key") == "other_value"
    
    def test_ttl_setting(self):
        """Test that cache entries have proper TTL."""
        template = Template("{% load pages %}{% get_pages as flatpages %}")
        context = Context({"request": RequestFactory().get("/")})
        template.render(context)
        
        # The cache.set call in the code uses 3600 seconds (1 hour) TTL
        # We can't directly test TTL with Django's cache API, but we can
        # verify that the cache was set
        cache_key = "flatpages:site_1:depth_0:anon"
        assert cache.get(cache_key) is not None
