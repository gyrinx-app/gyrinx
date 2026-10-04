"""Campaign editor controls round-trip supported content through safe rendering."""

import pytest
from bs4 import BeautifulSoup
from django.contrib.auth.models import User
from django.urls import reverse

from gyrinx.site.models import Availability, FeatureFlag
from n26.core.forms import CampaignForm
from n26.core.models import CampaignEvent
from n26.flags import CAMPAIGNS
from n26.library.authoring import create_campaign_type
from n26.tests.sandbox.actions import found_campaign

pytestmark = pytest.mark.django_db


@pytest.fixture
def campaign(client, default_pack):
    FeatureFlag.objects.create(
        slug=CAMPAIGNS, name="Campaigns", availability=Availability.EVERYONE
    )
    owner = User.objects.create_user("summary-arbitrator")
    campaign_type = create_campaign_type("Territory campaign")
    campaign = found_campaign("Dust Falls", campaign_type, owner=owner)
    client.force_login(owner)
    return campaign


CONTENT = (
    '<p><a href="https://example.com/campaign-pack">Campaign pack</a></p>'
    '<p><img src="https://example.com/map.png" alt="Campaign map" width="1200"></p>'
    "<table><tbody><tr><th>Cycle</th><th>Scenario</th></tr>"
    "<tr><td>1</td><td>Border dispute</td></tr></tbody></table>"
)


def test_campaign_controls_include_link_image_and_table_without_global_changes():
    from n26.core.widgets import RichText

    configured = CampaignForm().fields["summary"].widget.mce_attrs
    assert set(configured["plugins"].split()) >= {"link", "image", "table"}
    assert set(configured["toolbar"].split()) >= {"link", "image", "table"}
    assert configured["paste_data_images"] is True
    assert configured["automatic_uploads"] is True
    assert configured["setup"] == "n26CampaignImages"
    assert "/tinymce/upload/" in configured["images_upload_handler"]
    assert configured["menubar"] is False
    assert not RichText().mce_attrs.get("toolbar")


def test_supported_content_survives_save_edit_and_overview(client, campaign):
    edit = reverse("n26-edit-campaign", args=[campaign.pk])
    response = client.post(
        edit, {"name": campaign.name, "budget": "", "summary": CONTENT}
    )
    assert response.status_code == 302
    campaign.refresh_from_db()
    assert campaign.summary == CONTENT
    assert client.get(edit).context["form"].initial["summary"] == CONTENT
    overview = client.get(reverse("n26-campaign", args=[campaign.pk]))
    soup = BeautifulSoup(overview.content, "html.parser")
    assert soup.find("a", href="https://example.com/campaign-pack")
    assert soup.find("img", src="https://example.com/map.png")["alt"] == "Campaign map"
    assert soup.find("th", string="Cycle")
    assert soup.find("td", string="Border dispute")


@pytest.mark.parametrize(
    "source", ["data:image/png;base64,AAAA", "blob:https://example.com/image"]
)
def test_unsavable_pasted_images_show_an_error_and_preserve_the_previous_summary(
    client, campaign, source
):
    response = client.post(
        reverse("n26-edit-campaign", args=[campaign.pk]),
        {
            "name": campaign.name,
            "budget": "",
            "summary": f'<p><img src="{source}"></p>',
        },
    )
    assert response.status_code == 200
    assert (
        "Finish uploading each image before saving, or remove it."
        in response.content.decode()
    )
    campaign.refresh_from_db()
    assert campaign.summary == ""
    assert list(campaign.events.values_list("kind", flat=True)) == [
        CampaignEvent.Kind.CREATED
    ]


def test_overview_keeps_sanitisation_for_images_and_links(client, campaign):
    content = (
        CONTENT
        + '<img src="javascript:alert(1)" onerror="alert(1)">'
        + '<a href="javascript:alert(1)">Unsafe link</a><script>alert(1)</script>'
    )
    client.post(
        reverse("n26-edit-campaign", args=[campaign.pk]),
        {"name": campaign.name, "budget": "", "summary": content},
    )
    response = client.get(reverse("n26-campaign", args=[campaign.pk]))
    soup = BeautifulSoup(response.content, "html.parser")
    assert soup.find("a", href="https://example.com/campaign-pack")
    assert soup.find("a", string="Unsafe link").get("href") is None
    assert not soup.select("img[onerror]")
    assert not soup.select('img[src^="javascript:"]')
    assert not any(tag.get_text() == "alert(1)" for tag in soup.find_all("script"))


def test_only_the_arbitrator_can_change_the_summary(client, campaign):
    other = User.objects.create_user("summary-reader")
    client.force_login(other)
    response = client.post(
        reverse("n26-edit-campaign", args=[campaign.pk]),
        {"name": campaign.name, "budget": "", "summary": CONTENT},
    )
    assert response.status_code in {403, 404}
    campaign.refresh_from_db()
    assert campaign.summary == ""


def test_uploaded_image_url_survives_summary_save_edit_and_render(
    client, campaign, settings
):
    import base64

    from django.core.files.uploadedfile import SimpleUploadedFile

    settings.STORAGES = {
        **settings.STORAGES,
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    }
    image = SimpleUploadedFile(
        "summary.png",
        base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLbtAAAAABJRU5ErkJggg=="
        ),
        content_type="image/png",
    )
    response = client.post("/tinymce/upload/", {"file": image})
    assert response.status_code == 200
    location = response.json()["location"]
    assert location.startswith("/media/")
    content = f'<p>Cycle one</p><p><img src="{location}" alt="Campaign map"></p>'
    edit = reverse("n26-edit-campaign", args=[campaign.pk])
    assert (
        client.post(
            edit, {"name": campaign.name, "budget": "", "summary": content}
        ).status_code
        == 302
    )
    campaign.refresh_from_db()
    assert campaign.summary == content
    assert client.get(edit).context["form"].initial["summary"] == content
    assert (
        location
        in client.get(reverse("n26-campaign", args=[campaign.pk])).content.decode()
    )


def test_compact_description_keeps_full_rich_text_in_disclosure_and_popover(
    client, campaign
):
    client.post(
        reverse("n26-edit-campaign", args=[campaign.pk]),
        {"name": campaign.name, "budget": "1000", "summary": CONTENT},
    )
    response = client.get(reverse("n26-campaign", args=[campaign.pk]))
    soup = BeautifulSoup(response.content, "html.parser")
    overview = soup.find(id="campaign-overview")
    assert overview.find("dt", string="Type")
    assert overview.find("dt", string="Arbitrator")
    assert overview.find("dt", string="Gang budget")
    popover = overview.find(attrs={"popover": "auto"})
    assert overview.find("button", attrs={"popovertarget": popover["id"]})
    disclosure = overview.find("details")
    assert disclosure.find("summary")
    assert not disclosure.has_attr("open")
    for full in [disclosure, popover]:
        assert full.find("a", href="https://example.com/campaign-pack")
        assert full.find("img", src="https://example.com/map.png")
        assert full.find("td", string="Border dispute")


def test_empty_description_does_not_offer_an_empty_popover(client, campaign):
    response = client.get(reverse("n26-campaign", args=[campaign.pk]))
    overview = BeautifulSoup(response.content, "html.parser").find(
        id="campaign-overview"
    )
    assert "No description yet." in overview.get_text()
    assert not overview.find("details")
    assert not overview.find(attrs={"popover": True})
