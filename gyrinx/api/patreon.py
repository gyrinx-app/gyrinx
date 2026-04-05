import logging

from allauth.account.models import EmailAddress
from django.contrib.auth.models import User

from gyrinx.core.models.auth import PatreonStatus, UserProfile

logger = logging.getLogger(__name__)

DELETE_EVENTS = {"members:delete", "pledge:delete"}

PATREON_STATUS_MAP = {
    "active_patron": PatreonStatus.ACTIVE,
    "declined_patron": PatreonStatus.DECLINED,
    "former_patron": PatreonStatus.FORMER,
}


def _extract_tier_title(payload):
    """Extract the tier title from the webhook payload by joining tier IDs to included data."""
    tiers_data = (
        payload.get("data", {})
        .get("relationships", {})
        .get("currently_entitled_tiers", {})
        .get("data", [])
    )
    if not tiers_data:
        return ""

    tier_ids = {t["id"] for t in tiers_data if t.get("type") == "tier"}
    if not tier_ids:
        return ""

    for item in payload.get("included", []):
        if item.get("type") == "tier" and item.get("id") in tier_ids:
            return item.get("attributes", {}).get("title", "")

    return ""


def _find_user_by_email(email):
    """Match an email to a Django user, checking allauth EmailAddress first."""
    email_obj = EmailAddress.objects.filter(email__iexact=email, verified=True).first()
    if email_obj:
        return email_obj.user

    return User.objects.filter(email__iexact=email).first()


def process_patreon_webhook(payload, event):
    """
    Process a Patreon webhook payload and update the matched user's profile.

    Returns a dict with 'matched' (bool), 'user' (username or None), and 'email'.
    """
    data = payload.get("data", {})
    attributes = data.get("attributes", {})

    email = attributes.get("email", "")
    if not email:
        logger.warning("Patreon webhook missing email")
        return {"matched": False, "user": None, "email": ""}

    member_id = data.get("id", "")
    patreon_status_raw = attributes.get("patron_status", "")
    tier_title = _extract_tier_title(payload)

    is_delete = event in DELETE_EVENTS

    if is_delete:
        status = PatreonStatus.FORMER
        tier_title = ""
    else:
        status = PATREON_STATUS_MAP.get(patreon_status_raw, "")

    user = _find_user_by_email(email)
    if not user:
        logger.info("Patreon webhook: no user match for %s", email)
        return {"matched": False, "user": None, "email": email}

    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.patreon_status = status
    profile.patreon_tier = tier_title
    profile.patreon_member_id = member_id
    profile.patreon_email = email
    profile.save()

    logger.info("Patreon webhook: matched %s to user %s", email, user.username)
    return {"matched": True, "user": user.username, "email": email}
