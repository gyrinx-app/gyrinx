"""The app menu honours the platform campaign feature gate."""

import json

import pytest
from bs4 import BeautifulSoup
from django.contrib.auth.models import User
from django.urls import reverse

from gyrinx.site.models import Availability, FeatureFlag
from n26.flags import CAMPAIGNS

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "availability,offered", [(Availability.EVERYONE, True), (Availability.OFF, False)]
)
def test_the_home_menu_offers_campaigns_only_when_available(
    client, availability, offered
):
    FeatureFlag.objects.create(
        slug=CAMPAIGNS, name="Campaigns", availability=availability
    )
    client.force_login(User.objects.create_user("menu-reviewer"))
    response = client.get(reverse("n26-dashboard"))
    assert response.status_code == 200
    soup = BeautifulSoup(response.content, "html.parser")
    props = [
        json.loads(node.string)
        for node in soup.select('script[type="application/json"]')
        if node.string
    ]
    places = next(
        item for item in props if item.get("menuLabel") == "Go to another page"
    )
    hrefs = {item["label"]: item["href"] for item in places["items"]}
    assert hrefs["Home"] == reverse("n26-dashboard")
    assert hrefs["Gangs"] == reverse("n26-gangs")
    assert ("Campaigns" in hrefs) is offered
    if offered:
        assert hrefs["Campaigns"] == reverse("n26-campaigns")
    else:
        assert client.get(reverse("n26-campaigns")).status_code == 404
