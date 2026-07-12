import pytest
from django.contrib.auth.models import User

from allauth.account.models import EmailAddress

from gyrinx.api.models import WebhookRequest
from gyrinx.api.patreon import process_patreon_webhook
from gyrinx.core.models.auth import PatreonStatus, UserProfile


def _make_payload(
    email,
    full_name,
    patron_status="active_patron",
    tier_title="Scummer",
    tier_id="24970978",
    member_id="b93783ad-ed02-4b9f-ba2d-e4f83f02b521",
):
    """Build a realistic Patreon webhook payload."""
    return {
        "data": {
            "id": member_id,
            "type": "member",
            "attributes": {
                "email": email,
                "full_name": full_name,
                "patron_status": patron_status,
            },
            "relationships": {
                "currently_entitled_tiers": {
                    "data": [{"id": tier_id, "type": "tier"}] if tier_id else [],
                },
            },
        },
        "included": [
            {
                "id": tier_id,
                "type": "tier",
                "attributes": {
                    "title": tier_title,
                },
            },
        ]
        if tier_id
        else [],
    }


@pytest.mark.django_db
def test_matches_user_by_email():
    user = User.objects.create_user(
        "patron1", email="patron@example.com", password="test"
    )  # nosec B106
    EmailAddress.objects.create(
        user=user, email="patron@example.com", verified=True, primary=True
    )

    payload = _make_payload("patron@example.com", "Test Patron")
    result = process_patreon_webhook(payload, "members:create")

    assert result["matched"] is True
    assert result["user"] == "patron1"

    profile = UserProfile.objects.get(user=user)
    assert profile.patreon_status == PatreonStatus.ACTIVE
    assert profile.patreon_tier == "Scummer"
    assert profile.patreon_email == "patron@example.com"
    assert profile.patreon_member_id == "b93783ad-ed02-4b9f-ba2d-e4f83f02b521"


@pytest.mark.django_db
def test_matches_case_insensitive():
    user = User.objects.create_user(
        "patron2", email="Patron@Example.COM", password="test"
    )  # nosec B106
    EmailAddress.objects.create(
        user=user, email="Patron@Example.COM", verified=True, primary=True
    )

    payload = _make_payload("patron@example.com", "Test Patron")
    result = process_patreon_webhook(payload, "members:create")

    assert result["matched"] is True
    assert result["user"] == "patron2"


@pytest.mark.django_db
def test_unverified_email_does_not_match():
    # A user whose email is set on the User row but never verified via a
    # allauth EmailAddress must NOT be matched — we require proven ownership.
    User.objects.create_user("patron3", email="fallback@example.com", password="test")  # nosec B106

    payload = _make_payload("fallback@example.com", "Test Patron")
    result = process_patreon_webhook(payload, "members:create")

    assert result["matched"] is False
    assert result["user"] is None


@pytest.mark.django_db
def test_unverified_email_address_does_not_match():
    # An EmailAddress that exists but is not verified must not match either.
    user = User.objects.create_user(
        "patron4", email="other@example.com", password="test"
    )  # nosec B106
    EmailAddress.objects.create(
        user=user, email="unverified@example.com", verified=False, primary=False
    )

    payload = _make_payload("unverified@example.com", "Test Patron")
    result = process_patreon_webhook(payload, "members:create")

    assert result["matched"] is False
    assert result["user"] is None


@pytest.mark.django_db
def test_no_match_returns_unmatched():
    payload = _make_payload("nobody@example.com", "Ghost Patron")
    result = process_patreon_webhook(payload, "members:create")

    assert result["matched"] is False
    assert result["user"] is None
    assert result["email"] == "nobody@example.com"


@pytest.mark.django_db
def test_delete_event_sets_former_and_clears_tier():
    user = User.objects.create_user(
        "patron4", email="leaving@example.com", password="test"
    )  # nosec B106
    EmailAddress.objects.create(
        user=user, email="leaving@example.com", verified=True, primary=True
    )

    # First create an active membership
    create_payload = _make_payload("leaving@example.com", "Leaving Patron")
    process_patreon_webhook(create_payload, "members:create")

    profile = UserProfile.objects.get(user=user)
    assert profile.patreon_status == PatreonStatus.ACTIVE
    assert profile.patreon_tier == "Scummer"

    # Now process the delete — note patron_status in payload is still "active_patron"
    delete_payload = _make_payload(
        "leaving@example.com", "Leaving Patron", patron_status="active_patron"
    )
    process_patreon_webhook(delete_payload, "members:delete")

    profile.refresh_from_db()
    assert profile.patreon_status == PatreonStatus.FORMER
    assert profile.patreon_tier == ""


@pytest.mark.django_db
def test_pledge_delete_also_sets_former():
    user = User.objects.create_user(
        "patron5", email="pledgegone@example.com", password="test"
    )  # nosec B106
    EmailAddress.objects.create(
        user=user, email="pledgegone@example.com", verified=True, primary=True
    )

    payload = _make_payload("pledgegone@example.com", "Pledge Gone")
    process_patreon_webhook(payload, "members:pledge:delete")

    profile = UserProfile.objects.get(user=user)
    assert profile.patreon_status == PatreonStatus.FORMER
    assert profile.patreon_tier == ""


@pytest.mark.django_db
def test_declined_patron_status():
    user = User.objects.create_user(
        "patron6", email="declined@example.com", password="test"
    )  # nosec B106
    EmailAddress.objects.create(
        user=user, email="declined@example.com", verified=True, primary=True
    )

    payload = _make_payload(
        "declined@example.com", "Declined Patron", patron_status="declined_patron"
    )
    process_patreon_webhook(payload, "members:update")

    profile = UserProfile.objects.get(user=user)
    assert profile.patreon_status == PatreonStatus.DECLINED


@pytest.mark.django_db
def test_missing_email_returns_unmatched():
    payload = {
        "data": {"id": "abc", "attributes": {}, "relationships": {}},
        "included": [],
    }
    result = process_patreon_webhook(payload, "members:create")

    assert result["matched"] is False
    assert result["email"] == ""


@pytest.mark.django_db
def test_no_tier_in_payload():
    user = User.objects.create_user(
        "patron7", email="notier@example.com", password="test"
    )  # nosec B106
    EmailAddress.objects.create(
        user=user, email="notier@example.com", verified=True, primary=True
    )

    payload = _make_payload(
        "notier@example.com", "No Tier", tier_id=None, tier_title=""
    )
    result = process_patreon_webhook(payload, "members:create")

    assert result["matched"] is True
    profile = UserProfile.objects.get(user=user)
    assert profile.patreon_tier == ""


@pytest.mark.django_db
def test_backfill_processes_in_chronological_order():
    """When backfilling, later webhooks should overwrite earlier ones."""
    user = User.objects.create_user(
        "patron8", email="backfill@example.com", password="test"
    )  # nosec B106
    EmailAddress.objects.create(
        user=user, email="backfill@example.com", verified=True, primary=True
    )

    # Store webhooks — create first, then delete
    WebhookRequest.objects.create(
        source="patreon",
        event="members:create",
        payload=_make_payload("backfill@example.com", "Backfill User"),
        signature="sig1",
    )
    WebhookRequest.objects.create(
        source="patreon",
        event="members:delete",
        payload=_make_payload("backfill@example.com", "Backfill User"),
        signature="sig2",
    )

    # Process in chronological order
    for wh in WebhookRequest.objects.filter(source="patreon").order_by("created"):
        process_patreon_webhook(wh.payload, wh.event)

    profile = UserProfile.objects.get(user=user)
    assert profile.patreon_status == PatreonStatus.FORMER
    assert profile.patreon_tier == ""


@pytest.mark.django_db
def test_updates_existing_profile():
    """If UserProfile already exists, it should be updated not duplicated."""
    user = User.objects.create_user(
        "patron9", email="existing@example.com", password="test"
    )  # nosec B106
    EmailAddress.objects.create(
        user=user, email="existing@example.com", verified=True, primary=True
    )
    UserProfile.objects.create(user=user)

    payload = _make_payload("existing@example.com", "Existing Profile")
    process_patreon_webhook(payload, "members:create")

    assert UserProfile.objects.filter(user=user).count() == 1
    profile = UserProfile.objects.get(user=user)
    assert profile.patreon_status == PatreonStatus.ACTIVE


def _make_multi_tier_payload(email, full_name, tiers, patron_status="active_patron"):
    """Build a payload entitled to several tiers. ``tiers`` is [(id, title), ...]."""
    return {
        "data": {
            "id": "multi-tier-member",
            "type": "member",
            "attributes": {
                "email": email,
                "full_name": full_name,
                "patron_status": patron_status,
            },
            "relationships": {
                "currently_entitled_tiers": {
                    "data": [{"id": tid, "type": "tier"} for tid, _ in tiers],
                },
            },
        },
        "included": [
            {"id": tid, "type": "tier", "attributes": {"title": title}}
            for tid, title in tiers
        ],
    }


@pytest.mark.django_db
def test_free_tier_only_yields_no_stored_tier():
    """The free $0 tier is never a supporter badge tier."""
    user = User.objects.create_user(
        "patron_free", email="free@example.com", password="test"
    )  # nosec B106
    EmailAddress.objects.create(
        user=user, email="free@example.com", verified=True, primary=True
    )

    payload = _make_payload(
        "free@example.com", "Free Member", tier_title="Free", tier_id="24970901"
    )
    process_patreon_webhook(payload, "members:create")

    profile = UserProfile.objects.get(user=user)
    assert profile.patreon_tier == ""


@pytest.mark.django_db
def test_highest_ranked_tier_wins_over_free():
    """A member entitled to Free + Scummer stores Scummer."""
    user = User.objects.create_user(
        "patron_multi", email="multi@example.com", password="test"
    )  # nosec B106
    EmailAddress.objects.create(
        user=user, email="multi@example.com", verified=True, primary=True
    )

    payload = _make_multi_tier_payload(
        "multi@example.com",
        "Multi Tier",
        tiers=[("24970901", "Free"), ("24970978", "Scummer")],
    )
    process_patreon_webhook(payload, "members:create")

    profile = UserProfile.objects.get(user=user)
    assert profile.patreon_tier == "Scummer"


@pytest.mark.django_db
def test_former_via_update_clears_stale_tier():
    """A member lapsing to former via members:update keeps no tier."""
    user = User.objects.create_user(
        "patron_lapse", email="lapse@example.com", password="test"
    )  # nosec B106
    EmailAddress.objects.create(
        user=user, email="lapse@example.com", verified=True, primary=True
    )

    # Active first.
    process_patreon_webhook(
        _make_payload("lapse@example.com", "Lapsing"), "members:create"
    )
    assert UserProfile.objects.get(user=user).patreon_tier == "Scummer"

    # Now former via a plain update, still carrying the Scummer tier in payload.
    process_patreon_webhook(
        _make_payload("lapse@example.com", "Lapsing", patron_status="former_patron"),
        "members:update",
    )
    profile = UserProfile.objects.get(user=user)
    assert profile.patreon_status == PatreonStatus.FORMER
    assert profile.patreon_tier == ""


@pytest.mark.django_db
def test_null_patron_status_yields_blank_status_and_tier():
    user = User.objects.create_user(
        "patron_null", email="null@example.com", password="test"
    )  # nosec B106
    EmailAddress.objects.create(
        user=user, email="null@example.com", verified=True, primary=True
    )

    payload = _make_payload("null@example.com", "Null Status")
    payload["data"]["attributes"]["patron_status"] = None

    process_patreon_webhook(payload, "members:create")

    profile = UserProfile.objects.get(user=user)
    assert profile.patreon_status == ""
    assert profile.patreon_tier == ""


@pytest.mark.django_db
def test_legacy_pledge_event_does_not_crash():
    """Legacy pledges:* events have a different shape; extract nothing, no error."""
    user = User.objects.create_user(
        "patron_pledge", email="pledge@example.com", password="test"
    )  # nosec B106
    EmailAddress.objects.create(
        user=user, email="pledge@example.com", verified=True, primary=True
    )

    payload = {
        "data": {
            "id": "221273431",
            "type": "pledge",
            "attributes": {
                "email": "pledge@example.com",
                "amount_cents": 300,
            },
            "relationships": {
                "patron": {"data": {"id": "u1", "type": "user"}},
                "reward": {"data": {"id": "r1", "type": "reward"}},
            },
        },
        "included": [],
    }
    result = process_patreon_webhook(payload, "pledges:create")

    assert result["matched"] is True
    profile = UserProfile.objects.get(user=user)
    assert profile.patreon_tier == ""
