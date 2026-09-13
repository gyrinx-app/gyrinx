"""Development-only agent users and one-click login support."""

import re

from allauth.account.models import EmailAddress
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction

AGENT_PASSWORD = "password"  # nosec B105 -- fixed DEBUG-only agent password
AGENT_USERNAME_PATTERN = re.compile(r"agent(?:-[a-z0-9]+(?:-[a-z0-9]+)*)?\Z")


def validate_agent_username(username):
    """Return a valid dedicated agent username or raise ``ValueError``."""
    if not AGENT_USERNAME_PATTERN.fullmatch(username):
        raise ValueError("Debug users must be named 'agent' or 'agent-<purpose>'")
    return username


@transaction.atomic
def ensure_debug_agent_user(username="agent"):
    """Create or repair a dedicated local agent user under DEBUG."""
    if not settings.DEBUG:
        raise RuntimeError("Debug agent users are only available with DEBUG enabled")

    username = validate_agent_username(username)
    email = f"{username}@localhost"
    User = get_user_model()
    user, _ = User.objects.get_or_create(username=username)

    user.email = email
    user.is_active = True
    user.is_staff = True
    user.is_superuser = False
    update_fields = ["email", "is_active", "is_staff", "is_superuser"]
    if not user.check_password(AGENT_PASSWORD):
        user.set_password(AGENT_PASSWORD)
        update_fields.append("password")
    user.save(update_fields=update_fields)

    EmailAddress.objects.filter(user=user).exclude(email=email).update(primary=False)
    EmailAddress.objects.update_or_create(
        user=user,
        email=email,
        defaults={"verified": True, "primary": True},
    )
    return user
