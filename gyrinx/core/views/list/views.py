"""List CRUD views."""

from django.contrib.auth.decorators import login_required
from django.contrib.postgres.search import SearchQuery, SearchVector
from django.core.cache import cache
from django.db import transaction
from django.db.models import Q
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views import generic

from gyrinx import messages
from gyrinx.content.models import ContentFighter, ContentHouse
from gyrinx.core.context_processors import BANNER_CACHE_KEY
from gyrinx.core.forms.list import CloneListForm, EditListForm, NewListForm
from gyrinx.core.handlers.list import handle_list_clone, handle_list_creation
from gyrinx.core.models.list import List, ListFighter
from gyrinx.core.models.events import EventNoun, EventVerb, log_event
from gyrinx.core.utils import (
    build_safe_url,
    get_list_attributes,
    get_list_campaign_resources,
    get_list_held_assets,
    get_list_recent_campaign_actions,
    safe_redirect,
)
from gyrinx.core.views.list.common import get_clean_list_or_404
from gyrinx.models import is_valid_uuid
from gyrinx.tracing import traced
from gyrinx.tracker import track


class ListsListView(generic.ListView):
    """
    Display a list of public :model:`core.List` objects.

    **Context**

    ``lists``
        A list of :model:`core.List` objects where `public=True`.
    ``houses``
        A list of :model:`content.ContentHouse` objects for filtering.

    **Template**

    :template:`core/lists.html`
    """

    template_name = "core/lists.html"
    context_object_name = "lists"
    paginate_by = 20
    page_kwarg = "page"

    @traced("ListsListView_get_queryset")
    def get_queryset(self):
        """
        Return :model:`core.List` objects that are public and in list building mode.
        Campaign mode lists are only visible within their campaigns.
        Archived lists are excluded from this view unless requested.
        """
        queryset = (
            List.objects.all()
            .with_latest_actions()
            .select_related("content_house", "owner", "campaign")
        )

        # Apply "Your Lists" filter (default on if user is authenticated)
        show_my_lists = self.request.GET.get(
            "my", "1" if self.request.user.is_authenticated else "0"
        )
        if show_my_lists == "1" and self.request.user.is_authenticated:
            queryset = queryset.filter(owner=self.request.user)
        else:
            # Only show public lists if not filtering by user
            queryset = queryset.filter(public=True)

        # Apply archived filter (default off)
        show_archived = self.request.GET.get("archived", "0")
        if show_archived == "1":
            # Show ONLY archived lists that belong to the current user
            if self.request.user.is_authenticated:
                queryset = queryset.filter(archived=True, owner=self.request.user)
            else:
                # Non-authenticated users cannot see archived lists
                queryset = queryset.none()
        else:
            # Show only non-archived lists by default
            queryset = queryset.filter(archived=False)

        # Apply type filter (lists vs gangs)
        type_filters = self.request.GET.getlist("type")
        if type_filters:
            status_filters = []
            if "list" in type_filters:
                status_filters.append(List.LIST_BUILDING)
            if "gang" in type_filters:
                status_filters.append(List.CAMPAIGN_MODE)
            if status_filters:
                queryset = queryset.filter(status__in=status_filters)
        else:
            # Default to showing all
            pass

        # Apply search filter
        search_query = self.request.GET.get("q")
        if search_query:
            search_vector = SearchVector(
                "name", "content_house__name", "owner__username"
            )
            search_q = SearchQuery(search_query)
            queryset = queryset.annotate(search=search_vector).filter(
                Q(search=search_q)
                | Q(name__icontains=search_query)
                | Q(content_house__name__icontains=search_query)
            )

        # Apply house filter
        house_ids = self.request.GET.getlist("house")
        if house_ids and not ("all" in house_ids or not house_ids[0]):
            # Validate UUIDs to prevent SQL injection attempts
            valid_house_ids = [h_id for h_id in house_ids if is_valid_uuid(h_id)]
            if valid_house_ids:
                queryset = queryset.filter(content_house_id__in=valid_house_ids)

        return queryset

    @traced("ListsListView_get_context_data")
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["houses"] = ContentHouse.objects.all().order_by("name")
        return context

    @traced("ListsListView_get")
    def get(self, request, *args, **kwargs):
        """
        Override get to handle pagination errors.
        If the requested page is out of bounds, redirect to page 1
        with all other query parameters preserved.
        """
        try:
            return super().get(request, *args, **kwargs)
        except Http404:
            # Check if this is a pagination-related 404
            page = request.GET.get(self.page_kwarg, 1)
            # If page is not 1, it's likely a pagination error
            if page != "1":
                # Build new query parameters with page=1
                query_params = request.GET.copy()
                query_params[self.page_kwarg] = "1"
                # Build safe URL for redirect
                url = build_safe_url(
                    request,
                    path=request.path,
                    query_string=query_params.urlencode(),
                )
                # Redirect to the same URL with page=1
                return safe_redirect(request, url, fallback_url=reverse("core:lists"))
            # If it's already page 1, re-raise the 404
            raise


class ListDetailView(generic.DetailView):
    """
    Display a single :model:`core.List` object.

    **Context**

    ``list``
        The requested :model:`core.List` object.
    ``recent_actions``
        Recent campaign actions related to this list (if in campaign mode).
    ``campaign_resources``
        Resources held by this list in the campaign (if in campaign mode).
    ``held_assets``
        Assets held by this list in the campaign (if in campaign mode).

    **Template**

    :template:`core/list.html`
    """

    template_name = "core/list.html"
    context_object_name = "list"

    @traced("ListDetailView_get_object")
    def get_object(self):
        """
        Retrieve the :model:`core.List` by its `id`.

        Uses get_clean_list_or_404 to ensure dirty lists are refreshed
        before display (e.g., after content cost changes).
        """
        return get_clean_list_or_404(
            List.objects.with_related_data(with_fighters=True),
            id=self.kwargs["id"],
        )

    @traced("ListDetailView_get_context_data")
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        list_obj = context["list"]

        # Check if the list has a stash fighter
        context["has_stash_fighter"] = list_obj.listfighter_set.filter(
            content_fighter__is_stash=True
        ).exists()

        # If list is in campaign mode and has a campaign, fetch recent actions
        if list_obj.is_campaign_mode and list_obj.campaign:
            # Get recent actions for this specific list only
            context["recent_actions"] = get_list_recent_campaign_actions(list_obj)

            # Get campaign resources held by this list
            context["campaign_resources"] = get_list_campaign_resources(list_obj)

            # Get assets held by this list
            context["held_assets"] = get_list_held_assets(list_obj)

            # Get captured fighters held by this list
            captured_fighters = list_obj.captured_fighters.filter(
                sold_to_guilders=False
            ).select_related("fighter", "fighter__list")
            context["captured_fighters"] = captured_fighters

        # Get fighters with group keys for display grouping
        # Performance: it's critical that listfighter_set is pre-fetched with related data
        fighters_with_groups = list_obj.listfighter_set.filter(archived=False)
        # We use list(...) to force evaluation of the queryset now
        context["fighters_with_groups"] = list(fighters_with_groups)
        # Performance optimization: only fetch minimal fields for fighters when we offer embed links
        context["fighters_minimal"] = list(fighters_with_groups.values("id", "name"))

        # Get pending invitation count for this list (only for owner)
        if self.request.user.is_authenticated and list_obj.owner == self.request.user:
            from gyrinx.core.models.invitation import CampaignInvitation

            context["pending_invitations_count"] = CampaignInvitation.objects.filter(
                list=list_obj, status=CampaignInvitation.PENDING
            ).count()

        return context


class ListPerformanceView(generic.DetailView):
    template_name = "core/list_performance.html"
    context_object_name = "list"

    def get_object(self):
        """
        Retrieve the :model:`core.List` by its `id`.

        Uses get_clean_list_or_404 to ensure dirty lists are refreshed
        before display (e.g., after content cost changes).
        """
        return get_clean_list_or_404(
            List.objects.with_related_data(with_fighters=True),
            id=self.kwargs["id"],
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # This prevents the banner query being fired in tests
        cache.set(BANNER_CACHE_KEY, False, None)

        return context


class ListAboutDetailView(generic.DetailView):
    """
    Display a narrative view of a single :model:`core.List` object.

    **Context**

    ``list``
        The requested :model:`core.List` object.

    **Template**

    :template:`core/list_about.html`
    """

    template_name = "core/list_about.html"
    context_object_name = "list"

    def get_object(self):
        """
        Retrieve the :model:`core.List` by its `id`.

        Uses get_clean_list_or_404 to ensure dirty lists are refreshed
        before display (e.g., after content cost changes).
        Uses with_related_data() to optimize queries for the list_common_header.
        """
        return get_clean_list_or_404(
            List.objects.with_related_data(), id=self.kwargs["id"]
        )


class ListPrintView(generic.DetailView):
    """
    Display a printable view of a single :model:`core.List` object.

    **Context**

    ``list``
        The requested :model:`core.List` object.
    ``fighters_with_groups``
        QuerySet of :model:`core.ListFighter` objects with group keys for display grouping.
    ``print_config``
        The :model:`core.PrintConfig` object if a config_id is provided.

    **Template**

    :template:`core/list_print.html`
    """

    template_name = "core/list_print.html"
    context_object_name = "list"

    def get_object(self):
        """
        Retrieve the :model:`core.List` by its `id`.

        Uses get_clean_list_or_404 to ensure dirty lists are refreshed
        before display (e.g., after content cost changes).
        """
        return get_clean_list_or_404(List, id=self.kwargs["id"])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        list_obj = context["list"]

        # Get print configuration if specified
        from gyrinx.core.models import PrintConfig

        config_id = self.request.GET.get("config_id")
        print_config = None

        if config_id:
            try:
                print_config = PrintConfig.objects.get(
                    id=config_id, list=list_obj, archived=False
                )
            except PrintConfig.DoesNotExist:
                pass
        else:
            # No default config anymore - just use built-in defaults
            print_config = None

        context["print_config"] = print_config

        # Get fighters with group keys for display grouping
        # Use with_related_data() to prefetch all equipment, profiles, and related data
        # to avoid N+1 queries when templates access fighter properties
        fighters_qs = (
            ListFighter.objects.with_group_keys()
            .with_related_data()
            .filter(list=list_obj, archived=False)
        )

        # Apply print config filters if available
        if print_config:
            # Filter by included fighters if specific ones are selected
            if print_config.included_fighters.exists():
                fighters_qs = fighters_qs.filter(
                    id__in=print_config.included_fighters.values_list("id", flat=True)
                )

            # Exclude dead fighters if configured
            if not print_config.include_dead_fighters:
                fighters_qs = fighters_qs.exclude(injury_state=ListFighter.DEAD)
        else:
            # Default behavior: exclude dead fighters
            fighters_qs = fighters_qs.exclude(injury_state=ListFighter.DEAD)

        context["fighters_with_groups"] = fighters_qs

        # Add attributes if configured to be included
        if not print_config or print_config.include_attributes:
            context["attributes"] = get_list_attributes(list_obj)

        # Add assets and campaign resources if configured to be included
        if not print_config or print_config.include_assets:
            # Get campaign resources
            context["campaign_resources"] = get_list_campaign_resources(list_obj)

            # Get assets held by this list
            context["held_assets"] = get_list_held_assets(list_obj)

        # Add recent campaign actions if configured to be included
        if not print_config or print_config.include_actions:
            context["recent_actions"] = get_list_recent_campaign_actions(list_obj)

        # Add blank card ranges if print_config exists
        if print_config:
            context["blank_fighter_range"] = range(print_config.blank_fighter_cards)
            context["blank_vehicle_range"] = range(print_config.blank_vehicle_cards)

        return context


class ListCampaignClonesView(generic.DetailView):
    """
    Display the campaign clones of a :model:`core.List` object.

    **Context**

    ``list``
        The requested :model:`core.List` object.
    ``campaign_clones``
        QuerySet of campaign mode clones of this list.

    **Template**

    :template:`core/list_campaign_clones.html`
    """

    template_name = "core/list_campaign_clones.html"
    context_object_name = "list"

    def get_object(self):
        """
        Retrieve the :model:`core.List` by its `id`.
        """
        return get_object_or_404(List, id=self.kwargs["id"])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Get all campaign clones, not just active ones
        context["campaign_clones"] = self.object.campaign_clones.all().select_related(
            "campaign", "campaign__owner"
        )
        return context


@login_required
def new_list(request):
    """
    Create a new :model:`core.List` owned by the current user.

    **Context**

    ``form``
        A NewListForm for entering the name and details of the new list.
    ``houses``
        A queryset of :model:`content.ContentHouse` objects, possibly used in the form display.

    **Template**

    :template:`core/list_new.html`
    """
    houses = ContentHouse.objects.all()

    if request.method == "POST":
        form = NewListForm(request.POST)
        if form.is_valid():
            lst = form.save(commit=False)
            lst.owner = request.user

            # Call handler to handle business logic
            result = handle_list_creation(
                user=request.user,
                lst=lst,
                create_stash=form.cleaned_data.get("show_stash", True),
            )

            # Log the list creation event (HTTP-specific)
            log_event(
                user=request.user,
                noun=EventNoun.LIST,
                verb=EventVerb.CREATE,
                object=result.lst,
                request=request,
                list_name=result.lst.name,
                content_house=result.lst.content_house.name,
                public=result.lst.public,
            )

            return HttpResponseRedirect(reverse("core:list", args=(result.lst.id,)))
    else:
        form = NewListForm(
            initial={
                "name": request.GET.get("name", ""),
            }
        )

    return render(
        request,
        "core/list_new.html",
        {"form": form, "houses": houses},
    )


@login_required
def edit_list(request, id):
    """
    Edit an existing :model:`core.List` owned by the current user.

    **Context**

    ``form``
        A EditListForm for editing the list's details.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/list_edit.html`
    """
    list_ = get_object_or_404(List, id=id, owner=request.user)

    error_message = None
    if request.method == "POST":
        form = EditListForm(request.POST, instance=list_)
        if form.is_valid():
            updated_list = form.save(commit=False)
            updated_list.save()

            # Log the list update event
            log_event(
                user=request.user,
                noun=EventNoun.LIST,
                verb=EventVerb.UPDATE,
                object=updated_list,
                request=request,
                list_name=updated_list.name,
            )

            return HttpResponseRedirect(reverse("core:list", args=(list_.id,)))
    else:
        form = EditListForm(instance=list_)

    return render(
        request,
        "core/list_edit.html",
        {"form": form, "error_message": error_message},
    )


@login_required
def edit_list_credits(request, id):
    """
    Modify credits for a :model:`core.List` in campaign mode.

    **Context**

    ``form``
        An EditListCreditsForm for modifying list credits.
    ``list``
        The :model:`core.List` whose credits are being modified.

    **Template**

    :template:`core/list_credits_edit.html`
    """

    # Allow both list owner and campaign owner to modify credits
    # Filter the queryset to include only lists owned by the user or by campaigns they own
    from gyrinx.core.forms.list import EditListCreditsForm
    from gyrinx.core.handlers.list import handle_credits_modification

    lst = get_clean_list_or_404(
        List.objects.filter(Q(owner=request.user) | Q(campaign__owner=request.user)),
        id=id,
    )

    # Check permissions - must be list owner or campaign owner
    if lst.owner != request.user:
        if not (lst.campaign and lst.campaign.owner == request.user):
            messages.error(
                request, "You don't have permission to modify credits for this list."
            )
            return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    # Check campaign mode
    if lst.status != List.CAMPAIGN_MODE:
        messages.error(
            request, "Credits can only be tracked for lists in campaign mode."
        )
        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    if request.method == "POST":
        form = EditListCreditsForm(request.POST, lst=lst)
        if form.is_valid():
            operation = form.cleaned_data["operation"]
            amount = form.cleaned_data["amount"]
            description = form.cleaned_data.get("description", "")

            try:
                result = handle_credits_modification(
                    user=request.user,
                    lst=lst,
                    operation=operation,
                    amount=amount,
                    description=description,
                )

                # Log the credit update event
                log_event(
                    user=request.user,
                    noun=EventNoun.LIST,
                    verb=EventVerb.UPDATE,
                    object=lst,
                    request=request,
                    list_name=lst.name,
                    credit_operation=operation,
                    amount=amount,
                    credits_current=result.credits_after,
                    credits_earned=result.credits_earned_after,
                    description=description,
                )

                messages.success(request, f"Credits updated for {lst.name}")
                return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

            except ValueError as e:
                # Handler validation errors become form errors
                form.add_error("amount", str(e))
    else:
        form = EditListCreditsForm(lst=lst)

    return render(
        request,
        "core/list_credits_edit.html",
        {
            "form": form,
            "list": lst,
        },
    )


@login_required
def archive_list(request, id):
    """
    Archive or unarchive a :model:`core.List`.

    **Context**

    ``list``
        The :model:`core.List` to be archived or unarchived.
    ``is_in_active_campaign``
        Boolean indicating if the list is in an active campaign.
    ``active_campaigns``
        List of active campaigns this list is participating in.

    **Template**

    :template:`core/list_archive.html`
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)

    # Check if the list is in any active campaigns
    active_campaigns = lst.campaigns.filter(status="in_progress")
    is_in_active_campaign = active_campaigns.exists()

    if request.method == "POST":
        from gyrinx.core.models.campaign import CampaignAction

        with transaction.atomic():
            if request.POST.get("archive") == "1":
                lst.archive()

                # Log the archive event
                log_event(
                    user=request.user,
                    noun=EventNoun.LIST,
                    verb=EventVerb.ARCHIVE,
                    object=lst,
                    request=request,
                    list_name=lst.name,
                )

                # Add campaign action log entries for active campaigns
                for campaign in active_campaigns:
                    CampaignAction.objects.create(
                        campaign=campaign,
                        user=request.user,
                        list=lst,
                        description=f"Gang '{lst.name}' has been archived by its owner",
                        owner=request.user,
                    )
            elif lst.archived:
                lst.unarchive()

                # Log the restore event
                log_event(
                    user=request.user,
                    noun=EventNoun.LIST,
                    verb=EventVerb.RESTORE,
                    object=lst,
                    request=request,
                    list_name=lst.name,
                )

                # Add campaign action log entries for active campaigns when unarchiving
                for campaign in active_campaigns:
                    CampaignAction.objects.create(
                        campaign=campaign,
                        user=request.user,
                        list=lst,
                        description=f"Gang '{lst.name}' has been unarchived by its owner",
                        owner=request.user,
                    )

        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    return render(
        request,
        "core/list_archive.html",
        {
            "list": lst,
            "is_in_active_campaign": is_in_active_campaign,
            "active_campaigns": active_campaigns,
        },
    )


@login_required
def show_stash(request, id):
    """
    Add a stash fighter to a list if it doesn't already have one.

    **Context**

    ``list``
        The :model:`core.List` to add a stash fighter to.
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)

    # Check if the list already has a stash fighter
    has_stash = lst.listfighter_set.filter(content_fighter__is_stash=True).exists()

    if not has_stash:
        # Get or create a stash ContentFighter for this house
        stash_fighter, created = ContentFighter.objects.get_or_create(
            house=lst.content_house,
            is_stash=True,
            defaults={
                "type": "Stash",
                "category": "STASH",
                "base_cost": 0,
            },
        )

        # Create the stash ListFighter with correct cached values
        ListFighter.objects.create_with_facts(
            name="Stash",
            content_fighter=stash_fighter,
            list=lst,
            owner=request.user,
        )

        messages.success(request, "Stash fighter added to the list.")
    else:
        messages.info(request, "This list already has a stash fighter.")

    return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))


@login_required
def refresh_list_cost(request, id):
    """
    Refresh the cost cache for a :model:`core.List`.

    Only processes POST requests. Forces recalculation of facts via facts_from_db(),
    then redirects back to the list detail page.

    Can be accessed by either the list owner or the campaign owner (if list is in a campaign).
    """
    lst = get_clean_list_or_404(List, id=id)

    if lst.owner != request.user and (
        not lst.campaign or lst.campaign.owner != request.user
    ):
        raise Http404("List not found")

    if request.method == "POST":
        # Get old cached facts value (from DB cache, not in-memory cache)
        old_facts = lst.facts()
        old_wealth = old_facts.wealth if old_facts else None
        was_dirty = old_facts is None

        # Force recalculation and update DB cache
        new_facts = lst.facts_from_db(update=True)

        # Clear the cached_property if present
        if "cost_int_cached" in lst.__dict__:
            del lst.__dict__["cost_int_cached"]

        track(
            "list_cost_refresh",
            list_id=str(lst.id),
            old_cost=old_wealth,
            new_cost=new_facts.wealth,
            delta=new_facts.wealth - (old_wealth or 0),
            was_dirty=was_dirty,
        )

    return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))


@login_required
def clone_list(request, id):
    """
    Clone an existing :model:`core.List` owned by any user.

    **Context**

    ``form``
        A CloneListForm for entering the name and details of the new list.
    ``list``
        The :model:`core.List` to be cloned.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/list_clone.html`
    """
    # You can clone a list owned by another user
    list_ = get_object_or_404(List, id=id)

    error_message = None
    if request.method == "POST":
        form = CloneListForm(request.POST, list_to_clone=list_)
        if form.is_valid():
            result = handle_list_clone(
                user=request.user,
                original_list=list_,
                name=form.cleaned_data["name"],
                owner=request.user,
                public=form.cleaned_data["public"],
            )

            # Log the list clone event
            log_event(
                user=request.user,
                noun=EventNoun.LIST,
                verb=EventVerb.CLONE,
                object=result.cloned_list,
                request=request,
                list_name=result.cloned_list.name,
                source_list_id=str(list_.id),
                source_list_name=list_.name,
            )

            return HttpResponseRedirect(
                reverse("core:list", args=(result.cloned_list.id,))
            )
    else:
        form = CloneListForm(
            list_to_clone=list_,
            initial={
                "name": f"{list_.name} (Clone)",
                "narrative": list_.narrative,
                "public": list_.public,
            },
        )

    return render(
        request,
        "core/list_clone.html",
        {"form": form, "list": list_, "error_message": error_message},
    )
