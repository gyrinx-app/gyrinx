"""User profile and account views."""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from gyrinx.core.forms import UsernameChangeForm
from gyrinx.core.models.campaign import Campaign
from gyrinx.core.models.events import EventNoun, EventVerb, log_event
from gyrinx.core.models.list import List
from gyrinx.core.models.pack import CustomContentPack


def user(request, slug_or_id):
    """
    Display a user profile page.

    **Context**

    ``profile_user``
        The requested user object.
    ``is_own_profile``
        Whether the viewer is viewing their own profile.
    ``public_lists``
        Non-campaign-mode, non-archived lists visible to the viewer.
    ``campaign_gangs``
        Campaign-mode lists visible to the viewer.
    ``campaigns``
        Campaigns owned by the profile user, visible to the viewer.
    ``packs``
        Content packs owned by the profile user (only if user is in
        "Custom Content" group).
    ``show_packs``
        Whether the packs section should be shown.

    **Template**

    :template:`core/user.html`
    """
    User = get_user_model()
    slug_or_id = str(slug_or_id).lower()
    if slug_or_id.isnumeric():
        query = Q(id=slug_or_id)
    else:
        query = Q(username__iexact=slug_or_id)
    profile_user = get_object_or_404(User, query)

    is_own_profile = request.user.is_authenticated and request.user == profile_user

    # --- Public Lists (non-campaign, non-archived) ---
    public_lists_qs = (
        List.objects.filter(
            owner=profile_user, status=List.LIST_BUILDING, archived=False, public=True
        )
        .with_latest_actions()
        .select_related("content_house", "owner")
    )
    public_lists = public_lists_qs

    # --- Unlisted Lists (only visible to the owner) ---
    unlisted_lists = List.objects.none()
    if is_own_profile:
        unlisted_lists = (
            List.objects.filter(
                owner=profile_user,
                status=List.LIST_BUILDING,
                archived=False,
                public=False,
            )
            .with_latest_actions()
            .select_related("content_house", "owner")
        )

    # --- Campaign Gangs (campaign-mode lists) ---
    campaign_gangs_qs = List.objects.filter(
        owner=profile_user, status=List.CAMPAIGN_MODE, archived=False
    )
    if not is_own_profile:
        campaign_gangs_qs = campaign_gangs_qs.filter(public=True)
    campaign_gangs = campaign_gangs_qs.select_related(
        "content_house", "owner", "campaign"
    )

    # --- Campaigns owned by the user ---
    campaigns_qs = Campaign.objects.filter(owner=profile_user, archived=False)
    if not is_own_profile:
        campaigns_qs = campaigns_qs.filter(public=True)
    campaigns = campaigns_qs

    # --- Packs (only if profile user is in Custom Content group) ---
    show_packs = profile_user.groups.filter(name="Custom Content").exists()
    packs = CustomContentPack.objects.none()
    if show_packs:
        packs_qs = CustomContentPack.objects.filter(owner=profile_user, archived=False)
        if not is_own_profile:
            packs_qs = packs_qs.filter(listed=True)
        packs = packs_qs

    # Log the user profile view
    if request.user.is_authenticated:
        log_event(
            user=request.user,
            noun=EventNoun.USER,
            verb=EventVerb.VIEW,
            object=profile_user,
            request=request,
            viewed_user_id=str(profile_user.id),
            viewed_username=profile_user.username,
            public_lists_count=public_lists.count(),
        )

    return render(
        request,
        "core/user.html",
        {
            "profile_user": profile_user,
            "is_own_profile": is_own_profile,
            "public_lists": public_lists,
            "unlisted_lists": unlisted_lists,
            "campaign_gangs": campaign_gangs,
            "campaigns": campaigns,
            "packs": packs,
            "show_packs": show_packs,
        },
    )


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
                noun=EventNoun.USER,
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
            noun=EventNoun.USER,
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
