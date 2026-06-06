"""Home and dashboard views."""

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render

from gyrinx.core.utils import search_queryset

from gyrinx.content.models import ContentHouse
from gyrinx.core.models.battle import Battle
from gyrinx.core.models.campaign import Campaign
from gyrinx.core.models.events import EventNoun, EventVerb, log_event
from gyrinx.core.models.list import List, ListFighter
from gyrinx.core.models.pack import CustomContentPack
from gyrinx.tracing import span, traced


@traced("view_index")
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
        houses = ContentHouse.objects.none()
        has_any_lists = False
        search_query = None
        search_gangs_query = None
        search_campaigns_query = None
        pinned_lists = []
        pinned_gangs = []
        pinned_campaigns = []
    else:
        with span("fetch_user_dashboard_data"):
            # Check if user has ANY lists (for showing filter)
            has_any_lists = List.objects.filter(
                owner=request.user, status=List.LIST_BUILDING, archived=False
            ).exists()

            # Pinned items (private to the user) shown at the top of each column.
            # These can include other users' public lists/campaigns the user pinned.
            pinned_all_lists = list(
                request.user.pinned_lists.filter(archived=False)
                .with_latest_actions()
                .select_related("content_house", "campaign")
                .order_by("name")
            )
            pinned_lists = [
                lst for lst in pinned_all_lists if lst.status == List.LIST_BUILDING
            ]
            pinned_gangs = [
                lst for lst in pinned_all_lists if lst.status == List.CAMPAIGN_MODE
            ]
            pinned_campaigns = list(
                request.user.pinned_campaigns.filter(archived=False)
                .select_related("owner")
                .order_by("name")
            )
            pinned_list_ids = [lst.id for lst in pinned_all_lists]
            pinned_campaign_ids = [c.id for c in pinned_campaigns]

            # Regular lists (not in campaigns) - show 5 most recent
            lists_queryset = (
                List.objects.filter(
                    owner=request.user, status=List.LIST_BUILDING, archived=False
                )
                .exclude(id__in=pinned_list_ids)
                .with_latest_actions()
                .select_related("content_house")
            )

            # Apply search filter for lists
            search_query = request.GET.get("q")
            if search_query:
                lists_queryset = search_queryset(
                    lists_queryset,
                    search_query,
                    ["name", "content_house__name"],
                )

            # Order by modified and limit to 5
            lists = lists_queryset.order_by("-modified")[:5]

            # Campaign gangs - user's lists that are in active campaigns, show 5 most recent
            campaign_gangs_queryset = (
                List.objects.filter(
                    owner=request.user,
                    status=List.CAMPAIGN_MODE,
                    archived=False,
                    campaign__status=Campaign.IN_PROGRESS,
                    campaign__archived=False,
                )
                .exclude(id__in=pinned_list_ids)
                .with_latest_actions()
                .select_related("campaign", "content_house")
            )

            # Apply search filter for campaign gangs
            search_gangs_query = request.GET.get("q_gangs")
            if search_gangs_query:
                campaign_gangs_queryset = search_queryset(
                    campaign_gangs_queryset,
                    search_gangs_query,
                    ["name", "content_house__name", "campaign__name"],
                )

            campaign_gangs = campaign_gangs_queryset.order_by("-modified")[:5]

            # Campaigns - where user is owner or has lists participating
            campaigns_queryset = (
                Campaign.objects.filter(
                    Q(archived=False)
                    & (
                        Q(owner=request.user)  # User is campaign admin
                        | Q(campaign_lists__owner=request.user)
                    )  # User has lists in the campaign
                )
                .exclude(id__in=pinned_campaign_ids)
                .distinct()
            )

            # Apply search filter for campaigns
            search_campaigns_query = request.GET.get("q_campaigns")
            if search_campaigns_query:
                campaigns_queryset = search_queryset(
                    campaigns_queryset, search_campaigns_query, ["name"]
                )

            # Order by modified and limit to 5 (matches lists / campaign gangs)
            campaigns = campaigns_queryset.order_by("-modified")[:5]

    # Log the dashboard view
    if request.user.is_authenticated:
        log_event(
            user=request.user,
            noun=EventNoun.USER,
            verb=EventVerb.VIEW,
            request=request,
            page="dashboard",
            lists_count=len(lists) if lists else 0,
            campaign_gangs_count=len(campaign_gangs) if campaign_gangs else 0,
            campaigns_count=len(campaigns) if campaigns else 0,
        )

    # Derive houses from the user's actual lists so pack-defined
    # houses are included whenever a user has gangs using them.
    if request.user.is_authenticated:
        houses = (
            ContentHouse.objects.all_content()
            .filter(
                id__in=List.objects.filter(
                    owner=request.user, archived=False
                ).values_list("content_house_id", flat=True)
            )
            .order_by("name")
        )

    # Pick up to 3 random featured packs to showcase on the front page.
    featured_packs = (
        CustomContentPack.objects.filter(featured=True, listed=True, archived=False)
        .select_related("owner")
        .order_by("?")[:3]
    )

    return render(
        request,
        "core/index.html",
        {
            "lists": lists,
            "campaign_gangs": campaign_gangs,
            "campaigns": campaigns,
            "houses": houses,
            "has_any_lists": has_any_lists,
            "search_query": search_query,
            "search_gangs_query": search_gangs_query,
            "search_campaigns_query": search_campaigns_query,
            "featured_packs": featured_packs,
            "pinned_lists": pinned_lists,
            "pinned_gangs": pinned_gangs,
            "pinned_campaigns": pinned_campaigns,
        },
    )


@login_required
def account_home(request):
    """
    Management page for the user's account with stats dashboard.

    **Context**

    ``stats``
        Dictionary of user stats (lists, campaigns, fighters, etc.).
    ``show_packs``
        Whether the Content Packs stat should be shown.

    **Template**

    :template:`core/account_home.html`
    """
    user = request.user

    # Gather stats
    lists_count = List.objects.filter(
        owner=user, status=List.LIST_BUILDING, archived=False
    ).count()
    campaign_gangs_count = List.objects.filter(
        owner=user, status=List.CAMPAIGN_MODE, archived=False
    ).count()
    campaigns_count = Campaign.objects.filter(owner=user, archived=False).count()
    fighters_count = ListFighter.objects.filter(
        list__owner=user, list__archived=False, archived=False
    ).count()
    battles_count = Battle.objects.filter(campaign__owner=user).count()

    # Content Packs
    show_packs = True
    packs_count = CustomContentPack.objects.filter(owner=user, archived=False).count()

    stats = {
        "lists_count": lists_count,
        "campaign_gangs_count": campaign_gangs_count,
        "campaigns_count": campaigns_count,
        "fighters_count": fighters_count,
        "battles_count": battles_count,
        "packs_count": packs_count,
    }

    # Log the account home view
    log_event(
        user=request.user,
        noun=EventNoun.USER,
        verb=EventVerb.VIEW,
        request=request,
        page="account_home",
    )

    return render(
        request,
        "core/account_home.html",
        {
            "stats": stats,
            "show_packs": show_packs,
        },
    )
