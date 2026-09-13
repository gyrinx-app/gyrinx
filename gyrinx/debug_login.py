"""Development-only agent users and one-click login support."""

import string

from allauth.account.models import EmailAddress
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction

AGENT_PASSWORD = "password"  # nosec B105 -- fixed DEBUG-only agent password
AGENT_USERNAME_ERROR = "Debug users must be named 'agent' or 'agent-<purpose>'"
AGENT_ACCOUNT_CONFLICT_ERROR = (
    "That username already belongs to an account not provisioned for debug agents"
)
DEBUG_AGENT_LOGIN_ERROR = "Invalid debug agent login"
_AGENT_PURPOSE_CHARACTERS = frozenset(string.ascii_lowercase + string.digits + "-")


def validate_agent_username(username):
    """Return a valid dedicated agent username or raise ``ValueError``."""
    User = get_user_model()
    username_field = User._meta.get_field(User.USERNAME_FIELD)
    max_length = username_field.max_length
    valid_purpose = (
        isinstance(username, str)
        and username.startswith("agent-")
        and len(username) > len("agent-")
        and not username.endswith("-")
        and "--" not in username
        and all(character in _AGENT_PURPOSE_CHARACTERS for character in username[6:])
    )
    if (
        not isinstance(username, str)
        or (max_length is not None and len(username) > max_length)
        or (username != "agent" and not valid_purpose)
    ):
        raise ValueError(AGENT_USERNAME_ERROR)
    return username


def _is_provisioned_agent(user, email):
    return (
        user.email == email
        and user.is_active
        and user.is_staff
        and not user.is_superuser
        and user.check_password(AGENT_PASSWORD)
        and EmailAddress.objects.filter(
            user=user,
            email=email,
            verified=True,
            primary=True,
        ).exists()
    )


@transaction.atomic
def ensure_debug_agent_user(username="agent"):
    """Create a dedicated local agent user, or validate an existing one."""
    if not settings.DEBUG:
        raise RuntimeError("Debug agent users are only available with DEBUG enabled")

    username = validate_agent_username(username)
    email = f"{username}@localhost"
    User = get_user_model()
    user, created = User.objects.select_for_update().get_or_create(
        username=username,
        defaults={
            "email": email,
            "is_active": True,
            "is_staff": True,
            "is_superuser": False,
        },
    )

    if not created:
        if not _is_provisioned_agent(user, email):
            raise ValueError(AGENT_ACCOUNT_CONFLICT_ERROR)
        return user

    user.set_password(AGENT_PASSWORD)
    user.save(update_fields=["password"])
    EmailAddress.objects.create(
        user=user,
        email=email,
        verified=True,
        primary=True,
    )
    return user
