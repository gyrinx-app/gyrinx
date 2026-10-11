"""One public account destination, with edition-owned visibility."""

from unittest.mock import Mock
from urllib.parse import unquote

import pytest
from bs4 import BeautifulSoup
from django.apps import apps
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from gyrinx.accounts import public_profiles
from gyrinx.accounts.models import PatreonStatus, UserProfile
from gyrinx.accounts.public_profiles import ProfileSource
from gyrinx.editions import COOKIE_NAME

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("selected", ["staff", "scummer", "guilder"])
def test_the_profile_and_selector_draw_the_same_selected_badge(client, user, selected):
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    UserProfile.objects.update_or_create(
        user=user,
        defaults={
            "patreon_status": PatreonStatus.ACTIVE,
            "patreon_tier": "Guilder",
            "selected_badge": selected,
        },
    )
    client.force_login(user)
    fields = client.get(reverse("account-settings")).context["settings_form"]["fields"]
    field = next(field for field in fields if field["name"] == "selected_badge")
    selected_image = next(
        choice["imageUrl"] for choice in field["choices"] if choice["value"] == selected
    )
    assert selected_image.startswith("data:image/svg+xml;base64,")
    for edition in ("n23", "n26"):
        response = client.get(
            reverse("user-profile", args=[user.username]), {"tab": edition}
        )
        page = BeautifulSoup(response.content, "html.parser")
        header_image = page.find("h1").parent.find("img")
        assert header_image is not None
        assert header_image["src"] == selected_image


@pytest.mark.parametrize("edition", ["n23", "n26"])
def test_the_header_edition_defaults_the_profile_tab_without_changing_the_cookie(
    client, user, edition
):
    client.force_login(user)
    client.cookies[COOKIE_NAME] = edition
    response = client.get(reverse("user-profile", args=[user.username]))
    current = [tab for tab in response.context["tabs"] if tab["current"]]
    assert [tab["label"] for tab in current] == [edition.upper()]
    assert COOKIE_NAME not in response.cookies
    nav = BeautifulSoup(response.content, "html.parser").find(
        "span", {"aria-label": "Edition"}
    )
    assert (
        nav.find("a", {"aria-current": "true"}).get_text(strip=True) == edition.upper()
    )


@pytest.mark.parametrize("edition", ["n23", "n26"])
def test_tab_links_survive_reload_and_override_the_header_without_changing_it(
    client, user, edition
):
    client.force_login(user)
    other = "n26" if edition == "n23" else "n23"
    client.cookies[COOKIE_NAME] = other
    address = reverse("user-profile", args=[user.username]) + f"?tab={edition}"
    for _ in range(2):
        response = client.get(address)
        assert [tab["label"] for tab in response.context["tabs"] if tab["current"]] == [
            edition.upper()
        ]
        assert response.context["request"].edition == other
        assert COOKIE_NAME not in response.cookies
        links = BeautifulSoup(response.content, "html.parser").find(
            "nav", {"aria-label": "Gang edition"}
        )
        assert links.find("a", href=address, attrs={"aria-current": "page"})


def test_anonymous_and_invalid_tab_requests_use_the_default_edition(client, user):
    client.cookies[COOKIE_NAME] = "n26"
    response = client.get(
        reverse("user-profile", args=[user.username]), {"tab": "unknown"}
    )
    assert [tab["label"] for tab in response.context["tabs"] if tab["current"]] == [
        "N23"
    ]


def test_only_the_selected_edition_listing_is_read(client, user, monkeypatch):
    n23_reader, n26_reader = Mock(return_value=()), Mock(return_value=())
    monkeypatch.setitem(
        public_profiles._sources, "n23", ProfileSource("n23", n23_reader)
    )
    monkeypatch.setitem(
        public_profiles._sources, "n26", ProfileSource("n26", n26_reader)
    )
    response = client.get(reverse("user-profile", args=[user.username]), {"tab": "n26"})
    assert response.status_code == 200
    n26_reader.assert_called_once()
    n23_reader.assert_not_called()


@pytest.mark.parametrize("viewer", ["anonymous", "owner", "stranger"])
def test_n23_visibility_covers_gangs_campaigns_packs_and_archives(
    client, user, make_user, make_list, make_campaign, viewer
):
    List = apps.get_model("core", "List")
    Pack = apps.get_model("core", "CustomContentPack")
    visible, private, archived = [], [], []
    for public in (True, False):
        destination = visible if public else private
        campaign = make_campaign(f"League {public}", public=public)
        destination.append(campaign.name)
        for status in (List.LIST_BUILDING, List.CAMPAIGN_MODE):
            gang = make_list(
                f"Gang {public} {status}",
                public=public,
                status=status,
                campaign=campaign if status == List.CAMPAIGN_MODE else None,
            )
            destination.append(gang.name)
        pack = Pack.objects.create(name=f"Pack {public}", owner=user, listed=public)
        destination.append(pack.name)
    archived.append(make_list("Archived gang", archived=True).name)
    archived.append(make_campaign("Archived league", archived=True).name)
    archived.append(
        Pack.objects.create(
            name="Archived pack", owner=user, listed=True, archived=True
        ).name
    )
    if viewer == "owner":
        client.force_login(user)
    elif viewer == "stranger":
        client.force_login(make_user("stranger", "password"))
    response = client.get(reverse("user-profile", args=[user.username]), {"tab": "n23"})
    assert response.status_code == 200
    html = response.content.decode()
    for name in visible:
        assert name in html
    for name in private:
        assert (name in html) == (viewer == "owner")
    for name in archived:
        assert name not in html


def test_a_public_gang_does_not_disclose_its_private_campaign(
    client, user, make_list, make_campaign, make_user
):
    campaign = make_campaign("Private league", public=False)
    gang = make_list(
        "Public players",
        status=apps.get_model("core", "List").CAMPAIGN_MODE,
        campaign=campaign,
    )
    url = reverse("user-profile", args=[user.username])
    public = client.get(url).content.decode()
    assert gang.name in public
    assert campaign.name not in public
    assert reverse("core:campaign", args=[campaign.pk]) not in public
    participant = make_user("participant", "password")
    client.force_login(participant)
    assert campaign.name not in client.get(url).content.decode()
    playing = make_list("Participant gang", owner=participant)
    campaign.lists.add(playing)
    visible = client.get(url).content.decode()
    assert campaign.name in visible
    assert reverse("core:campaign", args=[campaign.pk]) in visible
    client.force_login(user)
    assert campaign.name in client.get(url).content.decode()


@pytest.mark.parametrize(
    "username", ["12345", "Upper.Player+tag@example.com", "Joueur-é", "@player"]
)
def test_canonical_links_retain_the_complete_username(client, make_user, username):
    person = make_user(username, "password")
    canonical = reverse("user-profile", args=[username])
    assert unquote(canonical) == f"/user/@{username}/"
    assert reverse("core:user", args=[username]) == canonical
    assert client.get(canonical).context["person"] == person


def test_legacy_leading_at_usernames_do_not_collide_with_canonical_profiles(
    client, make_user
):
    plain = make_user("player", "password")
    prefixed = make_user("@player", "password")
    response = client.get("/user/@player")
    assert response.status_code == 302
    assert response.url == reverse("user-profile", args=[prefixed.username])
    assert client.get(response.url).context["person"] == prefixed
    canonical = reverse("user-profile", args=[plain.username])
    assert canonical == "/user/@player/"
    assert client.get(canonical).context["person"] == plain


def test_legacy_n23_ids_do_not_target_an_account_with_that_numeric_username(
    client, user, make_user
):
    numeric = make_user(str(user.pk), "password")
    response = client.get(f"/user/{user.pk}")
    assert response.status_code == 302
    assert response.url == reverse("user-profile", args=[user.username])
    assert (
        client.get(reverse("user-profile", args=[numeric.username])).context["person"]
        == numeric
    )


@pytest.mark.parametrize("tab", ["n23", "n26"])
def test_old_username_addresses_preserve_explicit_tabs(client, user, tab):
    expected = reverse("user-profile", args=[user.username]) + f"?tab={tab}"
    for url in (
        f"/user/{user.username}",
        reverse("n26-user-profile", args=[user.username]),
        f"/n26/users/{user.username}/",
    ):
        response = client.get(url, {"tab": tab})
        assert response.status_code == 302
        assert response.url == expected
        assert client.get(response.url).status_code == 200


@pytest.mark.parametrize("viewer", ["owner", "participant"])
def test_n23_repeated_records_do_not_add_queries(
    client, user, make_list, make_campaign, make_user, viewer
):
    Pack = apps.get_model("core", "CustomContentPack")
    reader = user if viewer == "owner" else make_user("participant", "password")
    client.force_login(reader)
    url = reverse("user-profile", args=[user.username]) + "?tab=n23"

    def count():
        client.get(url)
        with CaptureQueriesContext(connection) as queries:
            assert client.get(url).status_code == 200
        return len(queries)

    def add(number):
        campaign = make_campaign(f"League {number}")
        make_list(f"Building gang {number}")
        make_list(
            f"Playing gang {number}",
            status=apps.get_model("core", "List").CAMPAIGN_MODE,
            campaign=campaign,
        )
        campaign.lists.add(make_list(f"Reader gang {number}", owner=reader))
        Pack.objects.create(name=f"Pack {number}", owner=user, listed=True)

    add(0)
    small = count()
    for number in range(1, 9):
        add(number)
    assert count() == small
