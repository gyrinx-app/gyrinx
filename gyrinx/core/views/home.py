"""Home and dashboard views."""

from django.contrib.auth.decorators import login_required
from django.contrib.postgres.search import SearchQuery, SearchVector
from django.db.models import Q
from django.shortcuts import render

from gyrinx.content.models import ContentHouse
from gyrinx.core.models.campaign import Campaign
from gyrinx.core.models.events import EventNoun, EventVerb, log_event
from gyrinx.core.models.list import List
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
    else:
        with span("fetch_user_dashboard_data"):
            # Check if user has ANY lists (for showing filter)
            has_any_lists = List.objects.filter(
                owner=request.user, status=List.LIST_BUILDING, archived=False
            ).exists()

            # Regular lists (not in campaigns) - show 5 most recent
            lists_queryset = (
                List.objects.filter(
                    owner=request.user, status=List.LIST_BUILDING, archived=False
                )
                .with_latest_actions()
                .select_related("content_house")
            )

            # Apply search filter for lists
            search_query = request.GET.get("q")
            if search_query:
                search_vector = SearchVector("name", "content_house__name")
                search_q = SearchQuery(search_query)
                lists_queryset = lists_queryset.annotate(search=search_vector).filter(
                    Q(search=search_q)
                    | Q(name__icontains=search_query)
                    | Q(content_house__name__icontains=search_query)
                )

            # Order by modified and limit to 5
            lists = lists_queryset.order_by("-modified")[:5]

            # Campaign gangs - user's lists that are in active campaigns, show 5 most recent
            campaign_gangs = (
                List.objects.filter(
                    owner=request.user,
                    status=List.CAMPAIGN_MODE,
                    archived=False,
                    campaign__status=Campaign.IN_PROGRESS,
                    campaign__archived=False,
                )
                .with_latest_actions()
                .select_related("campaign", "content_house")
                .order_by("-modified")[:5]
            )

            # Campaigns - where user is owner or has lists participating
            campaigns = (
                Campaign.objects.filter(
                    Q(archived=False)
                    & (
                        Q(owner=request.user)  # User is campaign admin
                        | Q(campaign_lists__owner=request.user)
                    )  # User has lists in the campaign
                )
                .distinct()
                .order_by("-created")
            )

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
            campaigns_count=campaigns.count() if campaigns else 0,
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
        },
    )


@login_required
def account_home(request):
    """
    Management page for the user's account.

    """
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
    )
