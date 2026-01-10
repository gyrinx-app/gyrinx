"""User profile and account views."""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from gyrinx.core.forms import UsernameChangeForm
from gyrinx.core.models.events import EventNoun, EventVerb, log_event
from gyrinx.core.models.list import List


def user(request, slug_or_id):
    """
    Display a user profile page with public lists.

    **Context**

    ``user``
        The requested user object.

    **Template**

    :template:`core/user.html`
    """
    User = get_user_model()
    slug_or_id = str(slug_or_id).lower()
    if slug_or_id.isnumeric():
        query = Q(id=slug_or_id)
    else:
        query = Q(username__iexact=slug_or_id)
    user = get_object_or_404(User, query)
    public_lists = (
        List.objects.filter(
            owner=user, public=True, status=List.LIST_BUILDING, archived=False
        )
        .with_latest_actions()
        .select_related("content_house", "owner")
    )

    # Log the user profile view
    if request.user.is_authenticated:
        log_event(
            user=request.user,
            noun=EventNoun.USER,
            verb=EventVerb.VIEW,
            object=user,
            request=request,
            viewed_user_id=str(user.id),
            viewed_username=user.username,
            public_lists_count=public_lists.count(),
        )

    return render(
        request,
        "core/user.html",
        {"user": user, "public_lists": public_lists},
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
