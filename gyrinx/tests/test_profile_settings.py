"""Public profile presentation and owner-only edits."""

import json
from datetime import timedelta
from io import BytesIO

import pytest
from bs4 import BeautifulSoup
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from gyrinx.accounts.models import UserProfile
from gyrinx.accounts.profile_settings import ProfileSettingsForm
from gyrinx.accounts.validators import social_link_href


def island(response):
    page = BeautifulSoup(response.content, "html.parser")
    host = page.select_one('[data-react-name="profile-settings"]')
    return json.loads(page.find(id=host["data-react-props"]).string) if host else None


def edit_data(client, user):
    client.force_login(user)
    data = island(client.get(reverse("user-profile", args=[user.username])))
    return {
        "snapshot": data["snapshot"],
        "colour": "",
        **{f"link_{i}": "" for i in range(5)},
    }


@pytest.mark.parametrize(
    "value,href",
    [
        (
            "https://example.com/@player?tab=gangs#top",
            "https://example.com/@player?tab=gangs#top",
        ),
        ("http://example.org/", "http://example.org/"),
        ("player@example.com", "mailto:player@example.com"),
        ("mailto:player@example.com", "mailto:player@example.com"),
    ],
)
def test_links_keep_the_supplied_text_and_use_a_valid_destination(value, href):
    assert social_link_href(value) == href


@pytest.mark.parametrize(
    "value",
    [
        "javascript:alert(1)",
        "data:text/html,bad",
        "//example.com",
        "/accounts/",
        "ftp://example.com",
        "not a link",
        "https://example.com/\n",
        "mailto:player@example.com?bcc=other@example.com",
        "https://example.com/ a",
        "player@example.com\r\nBcc:other@example.com",
    ],
)
def test_the_form_rejects_unsafe_or_incomplete_destinations(value):
    form = ProfileSettingsForm({"snapshot": "unused", "link_0": value})
    assert not form.is_valid()
    assert "link_0" in form.errors


def test_the_form_rejects_a_fourth_link_and_unrecognised_colours():
    form = ProfileSettingsForm(
        {
            "snapshot": "unused",
            "link_3": "https://example.org",
            "colour": "red;display:none",
        }
    )
    assert not form.is_valid()
    assert "colour" in form.errors
    assert "__all__" in form.errors


@pytest.mark.django_db
def test_only_the_owner_gets_settings_props(client, user, make_user):
    url = reverse("user-profile", args=[user.username])
    assert island(client.get(url)) is None
    staff = make_user("other-staff", "password")
    staff.is_staff = True
    staff.save()
    client.force_login(staff)
    assert island(client.get(url)) is None
    client.force_login(user)
    assert island(client.get(url))["links"] == [""] * 3


@pytest.mark.django_db
def test_the_owner_can_save_three_links_social_accounts_location_and_colour(
    client, user
):
    data = edit_data(client, user)
    links = [
        "https://example.com/one",
        "player@example.com",
        "mailto:other@example.com",
    ]
    data.update(
        {f"link_{i}": link for i, link in enumerate(links)},
        colour="violet",
        instagram="@ash_road",
        discord="@ash.road",
        discord_user_id="123456789012345678",
        location="Nottingham, UK",
    )
    url = reverse("profile-settings", args=[user.username])
    response = client.post(url + "?tab=n26&category=campaigns&page=2", data)
    assert response.status_code == 302
    assert response.url.endswith("?tab=n26&category=campaigns&page=2")
    profile = UserProfile.objects.get(user=user)
    assert profile.social_links == links
    assert profile.colour == "violet"
    assert profile.instagram_handle == "ash_road"
    assert profile.discord_handle == "ash.road"
    assert profile.discord_user_id == "123456789012345678"
    assert profile.location == "Nottingham, UK"
    client.logout()
    page = BeautifulSoup(
        client.get(reverse("user-profile", args=[user.username])).content, "html.parser"
    )
    shown = page.select('[aria-label="Social links"] a')
    assert [a.get_text(strip=True) for a in shown] == links + [
        "Instagram: @ash_road",
        "Discord: @ash.road",
    ]
    assert shown[-2]["href"] == "https://www.instagram.com/ash_road/"
    assert shown[-1]["href"] == "https://discord.com/users/123456789012345678"
    assert (
        page.select_one("[data-profile-location]").get_text(strip=True)
        == "Nottingham, UK"
    )
    separators = page.select('[aria-label="Social links"] [aria-hidden="true"]')
    assert len(separators) == 4 and all(item.get_text() == "·" for item in separators)
    assert shown[1]["href"] == "mailto:player@example.com"
    assert "--color-violet-400" in str(page)


@pytest.mark.django_db
def test_blank_links_are_omitted_and_invalid_posts_keep_the_draft(client, user):
    data = edit_data(client, user)
    data.update(
        link_0="javascript:bad", link_2="https://example.org/keep", colour="green"
    )
    response = client.post(reverse("profile-settings", args=[user.username]), data)
    assert response.status_code == 400
    props = island(response)
    assert props["open"] and props["errors"]["link_0"]
    assert props["links"][2] == "https://example.org/keep"
    assert not UserProfile.objects.filter(user=user, colour="green").exists()
    data["link_0"] = ""
    assert (
        client.post(reverse("profile-settings", args=[user.username]), data).status_code
        == 302
    )
    assert UserProfile.objects.get(user=user).social_links == [
        "https://example.org/keep"
    ]


@pytest.mark.django_db
def test_anonymous_and_other_accounts_cannot_write_settings(client, user, make_user):
    data = edit_data(client, user)
    url = reverse("profile-settings", args=[user.username])
    client.logout()
    assert client.post(url, data).status_code == 403
    client.force_login(make_user("other", "password"))
    assert client.post(url, data).status_code == 403
    assert not UserProfile.objects.filter(user=user, colour="red").exists()


@pytest.mark.django_db
def test_stale_and_forged_snapshots_cannot_overwrite_newer_settings(client, user):
    data = edit_data(client, user)
    url = reverse("profile-settings", args=[user.username])
    assert client.post(url, {**data, "colour": "red"}).status_code == 302
    stale = client.post(url, {**data, "colour": "blue"})
    assert stale.status_code == 409 and island(stale)["conflict"]
    assert UserProfile.objects.get(user=user).colour == "red"
    assert client.post(url, {**data, "colour": "red"}).status_code == 302
    assert client.post(url, {**data, "snapshot": "forged"}).status_code == 409


@pytest.mark.django_db
def test_profile_pictures_use_the_shared_square_crop_and_can_be_removed(
    client, user, settings, tmp_path
):
    settings.MEDIA_ROOT = tmp_path
    data = edit_data(client, user)
    raw = BytesIO()
    Image.new("RGB", (2200, 1800), "teal").save(raw, format="PNG")
    data["picture"] = SimpleUploadedFile(
        "portrait.png", raw.getvalue(), content_type="image/png"
    )
    url = reverse("profile-settings", args=[user.username])
    assert client.post(url, data).status_code == 302
    profile = UserProfile.objects.get(user=user)
    with profile.picture.open() as upload, Image.open(upload) as image:
        assert image.size == (1600, 1600)
        assert image.format == "JPEG"
    filename = profile.picture.path
    data = edit_data(client, user)
    assert client.post(url, {**data, "remove_picture": "on"}).status_code == 302
    assert not UserProfile.objects.get(user=user).picture
    assert __import__("pathlib").Path(filename).exists()


@pytest.mark.django_db
def test_corrupt_pictures_are_rejected(client, user):
    data = edit_data(client, user)
    data["picture"] = SimpleUploadedFile(
        "bad.jpg", b"not an image", content_type="image/jpeg"
    )
    response = client.post(reverse("profile-settings", args=[user.username]), data)
    assert response.status_code == 400
    assert island(response)["errors"]["picture"]


@pytest.mark.django_db
def test_categories_have_counts_and_only_seven_entries_are_rendered(
    client, user, make_list, make_campaign
):
    for i in range(20):
        make_list(f"Public {i:02}")
        make_campaign(f"Campaign {i:02}")
    client.force_login(user)
    url = reverse("user-profile", args=[user.username])
    first = client.get(url, {"tab": "n23", "category": "lists"})
    assert first.context["page"].paginator.count == 20
    assert len(first.context["page"].object_list) == 7
    soup = BeautifulSoup(first.content, "html.parser")
    assert len(soup.select("[data-profile-entries] > li")) == 7
    assert "Campaign 00" not in soup.select_one("[data-profile-entries]").get_text()
    categories = soup.select_one('[aria-label="Profile categories"]').get_text(
        " ", strip=True
    )
    assert "Lists 20" in categories and "Campaigns 20" in categories
    last = client.get(url, {"tab": "n23", "category": "lists", "page": "3"})
    assert len(last.context["page"].object_list) == 6
    assert last.context["page"].number == 3
    assert (
        client.get(url, {"page": "bad", "category": "unknown"}).context["page"].number
        == 1
    )
    assert client.get(url, {"page": "9999"}).context["page"].number == 3
    campaigns = client.get(url, {"category": "campaigns"})
    assert campaigns.context["active_section"].title == "Campaigns"
    assert campaigns.context["page"].object_list[0].name == "Campaign 00"


@pytest.mark.django_db
def test_gang_sorting_uses_name_modification_and_wealth(client, user, make_list):
    from n23.core.models import List

    older = make_list("Zulu")
    newer = make_list("Alpha")
    List.objects.filter(pk=older.pk).update(
        modified=timezone.now() - timedelta(days=2), credits_current=900
    )
    List.objects.filter(pk=newer.pk).update(credits_current=100)
    url = reverse("user-profile", args=[user.username])
    for sort, first in (("name", "Alpha"), ("modified", "Alpha"), ("wealth", "Zulu")):
        response = client.get(url, {"sort": sort})
        assert response.context["page"].object_list[0].name == first
        assert all(
            f"sort={sort}" in item["href"] for item in response.context["category_tabs"]
        )


@pytest.mark.django_db
def test_settings_posts_require_csrf(client, user, caplog):
    from django.test import Client

    data = edit_data(client, user)
    strict = Client(enforce_csrf_checks=True)
    strict.force_login(user)
    response = strict.post(
        reverse("profile-settings", args=[user.username]), {**data, "colour": "red"}
    )
    assert response.status_code == 302 and response.url == "/"
    assert "CSRF cookie not set" in caplog.text
    assert not UserProfile.objects.filter(user=user, colour="red").exists()


@pytest.mark.django_db
def test_gang_entries_use_sanitised_house_artwork_colour_and_campaign(
    client, user, make_list, make_campaign, content_house, settings, tmp_path
):
    from django.core.files.base import ContentFile

    from n23.core.models import List

    settings.MEDIA_ROOT = tmp_path
    content_house.icon.save(
        "test.svg",
        ContentFile(
            b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" onload="bad()"><path d="M2 2L8 8"/><script>bad()</script></svg>'
        ),
        save=True,
    )
    campaign = make_campaign("Visible campaign", public=True)
    gang = make_list(
        "Colourful gang",
        status=List.CAMPAIGN_MODE,
        campaign=campaign,
        theme_color="#14b8a6",
    )
    response = client.get(
        reverse("user-profile", args=[user.username]), {"category": "campaign-gangs"}
    )
    soup = BeautifulSoup(response.content, "html.parser")
    entry = soup.select_one("[data-profile-entries] > li")
    assert entry.find("path", {"d": "M2 2L8 8"})
    assert not entry.find("script")
    assert "onload" not in str(entry)
    assert "#14b8a6" in str(entry)
    assert entry.find("a", {"href": reverse("core:list", args=[gang.pk])})
    assert entry.find("a", {"href": reverse("core:campaign", args=[campaign.pk])})


@pytest.mark.django_db
def test_a_missing_snapshot_offers_reload_instead_of_repeated_invalid_saves(
    client, user
):
    data = edit_data(client, user)
    data.pop("snapshot")
    response = client.post(reverse("profile-settings", args=[user.username]), data)
    assert response.status_code == 409
    assert island(response)["conflict"]
    assert "Reload your profile before saving." in island(response)["errors"]["__all__"]


@pytest.mark.django_db
def test_large_collections_keep_pagination_bounded(client, user, monkeypatch):
    from gyrinx.accounts import public_profiles
    from gyrinx.accounts.public_profiles import (
        ProfileEntry,
        ProfileSection,
        ProfileSource,
    )

    entries = tuple(
        ProfileEntry(f"Gang {i:03}", f"/gang/{i}/", is_gang=True) for i in range(300)
    )
    monkeypatch.setitem(
        public_profiles._sources,
        "n23",
        ProfileSource(
            "n23",
            lambda person, request: (ProfileSection("Gangs", entries, "No gangs."),),
        ),
    )
    response = client.get(
        reverse("user-profile", args=[user.username]), {"tab": "n23", "page": "20"}
    )
    assert len(response.context["page"].object_list) == 7
    assert len(response.context["pagination"]) <= 7
    assert any(item.get("elided") for item in response.context["pagination"])


@pytest.mark.django_db
def test_legacy_links_are_preserved_until_the_owner_removes_them(client, user):
    links = [f"https://example.com/{i}" for i in range(5)]
    UserProfile.objects.update_or_create(user=user, defaults={"social_links": links})
    data = edit_data(client, user)
    data.update({f"link_{i}": value for i, value in enumerate(links[:3])})
    url = reverse("profile-settings", args=[user.username])
    assert client.post(url, data).status_code == 302
    assert UserProfile.objects.get(user=user).social_links == links
    data = edit_data(client, user)
    data.update(
        {f"link_{i}": value for i, value in enumerate(links[:3])},
        remove_extra_links="on",
    )
    assert client.post(url, data).status_code == 302
    assert UserProfile.objects.get(user=user).social_links == links[:3]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "field,value",
    [
        ("instagram", "https://example.com"),
        ("instagram", "bad handle"),
        ("instagram", "@"),
        ("discord", "bad..handle"),
        ("discord", "Bad Handle"),
        ("discord_user_id", "a_handle"),
        ("discord_user_id", "00000000000000000"),
        ("discord_user_id", "99999999999999999999"),
        ("location", "a" * 121),
        ("location", "London\nUK"),
    ],
)
def test_invalid_social_accounts_and_location_keep_the_draft(
    client, user, field, value
):
    data = edit_data(client, user)
    data[field] = value
    response = client.post(reverse("profile-settings", args=[user.username]), data)
    assert response.status_code == 400
    assert island(response)["errors"][field]
    assert not UserProfile.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_discord_handle_without_id_is_text_and_blank_location_has_a_fallback(
    client, user
):
    data = edit_data(client, user)
    data["discord"] = "@ash_road"
    assert (
        client.post(reverse("profile-settings", args=[user.username]), data).status_code
        == 302
    )
    client.logout()
    response = client.get(reverse("user-profile", args=[user.username]))
    page = BeautifulSoup(response.content, "html.parser")
    social = page.select_one('[aria-label="Social links"]')
    assert social.get_text(strip=True) == "Discord: @ash_road"
    assert not social.select("a")
    assert (
        page.select_one("[data-profile-location]").get_text(strip=True)
        == "None specified"
    )


@pytest.mark.django_db
def test_location_and_social_accounts_participate_in_stale_edit_detection(client, user):
    data = edit_data(client, user)
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.location = "New location"
    profile.save()
    data["instagram"] = "old_draft"
    response = client.post(reverse("profile-settings", args=[user.username]), data)
    assert response.status_code == 409
    profile.refresh_from_db()
    assert profile.location == "New location" and not profile.instagram_handle
