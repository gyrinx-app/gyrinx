"""The admin surfaces for creating badges and handing them out.

Admin actions are easy to ship broken — nothing else exercises them, and a
mistake only shows up when somebody clicks it. These drive the real ones
through a request, including the intermediate confirmation page.
"""

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory
from django.urls import reverse

from gyrinx.accounts.admin import (
    BadgeAdmin,
    BadgeForm,
    BadgeGrantAdmin,
    grant_badge_to_users,
    resolve_people,
)
from gyrinx.accounts.models import Badge, BadgeGrant
from gyrinx.badges import invalidate_granted_badges

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def clear_badge_cache():
    invalidate_granted_badges()
    yield
    invalidate_granted_badges()


@pytest.fixture
def staff():
    return User.objects.create_superuser("badgeadmin", "a@example.com", "password")


@pytest.fixture
def badge():
    return Badge.objects.create(
        slug="playtester", title="Playtester", description="Tested n26"
    )


def _request(staff, method="get", data=None):
    factory = RequestFactory()
    request = getattr(factory, method)("/admin/", data or {})
    request.user = staff
    # The action's confirmation page renders through the admin's own context.
    request.session = {}
    request._messages = _Messages()
    return request


class _Messages:
    """Collect messages instead of needing the middleware.

    Iterable because the admin's base template loops over them when the
    confirmation page renders.
    """

    def __init__(self):
        self.sent = []

    def add(self, level, message, extra_tags=""):
        self.sent.append(message)

    def __iter__(self):
        return iter([])


def test_uploading_a_drawing_fills_in_the_address(staff):
    upload = SimpleUploadedFile(
        "playtester.svg",
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2 2">'
        b'<rect width="2" height="2" fill="#B1873F"/></svg>',
        content_type="image/svg+xml",
    )
    form = BadgeForm(
        data={
            "slug": "playtester",
            "title": "Playtester",
            "description": "Tested n26",
            "artwork_url": "",
            "rank": 0,
        },
        files={"artwork_upload": upload},
    )
    assert form.is_valid(), form.errors
    assert form.cleaned_data["artwork_url"].endswith(".svg")
    assert "badges/" in form.cleaned_data["artwork_url"]


def test_a_badge_cannot_take_a_built_in_slug_through_the_admin(staff):
    form = BadgeForm(
        data={
            "slug": "staff",
            "title": "Staff",
            "description": "Not this one",
            "artwork_url": "",
            "rank": 0,
        }
    )
    assert not form.is_valid()
    assert "slug" in form.errors


def test_an_address_outside_our_storage_is_refused(staff):
    form = BadgeForm(
        data={
            "slug": "playtester",
            "title": "Playtester",
            "description": "Tested n26",
            "artwork_url": "https://evil.example/badge.svg",
            "rank": 0,
        }
    )
    assert not form.is_valid()
    assert "artwork_url" in form.errors


def test_the_grant_action_confirms_before_it_grants(staff, badge, make_user):
    person = make_user("tester", "password")
    modeladmin = BadgeGrantAdmin(BadgeGrant, AdminSite())
    request = _request(staff)

    response = grant_badge_to_users(
        modeladmin, request, User.objects.filter(pk=person.pk)
    )

    assert response.status_code == 200
    assert badge.title in response.content.decode()
    # Nothing granted yet — the page is the confirmation step.
    assert not BadgeGrant.objects.exists()


def test_the_grant_action_grants_to_everybody_selected(staff, badge, make_user):
    people = [make_user(f"tester{n}", "password") for n in range(3)]
    modeladmin = BadgeGrantAdmin(BadgeGrant, AdminSite())
    request = _request(
        staff,
        "post",
        {"post": "yes", "badge": str(badge.pk), "reason": "Tested n26"},
    )

    grant_badge_to_users(
        modeladmin, request, User.objects.filter(pk__in=[p.pk for p in people])
    )

    assert BadgeGrant.objects.count() == 3
    assert {g.user for g in BadgeGrant.objects.all()} == set(people)
    assert all(g.granted_by == staff for g in BadgeGrant.objects.all())
    assert all(g.reason == "Tested n26" for g in BadgeGrant.objects.all())


def test_running_the_grant_action_twice_grants_nothing_new(staff, badge, make_user):
    person = make_user("tester", "password")
    modeladmin = BadgeGrantAdmin(BadgeGrant, AdminSite())

    for _ in range(2):
        request = _request(
            staff, "post", {"post": "yes", "badge": str(badge.pk), "reason": ""}
        )
        grant_badge_to_users(modeladmin, request, User.objects.filter(pk=person.pk))

    assert BadgeGrant.objects.count() == 1


def test_a_pasted_list_matches_usernames_and_emails(make_user):
    alice = make_user("alice", "password")
    alice.email = "alice@example.com"
    alice.save()
    bob = make_user("bob", "password")

    people, missing = resolve_people("ALICE@example.com\n bob , nobody-at-all")

    assert people == [alice, bob]
    assert missing == ["nobody-at-all"]


def test_a_pasted_list_names_the_same_person_once(make_user):
    alice = make_user("alice", "password")
    alice.email = "alice@example.com"
    alice.save()

    people, missing = resolve_people("alice\nalice@example.com")

    assert people == [alice]
    assert missing == []


def test_granting_to_a_pasted_list_grants_and_reports_the_misses(
    client, staff, badge, make_user
):
    alice = make_user("alice", "password")
    client.force_login(staff)

    response = client.post(
        reverse("admin:accounts_badge_grant_to_list"),
        {
            "badge": str(badge.pk),
            "people": "alice\nghost",
            "reason": "Tested n26",
        },
    )

    assert response.status_code == 200
    assert list(BadgeGrant.objects.values_list("user", flat=True)) == [alice.pk]
    assert "ghost" in response.content.decode()


def test_the_paste_page_is_linked_from_the_badge_list(client, staff):
    client.force_login(staff)
    response = client.get(reverse("admin:accounts_badge_changelist"))
    assert reverse("admin:accounts_badge_grant_to_list") in response.content.decode()


def test_the_changelist_draws_the_artwork(staff, badge):
    modeladmin = BadgeAdmin(Badge, AdminSite())
    # No artwork stored, so there is nothing to draw and nothing pretending to.
    assert modeladmin.preview(badge) == "—"


def test_the_changelist_says_who_holds_a_badge(staff, badge, make_user):
    modeladmin = BadgeAdmin(Badge, AdminSite())
    assert modeladmin.held_by(badge) == 0

    BadgeGrant.objects.create(badge=badge, user=make_user("tester", "password"))
    assert modeladmin.held_by(badge) == 1

    BadgeGrant.objects.create(badge=badge, audience=BadgeGrant.Audience.EVERYONE)
    assert modeladmin.held_by(badge) == "Everyone"
