"""Tests for admin impersonation (middleware overlay + start/stop views)."""

from datetime import timedelta

import pytest
from django.http import HttpResponse
from django.urls import reverse
from django.utils import timezone

from gyrinx.analytics.models import Event
from gyrinx.impersonation import (
    IMPERSONATE_KEY,
    IMPERSONATE_LOG_KEY,
    IMPERSONATE_STARTED_KEY,
    can_impersonate,
    can_impersonate_target,
)
from gyrinx.middleware import ImpersonationMiddleware
from gyrinx.site.models import ImpersonationLog


@pytest.fixture
def superuser(make_user):
    u = make_user("super", "password")
    u.is_staff = True
    u.is_superuser = True
    u.save()
    return u


def _run_middleware(request):
    """Run ImpersonationMiddleware over a bare RequestFactory request."""
    ImpersonationMiddleware(lambda r: HttpResponse())(request)


# --- permission helpers -----------------------------------------------------


@pytest.mark.django_db
def test_can_impersonate_helpers(superuser, user, make_user):
    assert can_impersonate(superuser) is True
    assert can_impersonate(user) is False

    assert can_impersonate_target(superuser, user) is True
    # Cannot impersonate self.
    assert can_impersonate_target(superuser, superuser) is False
    # Cannot impersonate an inactive user.
    inactive = make_user("inactive", "password")
    inactive.is_active = False
    inactive.save()
    assert can_impersonate_target(superuser, inactive) is False
    # A non-superuser cannot impersonate anyone.
    assert can_impersonate_target(user, make_user("other", "password")) is False


# --- start / stop views -----------------------------------------------------


@pytest.mark.django_db
def test_start_impersonation_sets_session_and_log(client, superuser, user):
    client.force_login(superuser)
    resp = client.post(reverse("core:impersonate-start", args=[user.id]), {"next": "/"})
    assert resp.status_code == 302
    assert client.session[IMPERSONATE_KEY] == user.id

    log = ImpersonationLog.objects.get()
    assert log.owner == superuser
    assert log.target == user
    assert log.ended_at is None


@pytest.mark.django_db
def test_impersonation_swaps_request_user_and_shows_banner(client, superuser, user):
    client.force_login(superuser)
    client.post(reverse("core:impersonate-start", args=[user.id]), {"next": "/"})

    resp = client.get(reverse("core:account_home"))
    assert resp.status_code == 200
    assert resp.context["user"] == user
    assert resp.context["is_impersonating"] is True
    assert resp.context["impersonator"] == superuser
    assert "Stop impersonating" in resp.content.decode()


@pytest.mark.django_db
def test_impersonation_attributes_writes_to_target(client, superuser, user, make_user):
    """A write performed while impersonating is attributed to the target."""
    other = make_user("viewed", "password")
    client.force_login(superuser)
    client.post(reverse("core:impersonate-start", args=[user.id]), {"next": "/"})

    # Visiting a profile logs an Event with owner=request.user.
    client.get(reverse("core:user", args=[other.username]))

    latest = Event.objects.order_by("-created").first()
    assert latest is not None
    # Attributed to the impersonated user, not the admin.
    assert latest.owner == user


@pytest.mark.django_db
def test_stop_impersonation_clears_session_and_closes_log(client, superuser, user):
    client.force_login(superuser)
    client.post(reverse("core:impersonate-start", args=[user.id]), {"next": "/"})

    resp = client.post(reverse("core:impersonate-stop"), {"next": "/"})
    assert resp.status_code == 302
    assert IMPERSONATE_KEY not in client.session

    log = ImpersonationLog.objects.get()
    assert log.ended_at is not None
    assert log.ended_reason == ImpersonationLog.EndedReason.MANUAL

    # And a subsequent request is the admin again.
    resp = client.get(reverse("core:account_home"))
    assert resp.context["user"] == superuser
    assert resp.context["is_impersonating"] is False


@pytest.mark.django_db
def test_non_superuser_cannot_start(client, user, make_user):
    target = make_user("target", "password")
    client.force_login(user)
    resp = client.post(reverse("core:impersonate-start", args=[target.id]))
    assert resp.status_code == 403
    assert not ImpersonationLog.objects.exists()
    assert IMPERSONATE_KEY not in client.session


@pytest.mark.django_db
def test_cannot_impersonate_self(client, superuser):
    client.force_login(superuser)
    resp = client.post(reverse("core:impersonate-start", args=[superuser.id]))
    assert resp.status_code == 403
    assert not ImpersonationLog.objects.exists()


@pytest.mark.django_db
def test_can_impersonate_another_admin(client, superuser, make_user):
    other_admin = make_user("admin2", "password")
    other_admin.is_staff = True
    other_admin.is_superuser = True
    other_admin.save()

    client.force_login(superuser)
    resp = client.post(
        reverse("core:impersonate-start", args=[other_admin.id]), {"next": "/"}
    )
    assert resp.status_code == 302
    assert client.session[IMPERSONATE_KEY] == other_admin.id


@pytest.mark.django_db
def test_get_request_is_rejected(client, superuser, user):
    client.force_login(superuser)
    resp = client.get(reverse("core:impersonate-start", args=[user.id]))
    assert resp.status_code == 405


@pytest.mark.django_db
def test_already_impersonating_is_refused(client, superuser, user, make_user):
    third = make_user("third", "password")
    client.force_login(superuser)
    client.post(reverse("core:impersonate-start", args=[user.id]), {"next": "/"})

    # Attempt to start a second, nested impersonation.
    resp = client.post(
        reverse("core:impersonate-start", args=[third.id]), {"next": "/"}
    )
    assert resp.status_code == 302
    # Still impersonating the first target; only one log created.
    assert client.session[IMPERSONATE_KEY] == user.id
    assert ImpersonationLog.objects.count() == 1


@pytest.mark.django_db
def test_logout_closes_open_log(client, superuser, user):
    client.force_login(superuser)
    client.post(reverse("core:impersonate-start", args=[user.id]), {"next": "/"})

    client.logout()

    log = ImpersonationLog.objects.get()
    assert log.ended_at is not None
    assert log.ended_reason == ImpersonationLog.EndedReason.LOGOUT


# --- menu rendering ---------------------------------------------------------


@pytest.mark.django_db
def test_list_detail_shows_impersonate_for_superuser(client, superuser, make_list):
    lst = make_list("Test list", public=True)  # owned by the `user` fixture
    client.force_login(superuser)
    resp = client.get(reverse("core:list", args=[lst.id]))
    assert resp.status_code == 200
    assert "Impersonate owner" in resp.content.decode()


@pytest.mark.django_db
def test_campaign_detail_shows_impersonate_for_superuser(client, superuser, campaign):
    client.force_login(superuser)
    resp = client.get(reverse("core:campaign", args=[campaign.id]))
    assert resp.status_code == 200
    assert "Impersonate arbitrator" in resp.content.decode()


@pytest.mark.django_db
def test_user_profile_shows_impersonate_for_superuser(client, superuser, user):
    client.force_login(superuser)
    resp = client.get(reverse("core:user", args=[user.username]))
    assert resp.status_code == 200
    assert "Impersonate this user" in resp.content.decode()


@pytest.mark.django_db
def test_list_detail_hides_impersonate_for_regular_user(client, user, make_list):
    lst = make_list("Test list", public=True)
    other = user  # owner
    client.force_login(other)
    resp = client.get(reverse("core:list", args=[lst.id]))
    assert resp.status_code == 200
    assert "Impersonate owner" not in resp.content.decode()


# --- middleware unit tests --------------------------------------------------


@pytest.mark.django_db
def test_middleware_swaps_request_user(rf, superuser, user):
    log = ImpersonationLog.objects.create(owner=superuser, target=user)
    request = rf.get("/n23/lists/")
    request.user = superuser
    request.session = {
        IMPERSONATE_KEY: user.id,
        IMPERSONATE_STARTED_KEY: timezone.now().isoformat(),
        IMPERSONATE_LOG_KEY: str(log.pk),
    }

    _run_middleware(request)

    assert request.is_impersonating is True
    assert request.user == user
    assert request.impersonator == superuser


@pytest.mark.django_db
def test_middleware_expires_stale_session(rf, superuser, user):
    log = ImpersonationLog.objects.create(owner=superuser, target=user)
    request = rf.get("/n23/lists/")
    request.user = superuser
    request.session = {
        IMPERSONATE_KEY: user.id,
        IMPERSONATE_STARTED_KEY: (timezone.now() - timedelta(hours=4)).isoformat(),
        IMPERSONATE_LOG_KEY: str(log.pk),
    }

    _run_middleware(request)

    assert request.is_impersonating is False
    assert request.user == superuser
    assert IMPERSONATE_KEY not in request.session
    log.refresh_from_db()
    assert log.ended_at is not None
    assert log.ended_reason == ImpersonationLog.EndedReason.EXPIRED


@pytest.mark.django_db
def test_middleware_revokes_when_not_superuser(rf, user, make_user):
    """If the real principal is no longer a superuser, drop the overlay."""
    target = make_user("target", "password")
    log = ImpersonationLog.objects.create(owner=user, target=target)
    request = rf.get("/n23/lists/")
    request.user = user  # not a superuser
    request.session = {
        IMPERSONATE_KEY: target.id,
        IMPERSONATE_STARTED_KEY: timezone.now().isoformat(),
        IMPERSONATE_LOG_KEY: str(log.pk),
    }

    _run_middleware(request)

    assert request.is_impersonating is False
    assert request.user == user
    assert IMPERSONATE_KEY not in request.session
    log.refresh_from_db()
    assert log.ended_reason == ImpersonationLog.EndedReason.REVOKED


@pytest.mark.django_db
def test_middleware_does_not_swap_on_admin_path(rf, superuser, user):
    log = ImpersonationLog.objects.create(owner=superuser, target=user)
    request = rf.get("/admin/")
    request.user = superuser
    request.session = {
        IMPERSONATE_KEY: user.id,
        IMPERSONATE_STARTED_KEY: timezone.now().isoformat(),
        IMPERSONATE_LOG_KEY: str(log.pk),
    }

    _run_middleware(request)

    # Not swapped on the admin, and the overlay is preserved (not cleared).
    assert request.is_impersonating is False
    assert request.user == superuser
    assert request.session[IMPERSONATE_KEY] == user.id
