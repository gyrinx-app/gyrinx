from itertools import zip_longest
from random import randint
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.postgres.search import SearchQuery, SearchVector
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from gyrinx.content.models import ContentHouse
from gyrinx.core.forms import UsernameChangeForm
from gyrinx.core.models.campaign import Campaign
from gyrinx.core.models.list import List

from .csrf import csrf_failure as csrf_failure
from .upload import tinymce_upload as tinymce_upload


def make_query_params_str(**kwargs) -> str:
    return urlencode(dict([(k, v) for k, v in kwargs.items() if v is not None]))


def index(request):
    """
    Display a list of the user's :model:`core.List` objects, campaign gangs, and campaigns.

    **Context**

    ``lists``
        A list of :model:`core.List` objects owned by the current user (list building mode).
    ``campaign_gangs``
        A list of :model:`core.List` objects owned by the current user that are in active campaigns.
    ``campaigns``
        A list of :model:`core.Campaign` objects where the user is either the owner or has lists participating.

    **Template**

    :template:`core/index.html`
    """
    if request.user.is_anonymous:
        lists = []
        campaign_gangs = []
        campaigns = []
    else:
        # Regular lists (not in campaigns) - show 5 most recent
        lists_queryset = List.objects.filter(
            owner=request.user, status=List.LIST_BUILDING, archived=False
        ).select_related("content_house")

        # Apply search filter for lists
        search_query = request.GET.get("q")
        if search_query:
            search_vector = SearchVector("name", "content_house__name")
            search_q = SearchQuery(search_query)
            lists_queryset = lists_queryset.annotate(search=search_vector).filter(
                search=search_q
            )

        # Order by modified and limit to 5
        lists = lists_queryset.order_by("-modified")[:5]

        # Campaign gangs - user's lists that are in active campaigns, show 5 most recent
        campaign_gangs = (
            List.objects.filter(
                owner=request.user,
                status=List.CAMPAIGN_MODE,
                campaign__status=Campaign.IN_PROGRESS,
            )
            .select_related("campaign", "content_house")
            .order_by("-modified")[:5]
        )

        # Campaigns - where user is owner or has lists participating
        campaigns = (
            Campaign.objects.filter(
                Q(owner=request.user)  # User is campaign admin
                | Q(
                    campaign_lists__owner=request.user
                )  # User has lists in the campaign
            )
            .distinct()
            .order_by("-created")
        )

    return render(
        request,
        "core/index.html",
        {
            "lists": lists,
            "campaign_gangs": campaign_gangs,
            "campaigns": campaigns,
            "houses": ContentHouse.objects.all().order_by("name"),
        },
    )


@login_required
def account_home(request):
    """
    Management page for the user's account.

    """
    return render(
        request,
        "core/account_home.html",
    )


@login_required
def dice(request):
    """
    Display dice roll results (regular, firepower, or injury rolls).
    Users can specify query parameters to control the number of each die type.

    **Query Parameters**

    ``m`` (str)
        Mode for the dice roll, e.g. 'd6' or 'd3'.
    ``d`` (list of int)
        Number of standard dice to roll.
    ``fp`` (list of int)
        Number of firepower dice to roll.
    ``i`` (list of int)
        Number of injury dice to roll.

    **Context**

    ``mode``
        The dice mode (e.g. 'd6', 'd3').
    ``groups``
        A list of dictionaries, each containing:
          - ``dice``: rolled results for standard dice.
          - ``firepower``: rolled results for firepower dice.
          - ``injury``: rolled results for injury dice.
          - ``dice_n``, ``firepower_n``, ``injury_n``: the counts used.

    **Template**

    :template:`core/dice.html`
    """
    mode = request.GET.get("m", "d6")
    d = [int(x) for x in request.GET.getlist("d")]
    fp = [int(x) for x in request.GET.getlist("fp")]
    i = [int(x) for x in request.GET.getlist("i")]
    mod = {
        "d3": 3,
    }.get(mode, 6)
    groups = [
        dict(
            dice=[randint(0, 5) % mod + 1 for _ in range(group[0])],
            firepower=[randint(1, 6) for _ in range(group[1])],
            injury=[randint(1, 6) for _ in range(group[2])],
            dice_n=group[0],
            firepower_n=group[1],
            injury_n=group[2],
        )
        for group in zip_longest(d, fp, i, fillvalue=0)
    ]
    return render(
        request,
        "core/dice.html",
        {
            "mode": mode,
            "groups": groups,
        },
    )


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
    public_lists = List.objects.filter(
        owner=user, public=True, status=List.LIST_BUILDING, archived=False
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
            form.save()
            messages.success(
                request,
                f"Your username has been successfully changed to {form.cleaned_data['new_username']}!",
            )
            return redirect("core:account_home")
    else:
        form = UsernameChangeForm(user=request.user)

    return render(
        request,
        "core/change_username.html",
        {
            "form": form,
            "can_change": can_change,
        },
    )
