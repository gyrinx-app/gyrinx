import pytest
from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory

from gyrinx.core.admin.list import ListFighterAdmin, recompute_cost_caches
from gyrinx.core.models.list import ListFighter


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
def test_listfighter_id_is_searchable():
    admin_instance = admin.site._registry[ListFighter]
    assert "=id" in admin_instance.search_fields


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
