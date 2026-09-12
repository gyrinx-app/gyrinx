"""The Share button on a help page: a link to the page itself, with
the hook index.js takes over."""

import re

import pytest
from django.contrib.flatpages.models import FlatPage


@pytest.fixture
def flatpage(site):
    page = FlatPage.objects.create(
        url="/help/sharing/",
        title="Sharing",
        content="<p>How to share.</p>",
    )
    page.sites.add(site)
    return page


@pytest.mark.django_db
def test_help_page_share_is_a_link_to_the_page(client, flatpage):
    body = client.get(flatpage.url).content.decode()

    match = re.search(
        rf'<a\s[^>]*data-share-url="{re.escape(flatpage.url)}"[^>]*>', body
    )
    assert match is not None
    assert f'href="{flatpage.url}"' in match.group(0)
    assert "Link copied." in body
