"""
Signal handlers for logging events from third-party views.

This module captures authentication and user-related events from
django-allauth and other third-party packages that we don't control
directly.
"""

from allauth.account.signals import email_confirmed, user_logged_in, user_signed_up
from django.contrib.auth.signals import user_logged_out
from django.dispatch import receiver

from gyrinx.core.models.events import EventNoun, EventVerb, log_event


@receiver(user_logged_in)
def log_user_login(request, user, **kwargs):
    """Log when a user signs in via allauth."""
    log_event(
        user=user,
        noun=EventNoun.USER,
        verb=EventVerb.VIEW,
        request=request,
        action="login",
        login_method=kwargs.get("sociallogin", {}).get("provider", "email"),
    )


@receiver(user_logged_out)
def log_user_logout(sender, request, user, **kwargs):
    """Log when a user logs out."""
    if user and user.is_authenticated:
        log_event(
            user=user,
            noun=EventNoun.USER,
            verb=EventVerb.VIEW,
            request=request,
            action="logout",
        )


@receiver(user_signed_up)
def log_user_signup(request, user, **kwargs):
    """Log when a new user signs up via allauth."""
    log_event(
        user=user,
        noun=EventNoun.USER,
        verb=EventVerb.CREATE,
        request=request,
        action="signup",
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
        action="email_confirmed",
        email=email_address.email,
        primary=email_address.primary,
    )
