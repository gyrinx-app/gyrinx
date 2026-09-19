"""The Share button on a help page remains a real link to the page."""

import pytest
from bs4 import BeautifulSoup
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

    share = BeautifulSoup(body, "html.parser").find("a", attrs={"aria-label": "Share"})
    assert share is not None
    assert share["href"] == flatpage.url
    assert "n26-site-nav" in share.find_parent("header")["class"]
    assert "Link copied." in body
