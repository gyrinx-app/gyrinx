"""
Signal handlers for logging events from third-party views.

This module captures authentication and user-related events from
django-allauth and other third-party packages that we don't control
directly.
"""

from allauth.account.signals import (
    email_added,
    email_changed,
    email_confirmation_sent,
    email_confirmed,
    email_removed,
    password_changed,
    password_reset,
    password_set,
    user_logged_in,
    user_signed_up,
)
from allauth.mfa.models import Authenticator
from allauth.mfa.signals import (
    authenticator_added,
    authenticator_removed,
    authenticator_reset,
)
from allauth.usersessions.signals import session_client_changed
from django.contrib.auth.signals import user_logged_out
from django.dispatch import receiver

from gyrinx.core.models.events import EventField, EventNoun, EventVerb, log_event


@receiver(user_logged_in)
def log_user_login(request, user, **kwargs):
    """Log when a user signs in via allauth."""
    log_event(
        user=user,
        noun=EventNoun.USER,
        verb=EventVerb.LOGIN,
        request=request,
        login_method=kwargs.get("sociallogin", {}).get("provider", "email"),
    )


@receiver(user_logged_out)
def log_user_logout(sender, request, user, **kwargs):
    """Log when a user logs out."""
    if user and user.is_authenticated:
        log_event(
            user=user,
            noun=EventNoun.USER,
            verb=EventVerb.LOGOUT,
            request=request,
        )


@receiver(user_signed_up)
def log_user_signup(request, user, **kwargs):
    """Log when a new user signs up via allauth."""
    log_event(
        user=user,
        noun=EventNoun.USER,
        verb=EventVerb.SIGNUP,
        request=request,
        sociallogin=bool(kwargs.get("sociallogin")),
    )


@receiver(email_confirmed)
def log_email_confirmed(request, email_address, **kwargs):
    """Log when a user confirms their email address."""
    log_event(
        user=email_address.user,
        noun=EventNoun.USER,
        verb=EventVerb.UPDATE,
        request=request,
        field=EventField.EMAIL,
        email=email_address.email,
        primary=email_address.primary,
    )


@receiver(email_confirmation_sent)
def log_email_confirmation_sent(request, confirmation, signup, **kwargs):
    """Log when an email confirmation is sent."""
    log_event(
        user=None,
        noun=EventNoun.USER,
        verb=EventVerb.CONFIRM,
        request=request,
        confirmation=confirmation,
        signup=signup,
    )


@receiver(password_set)
def log_password_set(request, user, **kwargs):
    """Log when a user sets their password for the first time."""
    log_event(
        user=user,
        noun=EventNoun.USER,
        verb=EventVerb.CREATE,
        request=request,
        field=EventField.PASSWORD,
    )


@receiver(password_changed)
def log_password_changed(request, user, **kwargs):
    """Log when a user changes their password."""
    log_event(
        user=user,
        noun=EventNoun.USER,
        verb=EventVerb.UPDATE,
        request=request,
        field=EventField.PASSWORD,
    )


@receiver(password_reset)
def log_password_reset(request, user, **kwargs):
    """Log when a user resets their password."""
    log_event(
        user=user,
        noun=EventNoun.USER,
        verb=EventVerb.RESET,
        request=request,
        field=EventField.PASSWORD,
    )


@receiver(email_changed)
def log_email_changed(request, user, from_email_address, to_email_address, **kwargs):
    """Log when a user changes their primary email address."""
    log_event(
        user=user,
        noun=EventNoun.USER,
        verb=EventVerb.UPDATE,
        request=request,
        field=EventField.EMAIL,
        from_email=from_email_address.email,
        to_email=to_email_address.email,
    )


@receiver(email_added)
def log_email_added(request, user, email_address, **kwargs):
    """Log when a user adds a new email address."""
    log_event(
        user=user,
        noun=EventNoun.USER,
        verb=EventVerb.ADD,
        request=request,
        field=EventField.EMAIL,
        email=email_address.email,
        primary=email_address.primary,
    )


@receiver(email_removed)
def log_email_removed(request, user, email_address, **kwargs):
    """Log when a user removes an email address."""
    log_event(
        user=user,
        noun=EventNoun.USER,
        verb=EventVerb.REMOVE,
        request=request,
        field=EventField.EMAIL,
        email=email_address.email,
    )


@receiver(authenticator_added)
def log_authenticator_added(request, user, authenticator: Authenticator.Type, **kwargs):
    """Log when a user adds a new authenticator for MFA."""
    log_event(
        user=user,
        noun=EventNoun.USER,
        verb=EventVerb.ADD,
        request=request,
        field=EventField.MFA,
        authenticator_type=str(authenticator.type)
        if hasattr(authenticator, "type")
        else None,
    )


@receiver(authenticator_removed)
def log_authenticator_removed(
    request, user, authenticator: Authenticator.Type, **kwargs
):
    """Log when a user removes an authenticator."""
    log_event(
        user=user,
        noun=EventNoun.USER,
        verb=EventVerb.REMOVE,
        request=request,
        field=EventField.MFA,
        authenticator_type=str(authenticator.type)
        if hasattr(authenticator, "type")
        else None,
    )


@receiver(authenticator_reset)
def log_authenticator_reset(request, user, **kwargs):
    """Log when a user resets their authenticators."""
    log_event(
        user=user,
        noun=EventNoun.USER,
        verb=EventVerb.RESET,
        request=request,
        field=EventField.MFA,
    )


@receiver(session_client_changed)
def log_session_client_changed(sender, request, from_session, to_session, **kwargs):
    """Log when a user changes their session client."""
    log_event(
        user=request.user,
        noun=EventNoun.USER,
        verb=EventVerb.UPDATE,
        request=request,
        field=EventField.SESSION,
        from_session=from_session,
        to_session=to_session,
    )
