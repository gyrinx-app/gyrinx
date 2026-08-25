"""The admin's window onto player data: every page opens, and the
ledger-adjacent models stay read-only there.

Smoke tests, deliberately: the admin is generated from the
registrations, so the failure mode is a page that 500s on load (a
misnamed field, an autocomplete pointing at an admin with no search) —
which opening every page catches, and little else would.
"""

import pytest
from django.contrib import admin as django_admin
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core import admin as core_admin
from n26.core.models import (
    Assignment,
    Gang,
    LedgerEntry,
    LedgerEvent,
    Miniature,
    Stash,
)
from n26.core.operations import operation

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff(db):
    return User.objects.create_superuser("boss", "", "password")


@pytest.fixture
def clerk(db):
    """Staff, but not a superuser — the admin's ordinary reader."""
    return User.objects.create_user("clerk", "", "password", is_staff=True)


@pytest.fixture
def gang(gang_type, staff, make_profile):
    gang = Gang.objects.create(name="The Ashen Choir", owner=staff, gang_type=gang_type)
    with operation(gang, actor=staff) as op:
        op.found(gang_type)
        op.hire(make_profile("Ganger", price=0), "Vex")
    return gang


N26_MODELS = [
    model for model in django_admin.site._registry if model._meta.app_label == "n26"
]


def test_every_n26_model_is_registered():
    """The registry covers the app's stored models — a new model that
    skips admin registration should be a decision, not a default."""
    assert {model.__name__ for model in N26_MODELS} == {
        "Assignment",
        "AssignmentSet",
        "Campaign",
        "Gang",
        "LedgerEntry",
        "LedgerEvent",
        "Miniature",
        "PrintConfig",
        "Stash",
        "StatOverride",
    }


@pytest.mark.parametrize("model", N26_MODELS, ids=lambda m: m.__name__)
def test_every_changelist_opens(client, staff, gang, model):
    client.force_login(staff)
    url = reverse(f"admin:n26_{model._meta.model_name}_changelist")
    assert client.get(url).status_code == 200


def test_the_gang_change_page_opens(client, staff, gang):
    client.force_login(staff)
    url = reverse("admin:n26_gang_change", args=[gang.pk])
    assert client.get(url).status_code == 200


@pytest.mark.parametrize(
    "model", [Assignment, LedgerEntry, LedgerEvent, Stash], ids=lambda m: m.__name__
)
def test_ledger_adjacent_models_refuse_writes(client, staff, gang, model):
    """Player data is written by operations and nowhere else — the admin
    add page for these is a door that must not open."""
    client.force_login(staff)
    url = reverse(f"admin:n26_{model._meta.model_name}_add")
    assert client.get(url).status_code == 403


def test_the_index_namespaces_the_editions(client, staff):
    """Two editions' apps interleave on the index; the prefixes are what
    says which game a row belongs to."""
    client.force_login(staff)
    body = client.get(reverse("admin:index")).content.decode()
    assert "N26 · Core" in body
    assert "N26 · Library" in body
    assert "N23 · Core" in body
    assert "N23 · Content" in body


def test_readonly_admin_is_what_the_registry_uses():
    """The read-only guard is inheritance, so a new ledger-adjacent
    registration gets it by subclassing rather than by remembering three
    permission overrides."""
    for model in (Assignment, LedgerEntry, LedgerEvent, Stash):
        assert isinstance(django_admin.site._registry[model], core_admin.ReadOnlyAdmin)


class TestWhatTheGuardStillRefuses:
    """Writing is refused of everyone; removing is a superuser's."""

    def _asked(self, user):
        from django.test import RequestFactory

        request = RequestFactory().get("/")
        request.user = user
        return request

    def test_nobody_may_write_through_it(self, staff, clerk):
        guard = django_admin.site._registry[Assignment]

        for user in (staff, clerk):
            asked = self._asked(user)
            assert guard.has_add_permission(asked) is False
            assert guard.has_change_permission(asked) is False

    def test_a_superuser_may_remove_and_a_staffer_may_not(self, staff, clerk):
        guard = django_admin.site._registry[Assignment]

        assert guard.has_delete_permission(self._asked(staff)) is True
        assert guard.has_delete_permission(self._asked(clerk)) is False

    def test_no_changelist_offers_a_batch_delete(self, staff):
        """Deletion is deliberate, one at a time, on the page that says
        what goes with it — including the gang's own changelist."""
        for model in (Assignment, LedgerEntry, LedgerEvent, Stash, Gang):
            guard = django_admin.site._registry[model]
            assert "delete_selected" not in guard.get_actions(self._asked(staff))

    def test_a_single_row_may_still_be_removed(self, staff):
        """The escape hatch the guard exists to keep open: one thing,
        deliberately, from its own page."""
        guard = django_admin.site._registry[LedgerEvent]

        assert guard.has_delete_permission(self._asked(staff)) is True


@pytest.mark.django_db
def test_a_superuser_can_delete_a_gang_and_everything_it_owns(client, staff, gang):
    """A gang deleted through the admin takes its assignments, its
    ledger and its events. Its models stay, gangless, as they do
    whenever a membership ends."""
    assert Assignment.objects.filter(gang_root=gang).exists()
    # An entry hangs off its assignment rather than the gang, so it goes
    # the same way: down the cascade, one step further along.
    assert LedgerEntry.objects.filter(assignment__gang_root=gang).exists()
    hired = list(
        Miniature.objects.filter(membership__gang=gang).values_list("pk", flat=True)
    )
    assert hired
    client.force_login(staff)

    response = client.post(
        reverse("admin:n26_gang_delete", args=[gang.pk]), {"post": "yes"}
    )

    assert response.status_code == 302
    assert not Gang.objects.filter(pk=gang.pk).exists()
    assert not Assignment.objects.filter(gang_root=gang.pk).exists()
    assert not LedgerEntry.objects.filter(assignment__gang_root=gang.pk).exists()
    assert not LedgerEvent.objects.filter(gang=gang.pk).exists()
    # The models stay, and stay gangless: a membership is an assignment
    # like any other, and a model is not deleted by the ending of one
    # (test_miniature.py pins the same rule from the other side).
    left = Miniature.objects.filter(pk__in=hired)
    assert left.count() == len(hired)
    assert all(model.gang is None for model in left)


@pytest.mark.django_db
def test_a_staffer_is_refused_the_same_deletion(client, clerk, gang):
    """The other half of the gate, asked through the door rather than
    of the permission method."""
    client.force_login(clerk)

    response = client.post(
        reverse("admin:n26_gang_delete", args=[gang.pk]), {"post": "yes"}
    )

    assert response.status_code in (302, 403)
    assert Gang.objects.filter(pk=gang.pk).exists()
