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
from django.db.models.signals import post_save
from django.dispatch import receiver

from gyrinx.core.models.auth import UserProfile
from gyrinx.core.models.events import Event, EventField, EventNoun, EventVerb, log_event


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


@receiver(user_signed_up)
def create_user_profile_and_record_tos(request, user, **kwargs):
    """Create UserProfile and record ToS agreement when a new user signs up."""
    # Create the user profile if it doesn't exist
    profile, created = UserProfile.objects.get_or_create(user=user)

    # Record ToS agreement if the form data indicates agreement
    # The form data is available in the request POST data
    if request and hasattr(request, "POST") and request.POST.get("tos_agreement"):
        profile.record_tos_agreement()


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
        from_email=from_email_address.email if from_email_address else None,
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


@receiver(post_save, sender=Event)
def update_list_modified_on_event(sender, instance, created, **kwargs):
    """
    Update the list's modified timestamp when an event is created
    that references the list.

    This ensures that the "last edited" time shown in the UI reflects
    any changes to list-related objects, not just direct list updates.
    """
    if not created:
        # Only process newly created events
        return

    if type(instance) is not Event:
        # Only handle Event instances, not other types
        return

    if instance.verb is EventVerb.VIEW:
        # Skip view events, they don't modify the list
        return

    # Check if the event has a list_id in its context
    if not instance.context or "list_id" not in instance.context:
        return

    list_id = instance.context.get("list_id")
    if not list_id:
        return

    # Import here to avoid circular imports
    from gyrinx.core.models.list import List

    try:
        # Update the list's modified timestamp
        # Using update() to avoid triggering save signals and history
        List.objects.filter(id=list_id).update(modified=instance.created)
    except List.DoesNotExist:
        # List doesn't exist, nothing to do
        pass


@receiver(post_save, sender=Event)
def update_campaign_modified_on_event(sender, instance, created, **kwargs):
    """
    Update the campaign's modified timestamp when an event is created
    that references the campaign.

    This ensures that the "last edited" time shown in the UI reflects
    any changes to campaign-related objects, not just direct campaign updates.
    """
    if not created:
        # Only process newly created events
        return

    if type(instance) is not Event:
        # Only handle Event instances, not other types
        return

    if instance.verb is EventVerb.VIEW:
        # Skip view events, they don't modify the campaign
        return

    # Check if the event has a campaign_id in its context
    if not instance.context or "campaign_id" not in instance.context:
        return

    campaign_id = instance.context.get("campaign_id")
    if not campaign_id:
        return

    # Import here to avoid circular imports
    from gyrinx.core.models.campaign import Campaign

    try:
        # Update the campaign's modified timestamp
        # Using update() to avoid triggering save signals and history
        Campaign.objects.filter(id=campaign_id).update(modified=instance.created)
    except Campaign.DoesNotExist:
        # Campaign doesn't exist, nothing to do
        pass
