"""User profile and account views."""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from gyrinx.account_forms import (
    BadgeSelectionForm,
    TimezoneForm,
    UsernameChangeForm,
)
from gyrinx.accounts.models import UserProfile
from gyrinx.accounts.public_profiles import profile_person, profile_redirect
from gyrinx.analytics.models import EventVerb, log_event
from gyrinx.analytics.nouns import PlatformNoun
from gyrinx.badges import HIDE_BADGE


def user(request, slug_or_id):
    """Redirect legacy account names and numeric IDs to the shared profile."""
    if str(slug_or_id).isnumeric():
        person = get_object_or_404(get_user_model(), pk=slug_or_id, is_active=True)
    else:
        person = profile_person(slug_or_id)
    return profile_redirect(request, person)


@login_required
def change_username(request):
    """
    Allow users with '@' in their username to change it.

    **Context**

    ``form``
        The username change form.
    ``can_change``
        Whether the current user is eligible to change their username.

    **Template**

    :template:`core/change_username.html`
    """
    # Check if user is eligible to change username (has @ in username)
    can_change = "@" in request.user.username

    if not can_change:
        messages.error(request, "You are not eligible to change your username.")
        return redirect("core:account_home")

    if request.method == "POST":
        form = UsernameChangeForm(request.POST, user=request.user)
        if form.is_valid():
            old_username = request.user.username
            new_username = form.cleaned_data["new_username"]
            form.save()

            # Log the username change
            log_event(
                user=request.user,
                noun=PlatformNoun.USER,
                verb=EventVerb.UPDATE,
                request=request,
                field="username",
                old_username=old_username,
                new_username=new_username,
            )

            messages.success(
                request,
                f"Your username has been successfully changed to {new_username}!",
            )
            return redirect("core:account_home")
    else:
        # Log viewing the username change form
        log_event(
            user=request.user,
            noun=PlatformNoun.USER,
            verb=EventVerb.VIEW,
            request=request,
            page="change_username",
        )
        form = UsernameChangeForm(user=request.user)

    return render(
        request,
        "core/change_username.html",
        {
            "form": form,
            "can_change": can_change,
        },
    )


@login_required
def badge_settings(request):
    """
    Let the user choose which badge to display next to their name.

    Only badges the user can currently display (from their live Patreon status
    and staff access) are offered, plus an explicit "no badge" option. Users with
    no badges see an empty state explaining how to unlock them.

    **Context**

    ``form``
        The badge selection form.
    ``available_badges``
        The badges currently available to the user.

    **Template**

    :template:`core/badge_settings.html`
    """
    if request.method == "GET":
        return redirect("account-settings")
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    if request.method == "POST":
        form = BadgeSelectionForm(request.POST, user=request.user)
        if form.is_valid():
            form.save()
            log_event(
                user=request.user,
                noun=PlatformNoun.USER,
                verb=EventVerb.UPDATE,
                request=request,
                field="selected_badge",
                selected_badge=form.cleaned_data["selected_badge"],
            )
            messages.success(request, "Your badge has been updated.")
            return redirect("core:account_home")
    else:
        log_event(
            user=request.user,
            noun=PlatformNoun.USER,
            verb=EventVerb.VIEW,
            request=request,
            page="badge_settings",
        )
        form = BadgeSelectionForm(user=request.user)

    return render(
        request,
        "core/badge_settings.html",
        {
            "form": form,
            "available_badges": profile.available_badges,
            "hide_badge_value": HIDE_BADGE,
        },
    )


@login_required
def timezone_settings(request):
    """
    Let the user choose which timezone timestamps are shown in.

    **Context**

    ``form``
        The timezone selection form.

    **Template**

    :template:`core/timezone_settings.html`
    """
    if request.method == "GET":
        return redirect("account-settings")
    UserProfile.objects.get_or_create(user=request.user)

    if request.method == "POST":
        form = TimezoneForm(request.POST, user=request.user, request=request)
        if form.is_valid():
            form.save()
            log_event(
                user=request.user,
                noun=PlatformNoun.USER,
                verb=EventVerb.UPDATE,
                request=request,
                field="timezone",
                timezone=form.cleaned_data["timezone"],
            )
            messages.success(request, "Your timezone has been updated.")
            return redirect("core:account_home")
    else:
        log_event(
            user=request.user,
            noun=PlatformNoun.USER,
            verb=EventVerb.VIEW,
            request=request,
            page="timezone_settings",
        )
        form = TimezoneForm(user=request.user, request=request)

    return render(
        request,
        "core/timezone_settings.html",
        {
            "form": form,
        },
    )
