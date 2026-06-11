import pytest
from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory
from django.urls import reverse

from gyrinx.core.admin.list import (
    ListAdmin,
    ListFighterAdmin,
    recompute_cost_caches,
    recompute_list_cost_caches,
)
from gyrinx.core.models.list import List, ListFighter


def _admin_request():
    factory = RequestFactory()
    request = factory.post("/admin/")
    request.user = User.objects.create_superuser("admin", "admin@test.com", "password")
    # RequestFactory has no middleware; attach session + message storage so the
    # action's messages.* calls don't blow up.
    setattr(request, "session", {})
    setattr(request, "_messages", FallbackStorage(request))
    return request


@pytest.mark.django_db
def test_listfighter_admin_has_recompute_action():
    admin_instance = admin.site._registry[ListFighter]
    assert isinstance(admin_instance, ListFighterAdmin)
    assert recompute_cost_caches in admin_instance.actions


@pytest.mark.django_db
def test_changelist_search_by_uuid(admin_client, make_list, make_list_fighter):
    """Pasting an object's UUID into the admin search box finds it (BaseAdmin)."""
    lst = make_list("UUID Gang")
    other = make_list("Other Gang")
    fighter = make_list_fighter(lst, "Bozur")
    make_list_fighter(other, "Decoy")

    response = admin_client.get(
        reverse("admin:core_listfighter_changelist"), {"q": str(fighter.id)}
    )
    assert response.status_code == 200
    assert list(response.context["cl"].result_list) == [fighter]

    response = admin_client.get(
        reverse("admin:core_list_changelist"), {"q": str(lst.id)}
    )
    assert response.status_code == 200
    assert list(response.context["cl"].result_list) == [lst]

    # Plain text search is unaffected.
    response = admin_client.get(
        reverse("admin:core_listfighter_changelist"), {"q": "Bozur"}
    )
    assert fighter in response.context["cl"].result_list


@pytest.mark.django_db
def test_fighter_changelist_filter_by_list(admin_client, make_list, make_list_fighter):
    """The autocomplete list filter narrows fighters to the selected list(s)."""
    lst_one = make_list("Gang One")
    lst_two = make_list("Gang Two")
    lst_three = make_list("Gang Three")
    fighter_one = make_list_fighter(lst_one, "One")
    fighter_two = make_list_fighter(lst_two, "Two")
    make_list_fighter(lst_three, "Three")

    url = reverse("admin:core_listfighter_changelist")

    response = admin_client.get(url, {"list_id_in": str(lst_one.id)})
    assert response.status_code == 200
    assert list(response.context["cl"].result_list) == [fighter_one]

    # Multi-select carries comma-separated UUIDs.
    response = admin_client.get(url, {"list_id_in": f"{lst_one.id},{lst_two.id}"})
    assert set(response.context["cl"].result_list) == {fighter_one, fighter_two}

    # The filter widget and its select2 assets are on the page.
    assert b"list_id_in" in response.content
    assert b"admin-autocomplete" in response.content
    assert b"select2" in response.content


@pytest.mark.django_db
def test_fighter_change_page_has_object_action_button(
    admin_client, make_list, make_list_fighter
):
    lst = make_list("Button Gang")
    fighter = make_list_fighter(lst, "Btn")

    response = admin_client.get(
        reverse("admin:core_listfighter_change", args=[fighter.pk])
    )
    assert response.status_code == 200
    assert b'name="_object_action"' in response.content
    assert b'value="recompute_cost_caches"' in response.content


@pytest.mark.django_db
def test_object_action_recomputes_single_fighter(
    admin_client, make_list, make_list_fighter
):
    """Posting an object action from the change page runs it on just that object."""
    lst = make_list("Drift Gang")
    fighter = make_list_fighter(lst, "Drifty")
    correct = fighter.cost_int()
    ListFighter.objects.filter(pk=fighter.pk).update(
        rating_current=correct + 45, dirty=False
    )

    url = reverse("admin:core_listfighter_change", args=[fighter.pk])
    response = admin_client.post(url, {"_object_action": "recompute_cost_caches"})
    assert response.status_code == 302
    assert response.url == url

    fighter.refresh_from_db()
    assert fighter.rating_current == correct


@pytest.mark.django_db
def test_object_action_rejects_unlisted_action(
    admin_client, make_list, make_list_fighter
):
    """Only actions named in object_actions can run from the change page."""
    lst = make_list("Locked Gang")
    fighter = make_list_fighter(lst, "Lock")

    url = reverse("admin:core_listfighter_change", args=[fighter.pk])
    response = admin_client.post(url, {"_object_action": "delete_selected"})
    assert response.status_code == 403
    assert ListFighter.objects.filter(pk=fighter.pk).exists()


@pytest.mark.django_db
def test_recompute_list_cost_caches_action(make_list, make_list_fighter):
    """The List-level action rebuilds its fighters and reconciles aggregates."""
    lst = make_list("Whole Gang")
    fighter = make_list_fighter(lst, "Member")
    correct = fighter.cost_int()
    inflated = correct + 45
    ListFighter.objects.filter(pk=fighter.pk).update(
        rating_current=inflated, dirty=False
    )
    List.objects.filter(pk=lst.pk).update(rating_current=inflated, dirty=False)

    site = AdminSite()
    admin_instance = ListAdmin(List, site)
    request = _admin_request()

    recompute_list_cost_caches(admin_instance, request, List.objects.filter(pk=lst.pk))

    fighter.refresh_from_db()
    lst.refresh_from_db()
    assert fighter.rating_current == correct
    assert lst.rating_current == correct


@pytest.mark.django_db
def test_recompute_cost_caches_fixes_drift(make_list, make_list_fighter):
    """A fighter whose cached rating drifted (but is marked clean) is repaired."""
    lst = make_list("Drifty Gang")
    fighter = make_list_fighter(lst, "Bozur")

    correct = fighter.cost_int()

    # Simulate the kill-handler drift: cache inflated but clean (dirty=False),
    # and the list's aggregate caches carry the same inflation.
    inflated = correct + 45
    ListFighter.objects.filter(pk=fighter.pk).update(
        rating_current=inflated, dirty=False
    )
    type(lst).objects.filter(pk=lst.pk).update(rating_current=inflated, dirty=False)

    site = AdminSite()
    admin_instance = ListFighterAdmin(ListFighter, site)
    request = _admin_request()
    queryset = ListFighter.objects.filter(pk=fighter.pk)

    recompute_cost_caches(admin_instance, request, queryset)

    fighter.refresh_from_db()
    lst.refresh_from_db()

    assert fighter.rating_current == correct
    assert fighter.dirty is False
    # List aggregate reconciled to the corrected fighter value.
    assert lst.rating_current == correct


@pytest.mark.django_db
def test_recompute_cost_caches_fixes_stash_drift(make_list):
    """The reported bug: an inflated stash fighter reconciles list.stash_current."""
    lst = make_list("Stashy Gang")
    stash = lst.ensure_stash()

    correct = stash.cost_int()

    # Stash fighter's cache inflated but clean, with the same inflation baked
    # into the list's stash aggregate (the kill-handler drift scenario).
    inflated = correct + 45
    ListFighter.objects.filter(pk=stash.pk).update(rating_current=inflated, dirty=False)
    type(lst).objects.filter(pk=lst.pk).update(stash_current=inflated, dirty=False)

    site = AdminSite()
    admin_instance = ListFighterAdmin(ListFighter, site)
    request = _admin_request()
    queryset = ListFighter.objects.filter(pk=stash.pk)

    recompute_cost_caches(admin_instance, request, queryset)

    stash.refresh_from_db()
    lst.refresh_from_db()

    assert stash.rating_current == correct
    assert lst.stash_current == correct


@pytest.mark.django_db
def test_recompute_cost_caches_noop_when_in_sync(make_list, make_list_fighter):
    """Running on an already-correct fighter leaves the cache untouched."""
    lst = make_list("Tidy Gang")
    fighter = make_list_fighter(lst, "Clean")
    fighter.facts_from_db(update=True)
    lst.facts_from_db(update=True)

    before = ListFighter.objects.get(pk=fighter.pk).rating_current

    site = AdminSite()
    admin_instance = ListFighterAdmin(ListFighter, site)
    request = _admin_request()
    queryset = ListFighter.objects.filter(pk=fighter.pk)

    recompute_cost_caches(admin_instance, request, queryset)

    fighter.refresh_from_db()
    assert fighter.rating_current == before
