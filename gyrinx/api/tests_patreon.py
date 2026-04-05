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
def test_falls_back_to_user_email():
    User.objects.create_user("patron3", email="fallback@example.com", password="test")  # nosec B106
    # No EmailAddress record — should fall back to User.email

    payload = _make_payload("fallback@example.com", "Test Patron")
    result = process_patreon_webhook(payload, "members:create")

    assert result["matched"] is True
    assert result["user"] == "patron3"


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
