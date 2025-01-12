import pytest
from django.contrib.sites.models import Site

from gyrinx.pages.templatetags.pages import pages_path_segment


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
