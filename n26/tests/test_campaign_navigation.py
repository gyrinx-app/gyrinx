"""The app menu offers campaigns."""

import json

import pytest
from bs4 import BeautifulSoup
from django.contrib.auth.models import User
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_the_home_menu_offers_campaigns(client):
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
    assert hrefs["Campaigns"] == reverse("n26-campaigns")
