"""The Django admin must authenticate through allauth, second factor included.

See gyrinx/admin_site.py — Django's own admin login form takes a username and
password and nothing else, which would let a staff account with TOTP configured
into the admin without ever being challenged.
"""

from urllib.parse import unquote

import pytest
from allauth.account.models import EmailAddress
from allauth.mfa.totp.internal import auth as totp_auth
from django.test import Client, override_settings
from django.urls import reverse

ADMIN_INDEX = "/admin/"
ADMIN_LOGIN = "/admin/login/"
ALLAUTH_LOGIN = "/accounts/login/"
MFA_ACTIVATE = "/accounts/2fa/totp/activate/"
MFA_AUTHENTICATE = "/accounts/2fa/authenticate/"
MFA_REAUTHENTICATE = "/accounts/2fa/reauthenticate/"
ACCOUNT_REAUTHENTICATE = "/accounts/reauthenticate/"


@pytest.fixture
def staff_user(make_user):
    user = make_user("staffer", "password")
    user.is_staff = True
    user.is_superuser = True
    user.email = "staffer@example.com"
    user.save()
    EmailAddress.objects.create(
        user=user, email=user.email, verified=True, primary=True
    )
    return user


def enable_totp(user):
    """Give ``user`` a TOTP authenticator and return its secret."""
    secret = totp_auth.generate_totp_secret()
    totp_auth.TOTP.activate(user, secret)
    return secret


def totp_code(secret):
    counter = next(totp_auth.yield_hotp_counters_from_time())
    return totp_auth.format_hotp_value(totp_auth.hotp_value(secret, counter))


@pytest.fixture
def pass_captcha(monkeypatch):
    """The project's allauth login form carries a reCAPTCHA field."""
    monkeypatch.setattr(
        "django_recaptcha.fields.ReCaptchaField.validate", lambda self, value: True
    )


# ------------------------------------------------------- the form is gone


@pytest.mark.django_db
def test_admin_login_redirects_anonymous_users_to_allauth():
    response = Client().get(ADMIN_LOGIN)

    assert response.status_code == 302
    assert response.url == f"{ALLAUTH_LOGIN}?next={ADMIN_INDEX}"


@pytest.mark.django_db
def test_admin_login_does_not_render_a_login_form():
    response = Client().get(ADMIN_LOGIN, follow=True)

    # We land on allauth's login page, not the admin's.
    assert response.redirect_chain[-1][0].startswith(ALLAUTH_LOGIN)
    assert b"id_username" not in response.content


@pytest.mark.django_db
def test_admin_login_form_cannot_be_used_to_authenticate(staff_user):
    """Posting credentials at the admin login URL must not create a session."""
    client = Client()

    response = client.post(ADMIN_LOGIN, {"username": "staffer", "password": "password"})

    assert response.status_code == 302
    assert response.url.startswith(ALLAUTH_LOGIN)
    assert "_auth_user_id" not in client.session
    assert client.get(ADMIN_INDEX).status_code == 302


@pytest.mark.django_db
def test_admin_preserves_the_requested_page_as_next(staff_user):
    response = Client().get("/admin/auth/user/")

    # admin_view bounces to the admin login, which bounces on to allauth.
    assert response.status_code == 302
    assert response.url == f"{ADMIN_LOGIN}?next=/admin/auth/user/"

    response = Client().get(response.url)
    assert response.url == f"{ALLAUTH_LOGIN}?next=/admin/auth/user/"


@pytest.mark.django_db
def test_next_pointing_back_at_the_admin_login_falls_back_to_the_index():
    response = Client().get(f"{ADMIN_LOGIN}?next={ADMIN_LOGIN}")

    assert response.url == f"{ALLAUTH_LOGIN}?next={ADMIN_INDEX}"


@pytest.mark.django_db
def test_offsite_next_is_rejected():
    response = Client().get(f"{ADMIN_LOGIN}?next=https://evil.example.com/")

    assert response.url == f"{ALLAUTH_LOGIN}?next={ADMIN_INDEX}"


@pytest.mark.django_db
def test_logged_in_non_staff_user_is_forbidden(user):
    client = Client()
    client.force_login(user)

    assert client.get(ADMIN_LOGIN).status_code == 403


# ------------------------------------------------------- the 2FA gate


@override_settings(ADMIN_REQUIRE_MFA=True)
@pytest.mark.django_db
def test_staff_without_a_second_factor_is_sent_to_totp_setup(staff_user):
    client = Client()
    client.force_login(staff_user)

    response = client.get(ADMIN_INDEX)
    assert response.status_code == 302
    assert response.url == f"{ADMIN_LOGIN}?next={ADMIN_INDEX}"

    response = client.get(response.url)
    assert response.url == f"{MFA_ACTIVATE}?next={ADMIN_INDEX}"


@override_settings(ADMIN_REQUIRE_MFA=True)
@pytest.mark.django_db
def test_session_that_never_passed_a_challenge_is_sent_to_reauthenticate(staff_user):
    """A session predating the TOTP setup has not actually shown a code."""
    enable_totp(staff_user)
    client = Client()
    client.force_login(staff_user)

    response = client.get(ADMIN_LOGIN)

    assert response.url == f"{MFA_REAUTHENTICATE}?next={ADMIN_INDEX}"


@override_settings(ADMIN_REQUIRE_MFA=True)
@pytest.mark.django_db
def test_passing_the_challenge_opens_the_admin(staff_user):
    secret = enable_totp(staff_user)
    client = Client()
    client.force_login(staff_user)

    assert client.get(ADMIN_INDEX).status_code == 302

    response = client.post(
        f"{MFA_REAUTHENTICATE}?next={ADMIN_INDEX}",
        {"code": totp_code(secret)},
        follow=True,
    )

    assert response.status_code == 200
    assert response.redirect_chain[-1][0] == ADMIN_INDEX


@override_settings(ADMIN_REQUIRE_MFA=True)
@pytest.mark.django_db
def test_a_wrong_code_does_not_open_the_admin(staff_user):
    enable_totp(staff_user)
    client = Client()
    client.force_login(staff_user)

    client.post(f"{MFA_REAUTHENTICATE}?next={ADMIN_INDEX}", {"code": "000000"})

    assert client.get(ADMIN_INDEX).status_code == 302


@override_settings(ADMIN_REQUIRE_MFA=False)
@pytest.mark.django_db
def test_gate_can_be_switched_off_for_local_development(staff_user):
    client = Client()
    client.force_login(staff_user)

    assert client.get(ADMIN_INDEX).status_code == 200


# ------------------------------------------------------- end to end


@override_settings(ADMIN_REQUIRE_MFA=True)
@pytest.mark.django_db
def test_signing_in_for_the_admin_goes_through_the_full_allauth_flow(
    staff_user, pass_captcha
):
    secret = enable_totp(staff_user)
    client = Client()

    # Start at the admin, get pushed out to allauth.
    response = client.get(ADMIN_INDEX, follow=True)
    assert response.redirect_chain[-1][0] == f"{ALLAUTH_LOGIN}?next={ADMIN_INDEX}"

    # A correct username and password is not enough on its own.
    response = client.post(
        f"{ALLAUTH_LOGIN}?next={ADMIN_INDEX}",
        {"login": "staffer", "password": "password", "captcha": "dummy"},
    )
    assert response.status_code == 302
    assert response.url.startswith(MFA_AUTHENTICATE)
    assert client.get(ADMIN_INDEX).status_code == 302

    # The second factor completes the login and lands us in the admin.
    response = client.post(response.url, {"code": totp_code(secret)}, follow=True)
    assert response.status_code == 200
    assert response.redirect_chain[-1][0] == ADMIN_INDEX


@pytest.mark.django_db
def test_admin_index_is_reachable_once_authenticated(staff_user):
    """Sanity check that the replacement site still serves the admin itself."""
    client = Client()
    client.force_login(staff_user)

    with override_settings(ADMIN_REQUIRE_MFA=False):
        response = client.get(ADMIN_INDEX)

    assert response.status_code == 200
    assert reverse("admin:index") == ADMIN_INDEX


# ------------------------------------------------------- admindocs


@override_settings(ADMIN_REQUIRE_MFA=True)
@pytest.mark.django_db
def test_admindocs_is_behind_the_same_gate(staff_user):
    """admindocs' own staff_member_required knows nothing about the 2FA gate."""
    client = Client()
    client.force_login(staff_user)

    response = client.get("/admin/doc/")

    assert response.status_code == 302
    assert response.url == f"{ADMIN_LOGIN}?next=/admin/doc/"


@override_settings(ADMIN_REQUIRE_MFA=False)
@pytest.mark.django_db
def test_admindocs_is_reachable_when_the_gate_is_satisfied(staff_user):
    client = Client()
    client.force_login(staff_user)

    assert client.get("/admin/doc/").status_code == 200


@pytest.mark.django_db
def test_admindocs_url_names_are_unchanged():
    assert reverse("django-admindocs-docroot") == "/admin/doc/"


# ------------------------------------------------------- password is not a second factor


@override_settings(ADMIN_REQUIRE_MFA=True)
@pytest.mark.django_db
def test_password_reauthentication_does_not_open_the_admin(staff_user):
    """A password is what the session already has — it proves nothing new."""
    enable_totp(staff_user)
    client = Client()
    client.force_login(staff_user)

    response = client.post(
        f"{ACCOUNT_REAUTHENTICATE}?next={ADMIN_INDEX}", {"password": "password"}
    )
    assert response.status_code == 302

    response = client.get(ADMIN_INDEX, follow=True)
    assert response.redirect_chain[-1][0] == f"{MFA_REAUTHENTICATE}?next={ADMIN_INDEX}"


@override_settings(ADMIN_REQUIRE_MFA=True)
@pytest.mark.django_db
def test_the_challenge_page_does_not_offer_a_password_alternative(staff_user):
    enable_totp(staff_user)
    client = Client()
    client.force_login(staff_user)

    response = client.get(f"{MFA_REAUTHENTICATE}?next={ADMIN_INDEX}")

    alternatives = response.context["reauthentication_alternatives"]
    assert [alt["id"] for alt in alternatives] == []


@override_settings(ADMIN_REQUIRE_MFA=True)
@pytest.mark.django_db
def test_going_to_password_reauthentication_by_hand_is_steered_to_the_code(staff_user):
    enable_totp(staff_user)
    client = Client()
    client.force_login(staff_user)

    response = client.get(f"{ACCOUNT_REAUTHENTICATE}?next={ADMIN_INDEX}")

    assert response.status_code == 302
    assert response.url.startswith(MFA_REAUTHENTICATE)
    assert ADMIN_INDEX in unquote(response.url)


@override_settings(ADMIN_REQUIRE_MFA=True)
@pytest.mark.django_db
def test_password_reauthentication_still_works_away_from_the_admin(user):
    """Ordinary account flows keep the password option."""
    EmailAddress.objects.create(
        user=user, email="testuser@example.com", verified=True, primary=True
    )
    enable_totp(user)
    client = Client()
    client.force_login(user)

    response = client.get(f"{ACCOUNT_REAUTHENTICATE}?next=/account/")

    assert response.status_code == 200


# ------------------------------------------------------- the DEBUG default


@override_settings(ADMIN_REQUIRE_MFA=None, DEBUG=True)
@pytest.mark.django_db
def test_the_gate_is_off_in_debug_by_default(staff_user):
    """Local worktrees each have their own database — one TOTP each is a faff."""
    client = Client()
    client.force_login(staff_user)

    assert client.get(ADMIN_INDEX).status_code == 200


@override_settings(ADMIN_REQUIRE_MFA=None, DEBUG=False)
@pytest.mark.django_db
def test_the_gate_is_on_outside_debug_by_default(staff_user):
    client = Client()
    client.force_login(staff_user)

    assert client.get(ADMIN_INDEX).status_code == 302


@override_settings(ADMIN_REQUIRE_MFA=True, DEBUG=True)
@pytest.mark.django_db
def test_the_gate_can_still_be_forced_on_in_debug(staff_user):
    """So the production behaviour can be exercised locally."""
    client = Client()
    client.force_login(staff_user)

    assert client.get(ADMIN_INDEX).status_code == 302


@override_settings(ADMIN_REQUIRE_MFA=None, DEBUG=True)
@pytest.mark.django_db
def test_admin_login_still_goes_through_allauth_in_debug():
    """DEBUG relaxes the second factor, never the login path."""
    response = Client().get(ADMIN_LOGIN)

    assert response.url == f"{ALLAUTH_LOGIN}?next={ADMIN_INDEX}"
