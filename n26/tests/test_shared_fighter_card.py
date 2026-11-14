"""A fighter's shared card: a public page other websites may frame."""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from gyrinx.site.models import Availability, FeatureFlag
from n26.core.models import Gang
from n26.flags import SHARE_FIGHTER_CARD
from n26.tests.sandbox.actions import found_gang, hire

pytestmark = pytest.mark.django_db


@pytest.fixture
def fighter(gang_type, make_profile, default_pack):
    FeatureFlag.objects.create(
        slug=SHARE_FIGHTER_CARD,
        name=SHARE_FIGHTER_CARD,
        availability=Availability.EVERYONE,
    )
    gang = found_gang("Venom Sisters", gang_type, owner=User.objects.create_user("vex"))
    return hire(gang, make_profile("Escher Ganger"), "Yolanda", paid=55)


def card_page(client, fighter):
    return client.get(reverse("n26-shared-fighter-card", args=[fighter.pk]))


class TestTheSharedCard:
    def test_it_opens_without_signing_in_and_may_be_framed(self, client, fighter):
        response = card_page(client, fighter)

        assert response.status_code == 200
        assert "X-Frame-Options" not in response.headers
        assert response.headers["Content-Security-Policy"] == "frame-ancestors *"
        assert not response.cookies

    def test_it_shows_the_card_without_tabs_or_controls(self, client, fighter):
        page = card_page(client, fighter).text

        assert "Yolanda" in page
        assert "Venom Sisters" in page
        assert "Lore" not in page
        assert reverse("n26-edit-fighter", args=[fighter.pk]) not in page

    def test_the_owner_gets_the_same_card_as_anyone(self, client, fighter):
        client.force_login(fighter.membership.gang.owner)

        page = card_page(client, fighter).text

        assert reverse("n26-equip", args=[fighter.pk]) not in page

    def test_a_fighter_who_has_left_the_gang_is_gone(self, client, fighter):
        type(fighter.membership).objects.filter(pk=fighter.membership.pk).update(
            archived=True
        )

        assert card_page(client, fighter).status_code == 404

    def test_an_archived_gang_takes_its_fighters_with_it(self, client, fighter):
        Gang.objects.filter(pk=fighter.membership.gang_id).update(archived=True)

        assert card_page(client, fighter).status_code == 404

    def test_every_card_is_gone_while_the_flag_is_shut(self, client, fighter):
        FeatureFlag.objects.filter(slug=SHARE_FIGHTER_CARD).delete()

        assert card_page(client, fighter).status_code == 404

    def test_an_address_that_is_not_a_fighter_is_not_found(self, client, fighter):
        response = client.get(reverse("n26-shared-fighter-card", args=["nope"]))

        assert response.status_code == 404


def share_controls(client, fighter):
    page = client.get(reverse("n26-gang", args=[fighter.membership.gang_id])).text
    return page.count('data-react-name="share-card"')


class TestTheShareControl:
    def test_the_owner_gets_one_on_each_card(self, client, fighter):
        client.force_login(fighter.membership.gang.owner)

        assert share_controls(client, fighter) == 1

    def test_it_points_at_the_cards_page(self, client, fighter):
        client.force_login(fighter.membership.gang.owner)

        page = client.get(reverse("n26-gang", args=[fighter.membership.gang_id])).text

        assert reverse("n26-shared-fighter-card", args=[fighter.pk]) in page

    def test_nobody_else_gets_one(self, client, fighter):
        client.force_login(User.objects.create_user("reader"))

        assert share_controls(client, fighter) == 0

    def test_nobody_gets_one_while_the_flag_is_shut(self, client, fighter):
        FeatureFlag.objects.filter(slug=SHARE_FIGHTER_CARD).delete()
        client.force_login(fighter.membership.gang.owner)

        assert share_controls(client, fighter) == 0

    def test_the_fighters_own_page_has_one_too(self, client, fighter):
        client.force_login(fighter.membership.gang.owner)

        page = client.get(reverse("n26-edit-fighter", args=[fighter.pk])).text

        assert page.count('data-react-name="share-card"') == 1


@pytest.mark.parametrize("theme", ["light", "dark", "system"])
def test_shared_card_theme_and_branding(client, fighter, theme):
    response = client.get(
        reverse("n26-shared-fighter-card", args=[fighter.pk]), {"theme": theme}
    )
    assert response.status_code == 200
    assert f'data-shared-theme="{theme}"' in response.text
    assert "n26/gyrinx-logo.svg" in response.text
    assert response.text.index("data-shared-card") < response.text.index(
        "n26-shared-brand"
    )
    if theme in {"light", "dark"}:
        assert f'class="{theme}"' in response.text


def test_unknown_shared_theme_uses_system(client, fighter):
    response = client.get(
        reverse("n26-shared-fighter-card", args=[fighter.pk]),
        {"theme": "unrecognised-theme"},
    )
    assert 'data-shared-theme="system"' in response.text
    assert "unrecognised-theme" not in response.text
