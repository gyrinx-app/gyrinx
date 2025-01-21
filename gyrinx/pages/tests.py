import pytest
from django.contrib.sites.models import Site

from gyrinx.pages.models import WaitingListEntry, WaitingListSkill
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
