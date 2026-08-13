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
from n26.core.models import Assignment, Gang, LedgerEntry, LedgerEvent, Stash
from n26.core.operations import operation

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff(db):
    return User.objects.create_superuser("boss", "", "password")


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
