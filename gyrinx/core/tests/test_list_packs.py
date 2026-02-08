"""Tests for list pack subscription functionality."""

import pytest
from django.urls import reverse

from gyrinx.content.models import ContentFighter, ContentRule
from gyrinx.core.models.list import List
from gyrinx.core.models.pack import CustomContentPack, CustomContentPackItem
from gyrinx.models import FighterCategoryChoices


@pytest.fixture
def pack_fighter(pack, content_house):
    """A fighter in a pack."""
    fighter = ContentFighter.objects.create(
        type="Pack Fighter",
        category=FighterCategoryChoices.GANGER,
        house=content_house,
        base_cost=50,
    )
    from django.contrib.contenttypes.models import ContentType

    ct = ContentType.objects.get_for_model(ContentFighter)
    CustomContentPackItem.objects.create(
        pack=pack,
        content_type=ct,
        object_id=fighter.pk,
        owner=pack.owner,
    )
    return fighter


@pytest.fixture
def pack_rule(pack, cc_user):
    """A rule in a pack."""
    rule = ContentRule.objects.create(
        name="Pack Rule",
        description="A custom rule from a pack",
    )
    from django.contrib.contenttypes.models import ContentType

    ct = ContentType.objects.get_for_model(ContentRule)
    CustomContentPackItem.objects.create(
        pack=pack,
        content_type=ct,
        object_id=rule.pk,
        owner=cc_user,
    )
    return rule


@pytest.mark.django_db
class TestListPacksModel:
    """Test the List.packs M2M field."""

    def test_list_has_packs_field(self, make_list):
        lst = make_list("Test List")
        assert hasattr(lst, "packs")
        assert lst.packs.count() == 0

    def test_subscribe_pack(self, make_list, pack):
        lst = make_list("Test List")
        lst.packs.add(pack)
        assert pack in lst.packs.all()
        assert lst in pack.subscribed_lists.all()

    def test_unsubscribe_pack(self, make_list, pack):
        lst = make_list("Test List")
        lst.packs.add(pack)
        lst.packs.remove(pack)
        assert pack not in lst.packs.all()

    def test_multiple_packs(self, make_list, pack, cc_user):
        lst = make_list("Test List")
        pack2 = CustomContentPack.objects.create(
            name="Pack 2", listed=True, owner=cc_user
        )
        lst.packs.add(pack, pack2)
        assert lst.packs.count() == 2

    def test_clone_copies_packs(self, make_list, pack):
        lst = make_list("Test List")
        lst.packs.add(pack)
        clone = lst.clone(name="Cloned List")
        assert pack in clone.packs.all()


@pytest.mark.django_db
class TestPackSubscriptionViews:
    """Test the subscribe/unsubscribe views."""

    def test_subscribe_from_pack_detail(self, client, cc_user, pack, make_list):
        client.force_login(cc_user)
        lst = make_list("Test List")
        url = reverse("core:pack-subscribe", args=(pack.id,))
        response = client.post(url, {"list_id": str(lst.id)})
        assert response.status_code == 302
        lst.refresh_from_db()
        assert pack in lst.packs.all()

    def test_unsubscribe_from_pack_detail(self, client, cc_user, pack, make_list):
        client.force_login(cc_user)
        lst = make_list("Test List")
        lst.packs.add(pack)
        url = reverse("core:pack-unsubscribe", args=(pack.id,))
        response = client.post(url, {"list_id": str(lst.id)})
        assert response.status_code == 302
        lst.refresh_from_db()
        assert pack not in lst.packs.all()

    def test_subscribe_requires_custom_content_group(
        self, client, make_user, pack, content_house
    ):
        """Users not in Custom Content group get 404."""
        other_user = make_user("otheruser", "password")
        client.force_login(other_user)
        lst = List.objects.create(
            name="Other List", content_house=content_house, owner=other_user
        )
        url = reverse("core:pack-subscribe", args=(pack.id,))
        response = client.post(url, {"list_id": str(lst.id)})
        assert response.status_code == 404

    def test_subscribe_requires_post(self, client, cc_user, pack):
        client.force_login(cc_user)
        url = reverse("core:pack-subscribe", args=(pack.id,))
        response = client.get(url)
        assert response.status_code == 404

    def test_unsubscribe_returns_to_list(self, client, cc_user, pack, make_list):
        client.force_login(cc_user)
        lst = make_list("Test List")
        lst.packs.add(pack)
        url = reverse("core:pack-unsubscribe", args=(pack.id,))
        response = client.post(url, {"list_id": str(lst.id), "return_url": "list"})
        assert response.status_code == 302
        assert f"/list/{lst.id}/packs" in response.url


@pytest.mark.django_db
class TestListPacksManageView:
    """Test the list packs management view."""

    def test_manage_packs_page(self, client, cc_user, make_list):
        client.force_login(cc_user)
        lst = make_list("Test List")
        url = reverse("core:list-packs", args=(lst.id,))
        response = client.get(url)
        assert response.status_code == 200
        assert b"Content Packs" in response.content

    def test_manage_packs_shows_subscribed(self, client, cc_user, make_list, pack):
        client.force_login(cc_user)
        lst = make_list("Test List")
        lst.packs.add(pack)
        url = reverse("core:list-packs", args=(lst.id,))
        response = client.get(url)
        assert response.status_code == 200
        assert pack.name.encode() in response.content

    def test_manage_packs_add(self, client, cc_user, make_list, pack):
        client.force_login(cc_user)
        lst = make_list("Test List")
        url = reverse("core:list-packs", args=(lst.id,))
        response = client.post(url, {"pack_id": str(pack.id), "action": "add"})
        assert response.status_code == 302
        lst.refresh_from_db()
        assert pack in lst.packs.all()

    def test_manage_packs_requires_custom_content_group(
        self, client, make_user, content_house
    ):
        other_user = make_user("otheruser2", "password")
        client.force_login(other_user)
        lst = List.objects.create(
            name="Other List", content_house=content_house, owner=other_user
        )
        url = reverse("core:list-packs", args=(lst.id,))
        response = client.get(url)
        assert response.status_code == 404

    def test_manage_packs_search(self, client, cc_user, make_list, pack):
        client.force_login(cc_user)
        lst = make_list("Test List")
        url = reverse("core:list-packs", args=(lst.id,))
        response = client.get(url, {"q": "Test"})
        assert response.status_code == 200
        assert pack.name.encode() in response.content

    def test_manage_packs_my_packs_filter(
        self, client, cc_user, make_list, make_user, make_pack
    ):
        client.force_login(cc_user)
        lst = make_list("Test List")
        my_pack = make_pack("My Pack")
        other_user = make_user("otherpackowner", "password")
        other_pack = make_pack("Other Pack", owner=other_user, listed=True)
        url = reverse("core:list-packs", args=(lst.id,))
        # Without filter: both visible
        response = client.get(url)
        assert my_pack.name.encode() in response.content
        assert other_pack.name.encode() in response.content
        # With filter: only own pack visible
        response = client.get(url, {"my": "1"})
        assert my_pack.name.encode() in response.content
        assert other_pack.name.encode() not in response.content


@pytest.mark.django_db
class TestNewListPacksInterstitial:
    """Test the pack selection interstitial during list creation."""

    def test_cc_user_redirected_to_packs(self, client, cc_user, content_house):
        client.force_login(cc_user)
        url = reverse("core:lists-new")
        response = client.post(
            url,
            {"name": "New List", "content_house": content_house.id, "public": True},
        )
        assert response.status_code == 302
        # Should redirect to packs interstitial
        assert "/packs" in response.url

    def test_regular_user_redirected_to_list(self, client, make_user, content_house):
        other_user = make_user("regularuser", "password")
        client.force_login(other_user)
        url = reverse("core:lists-new")
        response = client.post(
            url,
            {"name": "New List", "content_house": content_house.id, "public": True},
        )
        assert response.status_code == 302
        # Should redirect to list detail, not packs
        assert "/packs" not in response.url

    def test_packs_interstitial_page(self, client, cc_user, make_list, pack):
        client.force_login(cc_user)
        lst = make_list("New List")
        url = reverse("core:lists-new-packs", args=(lst.id,))
        response = client.get(url)
        assert response.status_code == 200
        assert b"Content Packs" in response.content

    def test_packs_interstitial_select_packs(self, client, cc_user, make_list, pack):
        client.force_login(cc_user)
        lst = make_list("New List")
        url = reverse("core:lists-new-packs", args=(lst.id,))
        response = client.post(url, {"pack_ids": [str(pack.id)]})
        assert response.status_code == 302
        lst.refresh_from_db()
        assert pack in lst.packs.all()

    def test_packs_interstitial_skip(self, client, cc_user, make_list):
        client.force_login(cc_user)
        lst = make_list("New List")
        url = reverse("core:lists-new-packs", args=(lst.id,))
        response = client.post(url)
        assert response.status_code == 302
        lst.refresh_from_db()
        assert lst.packs.count() == 0

    def test_non_cc_user_redirected_away(self, client, make_user, content_house):
        other_user = make_user("regularuser2", "password")
        client.force_login(other_user)
        lst = List.objects.create(
            name="New List", content_house=content_house, owner=other_user
        )
        url = reverse("core:lists-new-packs", args=(lst.id,))
        response = client.get(url)
        assert response.status_code == 302
        assert f"/list/{lst.id}" in response.url


@pytest.mark.django_db
class TestPackContentVisibility:
    """Test that pack content is visible when a list is subscribed."""

    def test_pack_fighter_not_visible_without_subscription(
        self, pack_fighter, content_house
    ):
        """Pack fighter should not appear in default queryset."""
        fighters = ContentFighter.objects.available_for_house(content_house)
        assert pack_fighter not in fighters

    def test_pack_fighter_visible_with_subscription(
        self, make_list, pack, pack_fighter, content_house
    ):
        """Pack fighter should appear when list is subscribed to the pack."""
        lst = make_list("Test List")
        lst.packs.add(pack)
        fighters = ContentFighter.objects.with_packs(
            lst.packs.all()
        ).available_for_house(content_house)
        assert pack_fighter in fighters

    def test_pack_rule_not_visible_without_subscription(self, pack_rule):
        """Pack rule should not appear in default queryset."""
        rules = ContentRule.objects.all()
        assert pack_rule not in rules

    def test_pack_rule_visible_with_subscription(self, make_list, pack, pack_rule):
        """Pack rule should appear when list is subscribed to the pack."""
        lst = make_list("Test List")
        lst.packs.add(pack)
        rules = ContentRule.objects.with_packs(lst.packs.all())
        assert pack_rule in rules


@pytest.mark.django_db
class TestPackDetailViewSubscription:
    """Test the pack detail view subscription UI."""

    def test_pack_detail_shows_add_to_lists_link(
        self, client, cc_user, pack, make_list
    ):
        client.force_login(cc_user)
        make_list("Test List")
        url = reverse("core:pack", args=(pack.id,))
        response = client.get(url)
        assert response.status_code == 200
        assert b"Add to Lists" in response.content

    def test_pack_detail_shows_subscribed_badge(self, client, cc_user, pack, make_list):
        client.force_login(cc_user)
        lst = make_list("Subscribed List")
        lst.packs.add(pack)
        url = reverse("core:pack", args=(pack.id,))
        response = client.get(url)
        assert response.status_code == 200
        # Badge with count should appear in the dropdown
        assert b"Add to Lists" in response.content


@pytest.mark.django_db
class TestPackListsView:
    """Test the dedicated pack lists management page."""

    def test_pack_lists_page(self, client, cc_user, pack, make_list):
        client.force_login(cc_user)
        make_list("Test List")
        url = reverse("core:pack-lists", args=(pack.id,))
        response = client.get(url)
        assert response.status_code == 200
        assert b"Your Lists" in response.content

    def test_pack_lists_shows_subscribed(self, client, cc_user, pack, make_list):
        client.force_login(cc_user)
        lst = make_list("Subscribed List")
        lst.packs.add(pack)
        url = reverse("core:pack-lists", args=(pack.id,))
        response = client.get(url)
        assert response.status_code == 200
        assert b"Subscribed List" in response.content
        assert b"Subscribed Lists" in response.content

    def test_pack_lists_shows_unsubscribed(self, client, cc_user, pack, make_list):
        client.force_login(cc_user)
        make_list("Available List")
        url = reverse("core:pack-lists", args=(pack.id,))
        response = client.get(url)
        assert response.status_code == 200
        assert b"Available List" in response.content
        assert b"Add to List" in response.content

    def test_subscribe_redirects_to_pack_lists(self, client, cc_user, pack, make_list):
        client.force_login(cc_user)
        lst = make_list("Test List")
        url = reverse("core:pack-subscribe", args=(pack.id,))
        response = client.post(
            url, {"list_id": str(lst.id), "return_url": "pack-lists"}
        )
        assert response.status_code == 302
        assert f"/pack/{pack.id}/lists/" in response.url

    def test_unsubscribe_redirects_to_pack_lists(
        self, client, cc_user, pack, make_list
    ):
        client.force_login(cc_user)
        lst = make_list("Test List")
        lst.packs.add(pack)
        url = reverse("core:pack-unsubscribe", args=(pack.id,))
        response = client.post(
            url, {"list_id": str(lst.id), "return_url": "pack-lists"}
        )
        assert response.status_code == 302
        assert f"/pack/{pack.id}/lists/" in response.url


@pytest.mark.django_db
class TestListDetailShowsPacks:
    """Test that the list detail view shows subscribed packs."""

    def test_list_detail_shows_pack_badge(self, client, cc_user, make_list, pack):
        client.force_login(cc_user)
        lst = make_list("Test List")
        lst.packs.add(pack)
        url = reverse("core:list", args=(lst.id,))
        response = client.get(url)
        assert response.status_code == 200
        assert b"Content Pack" in response.content
