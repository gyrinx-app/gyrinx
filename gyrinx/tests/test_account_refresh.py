"""Account navigation and allauth integration contracts for the N26 refresh."""

import re
import time

import pytest
from allauth.account.models import EmailAddress
from django.template import Context, Origin, Template
from django.urls import reverse

from gyrinx.accounts.models import UserProfile
from gyrinx.analytics.models import Event, EventVerb
from gyrinx.analytics.nouns import PlatformNoun
from gyrinx.editions import COOKIE_NAME
from gyrinx.site.models import notify


@pytest.mark.django_db
@pytest.mark.parametrize("edition, destination", [("n23", "/"), ("n26", "/n26/")])
@pytest.mark.parametrize(
    "url",
    ["core:account_home", "account-settings", "account-security", "core:notifications"],
)
def test_account_home_link_follows_edition_switcher(
    client, user, edition, destination, url
):
    client.force_login(user)
    client.cookies[COOKIE_NAME] = edition
    response = client.get(reverse(url))
    anchors = re.findall(r"<a\b([^>]*)>(.*?)</a>", response.content.decode(), re.S)
    home_links = [
        attrs
        for attrs, content in anchors
        if re.sub(r"<[^>]+>", "", content).strip() == "Home"
    ]
    assert home_links
    assert all(f'href="{destination}"' in attrs for attrs in home_links)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url",
    [
        "core:account_home",
        "account-settings",
        "account-security",
        "core:notifications",
        "account_login",
        "account_signup",
        "account_reset_password",
        "mfa_activate_totp",
    ],
)
def test_account_screens_use_n26_styles(client, user, url):
    if url not in {"account_login", "account_signup"}:
        client.force_login(user)
    response = client.get(reverse(url), follow=True)
    assert response.status_code == 200
    html = response.content.decode()
    assert "designsystem/app.css" in html
    assert "core/css/screen.css" not in html
    assert "bootstrap.min.js" not in html
    assert "form-control" not in html


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url, destination",
    [
        ("account_change_password", "account-security"),
        ("mfa_index", "account-security"),
        ("usersessions_list", "account-security"),
        ("account_email", "account-settings"),
        ("core:badge-settings", "account-settings"),
        ("core:timezone-settings", "account-settings"),
    ],
)
def test_old_account_get_urls_redirect(client, user, url, destination):
    client.force_login(user)
    response = client.get(reverse(url))
    assert response.status_code == 302
    assert response.url == reverse(destination)


@pytest.mark.django_db
def test_combined_settings_save_preferences_without_reverifying_email(client, user):
    EmailAddress.objects.create(
        user=user, email="account@example.com", primary=True, verified=True
    )
    UserProfile.objects.get_or_create(user=user)
    client.force_login(user)
    response = client.post(
        reverse("account-settings"),
        {
            "action_save": "1",
            "email": "account@example.com",
            "timezone": "Europe/London",
            "selected_badge": "none",
        },
    )
    assert response.status_code == 302
    user.profile.refresh_from_db()
    assert user.profile.timezone == "Europe/London"
    assert EmailAddress.objects.filter(user=user).count() == 1


@pytest.mark.django_db
def test_combined_settings_logs_only_changed_preferences(client, user):
    EmailAddress.objects.create(
        user=user, email="account@example.com", primary=True, verified=True
    )
    UserProfile.objects.get_or_create(user=user)
    client.force_login(user)
    data = {
        "action_save": "1",
        "email": "account@example.com",
        "timezone": "UTC",
        "selected_badge": "none",
    }
    assert client.post(reverse("account-settings"), data).status_code == 302
    events = Event.objects.filter(
        owner=user, noun=PlatformNoun.USER, verb=EventVerb.UPDATE
    )
    assert {event.field: event.context for event in events} == {
        "selected_badge": {"selected_badge": "none"},
        "timezone": {"timezone": "UTC"},
    }
    assert client.post(reverse("account-settings"), data).status_code == 302
    assert events.count() == 2


@pytest.mark.django_db
def test_manage_subpage_has_one_page_heading(client, user):
    client.force_login(user)
    html = client.get(reverse("account_logout")).content.decode()
    assert len(re.findall(r"<h1\b", html)) == 1
    assert re.search(r"<h2\b[^>]*>\s*Sign Out\s*</h2>", html)
    assert "<a" not in re.search(r"<h1\b[^>]*>(.*?)</h1>", html, re.S).group(1)


@pytest.mark.django_db
def test_mfa_panels_are_security_subsections(client, user):
    client.force_login(user)
    html = client.get(reverse("account-security")).content.decode()
    assert re.search(r"<h2\b[^>]*>\s*Two-factor authentication\s*</h2>", html)
    assert re.search(r"<h3\b[^>]*>\s*Authenticator app\s*</h3>", html)


@pytest.mark.django_db
def test_notification_json_refresh_rebuilds_pages_without_late_flash(client, user):
    from django.contrib.messages import get_messages

    notes = [notify(recipient=user, subject=f"Update {i}") for i in range(26)]
    client.force_login(user)
    assert (
        client.get(
            reverse("core:notifications"), HTTP_ACCEPT="application/json"
        ).json()["pages"]
        == 2
    )
    result = client.post(
        reverse("core:notifications-bulk"),
        {"action": "archive", "ids": [str(notes[-1].id)]},
        HTTP_ACCEPT="application/json",
    )
    assert result.json() == {"ok": True}
    refreshed = client.get(
        reverse("core:notifications"), HTTP_ACCEPT="application/json"
    ).json()
    assert refreshed["page"] == refreshed["pages"] == 1
    assert refreshed["nextUrl"] == ""
    assert len(refreshed["rows"]) == 25
    assert str(notes[0].id) in {row["id"] for row in refreshed["rows"]}
    response = client.get(reverse("account-security"))
    assert not list(get_messages(response.wsgi_request))


@pytest.mark.django_db
@pytest.mark.parametrize(
    "error_view, code", [("error_400", 400), ("error_403", 403), ("error_404", 404)]
)
def test_shared_error_pages_use_n26_components(rf, user, client, error_view, code):
    from gyrinx.pages import views

    request = rf.get("/missing-page/")
    request.user = user
    request.session = client.session
    request.edition = "n26"
    response = getattr(views, error_view)(request)
    assert response.status_code == code
    html = response.content.decode()
    assert "designsystem/app.css" in html
    assert "bi-house-door" not in html
    assert "btn btn-primary" not in html
    assert 'href="/n26/"' in html


def test_allauth_error_alert_keeps_error_styles():
    html = Template(
        '{% load allauth %}{% element alert level="error" %}'
        "{% slot message %}Example error{% endslot %}{% endelement %}",
        origin=Origin("test", template_name="account/test_adapter.html"),
    ).render(Context())
    assert "bg-red-50" in html
    assert "Example error" in html


def test_allauth_badge_keeps_explanatory_tooltip():
    html = Template(
        '{% load allauth %}{% element badge title="Example explanation" %}'
        "Unspecified{% endelement %}",
        origin=Origin("test", template_name="account/test_adapter.html"),
    ).render(Context())
    assert 'title="Example explanation"' in html


@pytest.mark.parametrize(
    "attrs, submit",
    [
        ("", True),
        ('type="submit"', True),
        ('type="button"', False),
        ('href="/"', False),
    ],
)
def test_allauth_button_uses_success_for_submit_only(attrs, submit):
    html = Template(
        "{% load allauth %}{% element button " + attrs + " %}Example{% endelement %}",
        origin=Origin("test", template_name="account/test_adapter.html"),
    ).render(Context())
    assert ("bg-green-700" in html) == submit


@pytest.mark.django_db
def test_settings_rejects_unavailable_badge_and_invalid_timezone(client, user):
    UserProfile.objects.get_or_create(user=user)
    client.force_login(user)
    response = client.post(
        reverse("account-settings"),
        {
            "action_save": "1",
            "email": user.email,
            "timezone": "bad",
            "selected_badge": "staff",
        },
    )
    assert response.status_code == 200
    props = response.context["settings_form"]
    assert next(f for f in props["fields"] if f["name"] == "selected_badge")["errors"]
    assert next(f for f in props["fields"] if f["name"] == "timezone")["errors"]
    user.profile.refresh_from_db()
    assert user.profile.selected_badge != "staff"


@pytest.mark.django_db
def test_notification_props_sanitize_rich_content_and_keep_open_proxy(
    client, user, make_list
):
    from gyrinx.site.models import notify_list_owner

    notification = notify_list_owner(
        make_list("Example"),
        subject="A linked update",
        content='<p>Hello <strong>bold</strong><img src="/example.png" onerror="alert(1)"></p>',
    )
    client.force_login(user)
    response = client.get(reverse("core:notifications"))
    row = response.context["notification_inbox"]["rows"][0]
    assert row["openUrl"] == reverse("core:notification-open", args=[notification.pk])
    assert row["content"][0]["children"][1]["tag"] == "strong"
    assert "onerror" not in str(row["content"])


@pytest.mark.django_db
def test_json_notification_actions_enforce_ownership(client, user, make_user):
    theirs = notify(recipient=make_user("other-refresh", "password"), subject="Private")
    mine = notify(recipient=user, subject="Mine")
    client.force_login(user)

    def url(n):
        return reverse("core:notification-read", args=[n.pk])

    assert client.post(url(theirs), HTTP_ACCEPT="application/json").status_code == 404
    response = client.post(url(mine), HTTP_ACCEPT="application/json")
    assert response.json() == {"ok": True}
    mine.refresh_from_db()
    assert mine.is_read


@pytest.mark.django_db
def test_combined_settings_new_email_preserves_verified_address(client, user, settings):
    settings.ACCOUNT_REAUTHENTICATION_REQUIRED = False
    old = EmailAddress.objects.create(
        user=user, email="old@example.com", primary=True, verified=True
    )
    client.force_login(user)
    response = client.post(
        reverse("account-settings"),
        {
            "action_save": "1",
            "email": "new@example.com",
            "timezone": "UTC",
            "selected_badge": "none",
        },
    )
    assert response.status_code == 302
    old.refresh_from_db()
    assert old.primary and old.verified
    pending = EmailAddress.objects.get(user=user, email="new@example.com")
    assert not pending.verified and not pending.primary
    response = client.get(reverse("account-settings"))
    assert response.context["new_emailaddress"].pk == pending.pk
    assert "Cancel email change" in response.content.decode()


@pytest.mark.django_db
def test_invalid_password_stays_on_combined_security(client, user):
    client.force_login(user)
    response = client.post(
        reverse("account_change_password"),
        {
            "oldpassword": "wrong",
            "password1": "new-password",
            "password2": "new-password",
        },
    )
    assert response.status_code == 200
    props = response.context["password_form"]
    assert props["fields"][0]["errors"]
    assert all("value" not in field for field in props["fields"])
    assert "Sessions" in response.content.decode()


@pytest.mark.django_db
def test_account_settings_requires_login(client):
    for url in ("account-settings", "account-security"):
        response = client.get(reverse(url))
        assert response.status_code == 302
        assert reverse("account_login") in response.url


@pytest.mark.django_db
def test_settings_offers_artwork_for_every_available_badge(client, user):
    from base64 import b64decode

    from gyrinx.accounts.models import PatreonStatus

    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.patreon_status = PatreonStatus.ACTIVE
    profile.patreon_tier = "Guilder"
    profile.save()
    client.force_login(user)
    response = client.get(reverse("account-settings"))
    field = next(
        f
        for f in response.context["settings_form"]["fields"]
        if f["name"] == "selected_badge"
    )
    assert [c["value"] for c in field["choices"]] == ["scummer", "guilder", "none"]
    assert field["value"] == "guilder"
    for choice in field["choices"][:-1]:
        assert choice["imageUrl"].startswith("data:image/svg+xml;base64,")
        assert "<svg" in b64decode(choice["imageUrl"].split(",", 1)[1]).decode()
    assert field["choices"][-1]["imageUrl"] == ""


@pytest.mark.django_db
def test_password_change_returns_to_security_and_keeps_current_session(client, user):
    user.set_password("old-account-password")
    user.save()
    client.force_login(user)
    response = client.post(
        reverse("account_change_password"),
        {
            "oldpassword": "old-account-password",
            "password1": "new-account-password-927",
            "password2": "new-account-password-927",
            "next": reverse("account-security"),
        },
    )
    assert response.status_code == 302
    assert response.url == reverse("account-security")
    user.refresh_from_db()
    assert user.check_password("new-account-password-927")
    assert client.get(response.url).status_code == 200


@pytest.mark.django_db
def test_settings_cancel_email_change_preserves_verified_email(client, user):
    current = EmailAddress.objects.create(
        user=user, email="current@example.com", primary=True, verified=True
    )
    pending = EmailAddress.objects.create(user=user, email="pending@example.com")
    client.force_login(user)
    response = client.post(
        reverse("account-settings"),
        {"action_remove": "1", "email": pending.email},
    )
    assert response.status_code == 302
    assert not EmailAddress.objects.filter(pk=pending.pk).exists()
    current.refresh_from_db()
    assert current.primary and current.verified


@pytest.mark.django_db
def test_totp_setup_keeps_qr_code_and_native_activation_form(client, user):
    EmailAddress.objects.create(
        user=user, email=user.email, primary=True, verified=True
    )
    client.force_login(user)
    session = client.session
    session["account_authentication_methods"] = [
        {"method": "password", "at": time.time()}
    ]
    session.save()
    response = client.get(reverse("mfa_activate_totp"))
    assert response.status_code == 200
    assert response.context["totp_svg_data_uri"].startswith("data:image/svg+xml;")
    html = response.content.decode()
    assert 'name="code"' in html
    assert 'type="submit"' in html
    assert 'name="csrfmiddlewaretoken"' in html
    assert "designsystem/app.css" in html
