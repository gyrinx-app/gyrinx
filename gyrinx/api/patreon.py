import logging

from allauth.account.models import EmailAddress

from gyrinx.accounts.models import PatreonStatus, UserProfile
from gyrinx.badges import rank_for_tier_title

logger = logging.getLogger(__name__)

DELETE_EVENTS = {"members:delete", "members:pledge:delete"}

PATREON_STATUS_MAP = {
    "active_patron": PatreonStatus.ACTIVE,
    "declined_patron": PatreonStatus.DECLINED,
    "former_patron": PatreonStatus.FORMER,
}


def _extract_tier_title(payload):
    """Resolve entitled tier IDs to the highest-ranked badge-eligible title.

    Free and unrecognised titles have rank zero and produce no badge title.
    """
    tiers_data = (
        payload.get("data", {})
        .get("relationships", {})
        .get("currently_entitled_tiers", {})
        .get("data", [])
    )
    if not tiers_data:
        return ""

    tier_ids = {
        t.get("id")
        for t in tiers_data
        if isinstance(t, dict) and t.get("type") == "tier" and t.get("id")
    }
    if not tier_ids:
        return ""

    best_title = ""
    best_rank = 0
    for item in payload.get("included", []):
        if (
            isinstance(item, dict)
            and item.get("type") == "tier"
            and item.get("id") in tier_ids
        ):
            title = item.get("attributes", {}).get("title", "")
            rank = rank_for_tier_title(title)
            if rank > best_rank:
                best_rank = rank
                best_title = title

    return best_title


def _find_user_by_email(email):
    """Find the account through a verified allauth email address.

    Do not fall back to User.email because an unverified address must not
    receive supporter status.
    """
    email_obj = EmailAddress.objects.filter(email__iexact=email, verified=True).first()
    if email_obj:
        return email_obj.user

    return None


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

    # Clear stale tier data on any inactive status, including ordinary membership updates.
    if status != PatreonStatus.ACTIVE:
        tier_title = ""

    user = _find_user_by_email(email)
    if not user:
        logger.info("Patreon webhook: no user match for member %s", member_id)
        return {"matched": False, "user": None, "email": email}

    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.patreon_status = status
    profile.patreon_tier = tier_title
    profile.patreon_member_id = member_id
    profile.patreon_email = email
    profile.save()

    logger.info(
        "Patreon webhook: matched member %s to user %s", member_id, user.username
    )
    return {"matched": True, "user": user.username, "email": email}
