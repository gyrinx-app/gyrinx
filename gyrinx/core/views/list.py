import json
import random
import uuid
from typing import Literal, Optional
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.contrib.postgres.search import SearchQuery, SearchVector
from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.paginator import Paginator
from django.db import models, transaction
from django.db.models import Case, Q, When
from django.http import Http404, HttpRequest, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import generic
from django.views.decorators.clickjacking import xframe_options_exempt
from pydantic import BaseModel, ValidationError, field_validator

from gyrinx import messages
from gyrinx.content.models import (
    ContentAdvancementEquipment,
    ContentEquipment,
    ContentEquipmentCategory,
    ContentEquipmentUpgrade,
    ContentFighter,
    ContentFighterDefaultAssignment,
    ContentFighterEquipmentListItem,
    ContentFighterEquipmentListWeaponAccessory,
    ContentFighterPsykerPowerDefaultAssignment,
    ContentHouse,
    ContentPsykerPower,
    ContentRule,
    ContentSkill,
    ContentSkillCategory,
    ContentWeaponAccessory,
    ContentWeaponProfile,
    VirtualWeaponProfile,
)
from gyrinx.core.context_processors import BANNER_CACHE_KEY
from gyrinx.core.forms.advancement import (
    AdvancementDiceChoiceForm,
    AdvancementTypeForm,
    SkillCategorySelectionForm,
    SkillSelectionForm,
)
from gyrinx.core.forms.attribute import ListAttributeForm
from gyrinx.core.forms.list import (
    AddInjuryForm,
    CloneListFighterForm,
    CloneListForm,
    EditFighterStateForm,
    EditListFighterInfoForm,
    EditListFighterNarrativeForm,
    EditListFighterStatsForm,
    EditListForm,
    ListFighterEquipmentAssignmentAccessoriesForm,
    ListFighterEquipmentAssignmentCostForm,
    ListFighterEquipmentAssignmentForm,
    ListFighterEquipmentAssignmentUpgradeForm,
    ListFighterForm,
    NewListForm,
)
from gyrinx.core.handlers.equipment import (
    SaleItemDetail,
    handle_accessory_purchase,
    handle_equipment_component_removal,
    handle_equipment_cost_override,
    handle_equipment_purchase,
    handle_equipment_reassignment,
    handle_equipment_removal,
    handle_equipment_sale,
    handle_equipment_upgrade,
    handle_weapon_profile_purchase,
)
from gyrinx.core.handlers.fighter import (
    FighterCloneParams,
    handle_fighter_advancement,
    handle_fighter_advancement_deletion,
    handle_fighter_archive_toggle,
    handle_fighter_clone,
    handle_fighter_deletion,
    handle_fighter_edit,
    handle_fighter_hire,
    handle_fighter_kill,
    handle_fighter_resurrect,
)
from gyrinx.core.handlers.list import handle_list_clone, handle_list_creation
from gyrinx.core.models.campaign import CampaignAction
from gyrinx.core.models.events import EventField, EventNoun, EventVerb, log_event
from gyrinx.core.models.list import (
    List,
    ListFighter,
    ListFighterAdvancement,
    ListFighterEquipmentAssignment,
    ListFighterInjury,
    ListFighterPsykerPowerAssignment,
    ListFighterStatOverride,
    VirtualListFighterEquipmentAssignment,
)
from gyrinx.core.utils import (
    build_safe_url,
    get_list_attributes,
    get_list_campaign_resources,
    get_list_held_assets,
    get_list_recent_campaign_actions,
    get_return_url,
    safe_redirect,
)
from gyrinx.core.views import make_query_params_str
from gyrinx.models import FighterCategoryChoices, QuerySetOf, is_int, is_valid_uuid
from gyrinx.tracing import traced
from gyrinx.tracker import track


def get_clean_list_or_404(model_or_queryset, *args, **kwargs):
    """
    Get a List object and ensure its cached facts are fresh.

    If the list is marked as dirty (e.g., due to content cost changes),
    this function will refresh the cached facts before returning.

    When passed the List model class directly, this function automatically
    applies the with_latest_actions() prefetch to enable the facts system
    for consistent rating display across all views.

    Args:
        model_or_queryset: A model class (List) or queryset to filter
        *args, **kwargs: Additional arguments passed to get_object_or_404

    Returns:
        List: The list object with fresh cached facts

    Usage:
        get_clean_list_or_404(List, id=id, owner=request.user)
        get_clean_list_or_404(List.objects.filter(...), id=id)
    """
    # If passed the List model directly, apply with_latest_actions() prefetch
    # to enable can_use_facts for consistent rating display
    if model_or_queryset is List:
        model_or_queryset = List.objects.with_latest_actions()

    obj = get_object_or_404(model_or_queryset, *args, **kwargs)

    if obj.dirty:
        obj.facts_from_db(update=True)

    return obj


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
        from gyrinx.core.models.list import ListFighter

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
    from django.db.models import Q

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


@login_required
def new_list_fighter(request, id):
    """
    Add a new :model:`core.ListFighter` to an existing :model:`core.List`.

    **Context**

    ``form``
        A ListFighterForm for adding a new fighter.
    ``list``
        The :model:`core.List` to which this fighter will be added.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/list_fighter_new.html`
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = ListFighter(list=lst, owner=lst.owner)

    error_message = None
    if request.method == "POST":
        form = ListFighterForm(request.POST, instance=fighter)
        if form.is_valid():
            fighter = form.save(commit=False)
            fighter.list = lst
            fighter.owner = lst.owner

            # Call handler to handle business logic
            try:
                result = handle_fighter_hire(
                    user=request.user,
                    lst=lst,
                    fighter=fighter,
                )
            except DjangoValidationError as e:
                error_message = messages.validation(request, e)
                form = ListFighterForm(request.POST, instance=fighter)
                return render(
                    request,
                    "core/list_fighter_new.html",
                    {"form": form, "list": lst, "error_message": error_message},
                )

            # Log the fighter creation event (HTTP-specific)
            log_event(
                user=request.user,
                noun=EventNoun.LIST_FIGHTER,
                verb=EventVerb.CREATE,
                object=result.fighter,
                request=request,
                fighter_name=result.fighter.name,
                list_id=str(lst.id),
                list_name=lst.name,
            )

            # Redirect with flash parameter (HTTP-specific)
            query_params = urlencode(dict(flash=result.fighter.id))
            return HttpResponseRedirect(
                reverse("core:list", args=(lst.id,))
                + f"?{query_params}"
                + f"#{str(result.fighter.id)}"
            )

    else:
        form = ListFighterForm(instance=fighter)

    return render(
        request,
        "core/list_fighter_new.html",
        {"form": form, "list": lst, "error_message": error_message},
    )


@login_required
def edit_list_fighter(request, id, fighter_id):
    """
    Edit an existing :model:`core.ListFighter` within a :model:`core.List`.

    **Context**

    ``form``
        A ListFighterForm for editing fighter details.
    ``list``
        The :model:`core.List` that owns this fighter.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/list_fighter_edit.html`
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )

    error_message = None
    if request.method == "POST":
        # Capture old values before form.is_valid() modifies the instance
        old_name = fighter.name
        old_content_fighter = fighter.content_fighter
        old_legacy_content_fighter = fighter.legacy_content_fighter
        old_category_override = fighter.category_override
        old_cost_override = fighter.cost_override

        form = ListFighterForm(request.POST, instance=fighter)
        if form.is_valid():
            # Form's is_valid() already applied new values to fighter
            # Call handler to save and track changes via ListAction
            handle_fighter_edit(
                user=request.user,
                fighter=fighter,
                old_name=old_name,
                old_content_fighter=old_content_fighter,
                old_legacy_content_fighter=old_legacy_content_fighter,
                old_category_override=old_category_override,
                old_cost_override=old_cost_override,
            )

            # Log the fighter update event
            log_event(
                user=request.user,
                noun=EventNoun.LIST_FIGHTER,
                verb=EventVerb.UPDATE,
                object=fighter,
                request=request,
                fighter_name=fighter.name,
                list_id=str(lst.id),
                list_name=lst.name,
            )

            query_params = urlencode(dict(flash=fighter.id))
            return HttpResponseRedirect(
                reverse("core:list", args=(lst.id,))
                + f"?{query_params}"
                + f"#{str(fighter.id)}"
            )
    else:
        form = ListFighterForm(instance=fighter)

    return render(
        request,
        "core/list_fighter_edit.html",
        {"form": form, "list": lst, "error_message": error_message},
    )


@login_required
def clone_list_fighter(request: HttpRequest, id, fighter_id):
    """
    Clone an existing :model:`core.ListFighter` to the same or another :model:`core.List`.

    **Context**

    ``form``
        A CloneListFighterForm for entering the name and details of the new fighter.
    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` to be cloned.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/list_fighter_clone.html`
    """
    lst = get_clean_list_or_404(List, id=id)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
    )

    error_message = None
    if request.method == "POST":
        form = CloneListFighterForm(request.POST, fighter=fighter, user=request.user)
        if form.is_valid():
            try:
                # Prepare clone params
                # Handle category_override based on checkbox
                # If fighter has an override and checkbox is checked, preserve it
                # Otherwise, clear it
                category_override = None
                if fighter.category_override and form.cleaned_data.get(
                    "clone_category_override", False
                ):
                    category_override = fighter.category_override

                clone_params = FighterCloneParams(
                    name=form.cleaned_data["name"],
                    content_fighter=form.cleaned_data["content_fighter"],
                    target_list=form.cleaned_data["list"],
                    category_override=category_override,
                )

                # Handle the clone operation (clones fighter, creates ListAction, handles credits)
                result = handle_fighter_clone(
                    user=request.user,
                    source_fighter=fighter,
                    clone_params=clone_params,
                )

                # Log the fighter clone event
                log_event(
                    user=request.user,
                    noun=EventNoun.LIST_FIGHTER,
                    verb=EventVerb.CLONE,
                    object=result.fighter,
                    request=request,
                    fighter_name=result.fighter.name,
                    list_id=str(result.fighter.list.id),
                    list_name=result.fighter.list.name,
                    source_fighter_id=str(fighter.id),
                    source_fighter_name=fighter.name,
                )

                query_params = urlencode(dict(flash=result.fighter.id))
                return HttpResponseRedirect(
                    reverse("core:list", args=(result.fighter.list.id,))
                    + f"?{query_params}"
                    + f"#{str(result.fighter.id)}"
                )
            except DjangoValidationError as e:
                error_message = str(e)
    else:
        form = CloneListFighterForm(
            fighter=fighter,
            initial={
                "name": f"{fighter.name} (Clone)",
                "content_fighter": fighter.content_fighter,
                "list": fighter.list,
            },
            user=request.user,
        )

    return render(
        request,
        "core/list_fighter_clone.html",
        {"form": form, "list": lst, "fighter": fighter, "error_message": error_message},
    )


@login_required
def edit_list_fighter_skills(request, id, fighter_id):
    """
    Edit the skills of an existing :model:`core.ListFighter`.

    **Context**

    ``fighter``
        The :model:`core.ListFighter` being edited.
    ``list``
        The :model:`core.List` that owns this fighter.
    ``categories``
        All skill categories with their skills.
    ``category_filter``
        The current filter applied to the skill categories,
        one of "primary-secondary-only" (default), "all" or
        "all-with-restricted".

    **Template**

    :template:`core/list_fighter_skills_edit.html`
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )

    # Get query parameters
    search_query = request.GET.get("q", "").strip()
    category_filter = request.GET.get("category_filter", "primary-secondary-only")

    # Create boolean flags based on value of filter parameter.
    # Note that we don't explicitly handle `all` because it's the default query behaviour.
    show_primary_secondary_only = category_filter == "primary-secondary-only"
    show_restricted = category_filter == "all-with-restricted"

    # Get default skills from ContentFighter
    default_skills = fighter.content_fighter.skills.all()
    disabled_skill_ids = set(fighter.disabled_skills.values_list("id", flat=True))

    # Build default skills with status
    default_skills_display = []
    for skill in default_skills:
        default_skills_display.append(
            {
                "skill": skill,
                "is_disabled": skill.id in disabled_skill_ids,
            }
        )

    # Get current fighter skills (user-added)
    current_skill_ids = set(fighter.skills.values_list("id", flat=True))

    # Get all skill categories with annotations
    # Get fighter's primary and secondary categories including equipment modifications
    primary_categories = fighter.get_primary_skill_categories()
    secondary_categories = fighter.get_secondary_skill_categories()

    # Extract IDs once to avoid duplicate list comprehensions
    primary_category_ids = [cat.id for cat in primary_categories]
    secondary_category_ids = [cat.id for cat in secondary_categories]

    # Build skill categories query
    skill_cats_query = ContentSkillCategory.objects.all()
    if show_restricted:
        # When showing restricted, exclude house-specific categories from regular categories
        # They will be added separately as special categories
        skill_cats_query = skill_cats_query.filter(houses__isnull=True)
    else:
        # Otherwise, exclude restricted categories
        skill_cats_query = skill_cats_query.filter(restricted=False)

    skill_cats = skill_cats_query.annotate(
        primary=Case(
            When(id__in=primary_category_ids, then=True),
            default=False,
            output_field=models.BooleanField(),
        ),
        secondary=Case(
            When(id__in=secondary_category_ids, then=True),
            default=False,
            output_field=models.BooleanField(),
        ),
    )

    # Get special categories
    if show_restricted:
        # When showing restricted, get all house-specific categories from all houses
        special_cats = (
            ContentSkillCategory.objects.filter(houses__isnull=False)
            .distinct()
            .annotate(
                primary=Case(
                    When(id__in=primary_category_ids, then=True),
                    default=False,
                    output_field=models.BooleanField(),
                ),
                secondary=Case(
                    When(id__in=secondary_category_ids, then=True),
                    default=False,
                    output_field=models.BooleanField(),
                ),
            )
        )
    else:
        # Default behavior: only show categories from the fighter's house
        special_cats = fighter.content_fighter.house.skill_categories.all().annotate(
            primary=Case(
                When(id__in=primary_category_ids, then=True),
                default=False,
                output_field=models.BooleanField(),
            ),
            secondary=Case(
                When(id__in=secondary_category_ids, then=True),
                default=False,
                output_field=models.BooleanField(),
            ),
        )

    # Combine all categories
    all_categories = []

    # Process regular categories
    for cat in skill_cats:
        if show_primary_secondary_only and not (cat.primary or cat.secondary):
            continue

        # Get skills for this category that fighter doesn't have
        skills_qs = cat.skills.exclude(id__in=current_skill_ids)

        # Apply search filter
        if search_query:
            skills_qs = skills_qs.filter(name__icontains=search_query)

        if skills_qs.exists():
            all_categories.append(
                {
                    "category": cat,
                    "skills": list(skills_qs.order_by("name")),
                    "is_special": False,
                    "primary": cat.primary,
                    "secondary": cat.secondary,
                }
            )

    # Process special categories
    for cat in special_cats:
        if show_primary_secondary_only and not (cat.primary or cat.secondary):
            continue

        # Get skills for this category that fighter doesn't have
        skills_qs = cat.skills.exclude(id__in=current_skill_ids)

        # Apply search filter
        if search_query:
            skills_qs = skills_qs.filter(name__icontains=search_query)

        if skills_qs.exists():
            all_categories.append(
                {
                    "category": cat,
                    "skills": list(skills_qs.order_by("name")),
                    "is_special": True,
                    "primary": cat.primary,
                    "secondary": cat.secondary,
                }
            )

    return render(
        request,
        "core/list_fighter_skills_edit.html",
        {
            "fighter": fighter,
            "list": lst,
            "default_skills_display": default_skills_display,
            "categories": all_categories,
            "search_query": search_query,
            "category_filter": category_filter,
        },
    )


@login_required
def add_list_fighter_skill(request, id, fighter_id):
    """
    Add a single skill to a :model:`core.ListFighter`.
    """
    if request.method != "POST":
        raise Http404()

    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )

    skill_id = request.POST.get("skill_id")
    if skill_id:
        skill = get_object_or_404(ContentSkill, id=skill_id)
        fighter.skills.add(skill)

        # Log the skill addition event
        log_event(
            user=request.user,
            noun=EventNoun.LIST_FIGHTER,
            verb=EventVerb.UPDATE,
            object=fighter,
            request=request,
            fighter_name=fighter.name,
            list_id=str(lst.id),
            list_name=lst.name,
            field="skills",
            action="add_skill",
            skill_name=skill.name,
            skills_count=fighter.skills.count(),
        )

        messages.success(request, f"Added {skill.name}")

    return HttpResponseRedirect(
        reverse("core:list-fighter-skills-edit", args=(lst.id, fighter.id))
    )


@login_required
def remove_list_fighter_skill(request, id, fighter_id, skill_id):
    """
    Remove a single skill from a :model:`core.ListFighter`.
    """
    if request.method != "POST":
        raise Http404()

    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )

    skill = get_object_or_404(ContentSkill, id=skill_id)
    fighter.skills.remove(skill)

    # Log the skill removal event
    log_event(
        user=request.user,
        noun=EventNoun.LIST_FIGHTER,
        verb=EventVerb.UPDATE,
        object=fighter,
        request=request,
        fighter_name=fighter.name,
        list_id=str(lst.id),
        list_name=lst.name,
        field="skills",
        action="remove_skill",
        skill_name=skill.name,
        skills_count=fighter.skills.count(),
    )

    messages.success(request, f"Removed {skill.name}")

    return HttpResponseRedirect(
        reverse("core:list-fighter-skills-edit", args=(lst.id, fighter.id))
    )


@login_required
def edit_list_fighter_powers(request, id, fighter_id):
    """
    Edit the psyker powers of an existing :model:`core.ListFighter`.

    **Context**

    ``form``
        A ListFighterPowersForm for selecting fighter powers.
    ``list``
        The :model:`core.List` that owns this fighter.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/list_fighter_psyker_powers_edit.html`
    """
    from .fighter_helpers import (
        FighterEditMixin,
        build_virtual_psyker_power_assignments,
        get_common_query_params,
        get_fighter_powers,
        group_available_assignments,
    )

    # Use helper to get fighter and list
    helper = FighterEditMixin()
    lst, fighter = helper.get_fighter_and_list(request, id, fighter_id)

    error_message = None
    if request.method == "POST":
        power_id = request.POST.get("psyker_power_id", None)
        if not power_id:
            return HttpResponseRedirect(
                reverse("core:list-fighter-powers-edit", args=(lst.id, fighter.id))
            )

        if request.POST.get("action") == "remove":
            kind = request.POST.get("assign_kind")
            if kind == "default":
                default_assign = get_object_or_404(
                    ContentFighterPsykerPowerDefaultAssignment,
                    psyker_power=power_id,
                    fighter=fighter.content_fighter_cached,
                )
                fighter.disabled_pskyer_default_powers.add(default_assign)
                fighter.save()

                # Log the power removal event
                helper.log_fighter_event(
                    request,
                    fighter,
                    lst,
                    EventVerb.UPDATE,
                    field="psyker_powers",
                    action="remove_default_power",
                    power_name=default_assign.psyker_power.name,
                )

                return HttpResponseRedirect(
                    reverse("core:list-fighter-powers-edit", args=(lst.id, fighter.id))
                )
            elif kind == "assigned":
                assign = get_object_or_404(
                    ListFighterPsykerPowerAssignment,
                    psyker_power=power_id,
                    list_fighter=fighter,
                )
                power_name = assign.psyker_power.name
                assign.delete()

                # Log the power removal event
                helper.log_fighter_event(
                    request,
                    fighter,
                    lst,
                    EventVerb.UPDATE,
                    field="psyker_powers",
                    action="remove_assigned_power",
                    power_name=power_name,
                )

                return HttpResponseRedirect(
                    reverse("core:list-fighter-powers-edit", args=(lst.id, fighter.id))
                )
            else:
                error_message = "Invalid action."
        elif request.POST.get("action") == "enable":
            # Enable a disabled default power
            default_assign = get_object_or_404(
                ContentFighterPsykerPowerDefaultAssignment,
                psyker_power=power_id,
                fighter=fighter.content_fighter_cached,
            )
            fighter.disabled_pskyer_default_powers.remove(default_assign)
            fighter.save()

            # Log the power enable event
            helper.log_fighter_event(
                request,
                fighter,
                lst,
                EventVerb.UPDATE,
                field="psyker_powers",
                action="enable_default_power",
                power_name=default_assign.psyker_power.name,
            )

            return HttpResponseRedirect(
                reverse("core:list-fighter-powers-edit", args=(lst.id, fighter.id))
            )
        elif request.POST.get("action") == "add":
            power = get_object_or_404(
                ContentPsykerPower,
                id=power_id,
            )
            assign = ListFighterPsykerPowerAssignment(
                list_fighter=fighter,
                psyker_power=power,
            )
            assign.save()

            # Log the power add event
            helper.log_fighter_event(
                request,
                fighter,
                lst,
                EventVerb.UPDATE,
                field="psyker_powers",
                action="add_power",
                power_name=power.name,
            )

            return HttpResponseRedirect(
                reverse("core:list-fighter-powers-edit", args=(lst.id, fighter.id))
            )

    # Get query parameters
    params = get_common_query_params(request)

    # Get powers using helper
    powers = get_fighter_powers(fighter, params["show_restricted"])

    # Build assignments using helper
    all_assigns = build_virtual_psyker_power_assignments(powers, fighter)

    # Separate current powers (unfiltered) from available powers
    # Include disabled defaults in current powers
    current_powers = [
        a
        for a in all_assigns
        if a.kind() in ["default", "assigned"] or getattr(a, "is_disabled", False)
    ]

    # Apply search filter only for the available powers grid
    if params["search_query"]:
        filtered_powers = powers.filter(
            Q(name__icontains=params["search_query"])
            | Q(discipline__name__icontains=params["search_query"])
        )
        assigns = build_virtual_psyker_power_assignments(filtered_powers, fighter)
    else:
        assigns = all_assigns

    # Group available powers by discipline using helper
    available_disciplines = group_available_assignments(assigns, "disc")
    # Rename 'group' to 'discipline' and 'items' to 'powers' for template compatibility
    for disc_data in available_disciplines:
        disc_data["discipline"] = disc_data.pop("group")
        disc_data["powers"] = disc_data.pop("items")

    return render(
        request,
        "core/list_fighter_psyker_powers_edit.html",
        {
            "list": lst,
            "fighter": fighter,
            "powers": powers,
            "assigns": assigns,
            "current_powers": current_powers,
            "available_disciplines": available_disciplines,
            "error_message": error_message,
            **params,  # Includes search_query and show_restricted
        },
    )


@login_required
def edit_list_fighter_narrative(request, id, fighter_id):
    """
    Edit the narrative of an existing :model:`core.ListFighter`.

    **Context**

    ``form``
        A EditListFighterNarrativeForm for editing fighter narrative.
    ``list``
        The :model:`core.List` that owns this fighter.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/list_fighter_narrative_edit.html`
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )

    # Get the return URL from query params or POST data, with fallback to default
    default_url = (
        reverse("core:list-about", args=(lst.id,)) + f"#about-{str(fighter.id)}"
    )
    return_url = get_return_url(request, default_url)

    error_message = None
    if request.method == "POST":
        form = EditListFighterNarrativeForm(request.POST, instance=fighter)
        if form.is_valid():
            form.save()

            # Log the narrative update event
            log_event(
                user=request.user,
                noun=EventNoun.LIST_FIGHTER,
                verb=EventVerb.UPDATE,
                object=fighter,
                request=request,
                fighter_name=fighter.name,
                list_id=str(lst.id),
                list_name=lst.name,
                field="narrative",
                narrative_length=len(fighter.narrative) if fighter.narrative else 0,
            )

            return safe_redirect(request, return_url, fallback_url=default_url)
    else:
        form = EditListFighterNarrativeForm(instance=fighter)

    return render(
        request,
        "core/list_fighter_narrative_edit.html",
        {
            "form": form,
            "list": lst,
            "error_message": error_message,
            "return_url": return_url,
        },
    )


@login_required
def edit_list_fighter_info(request, id, fighter_id):
    """
    Edit the info section (image, save, notes) of an existing :model:`core.ListFighter`.

    **Context**

    ``form``
        A EditListFighterInfoForm for editing fighter info.
    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` being edited.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/list_fighter_info_edit.html`
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )

    # Get the return URL from query params or POST data, with fallback to default
    default_url = (
        reverse("core:list-about", args=(lst.id,)) + f"#about-{str(fighter.id)}"
    )
    return_url = get_return_url(request, default_url)

    error_message = None
    if request.method == "POST":
        form = EditListFighterInfoForm(request.POST, request.FILES, instance=fighter)
        if form.is_valid():
            form.save()

            # Log the info update event
            log_event(
                user=request.user,
                noun=EventNoun.LIST_FIGHTER,
                verb=EventVerb.UPDATE,
                field=EventField.INFO,
                object=fighter,
                request=request,
                fighter_name=fighter.name,
                list_id=str(lst.id),
                list_name=lst.name,
                has_image=bool(fighter.image),
                image_url=fighter.image.url if fighter.image else None,
                has_save=bool(fighter.save_roll),
                has_private_notes=bool(fighter.private_notes),
            )

            return safe_redirect(request, return_url, fallback_url=default_url)
    else:
        form = EditListFighterInfoForm(instance=fighter)

    return render(
        request,
        "core/list_fighter_info_edit.html",
        {
            "form": form,
            "list": lst,
            "fighter": fighter,
            "error_message": error_message,
            "return_url": return_url,
        },
    )


@login_required
@transaction.atomic
def list_fighter_stats_edit(request, id, fighter_id):
    """
    Edit the stat overrides of an existing :model:`core.ListFighter`.

    **Context**

    ``form``
        A EditListFighterStatsForm for editing fighter stats.
    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` being edited.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/list_fighter_stats_edit.html`
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )

    # Get the return URL from query params or POST data, with fallback to default
    default_url = reverse("core:list-fighter-edit", args=(lst.id, fighter.id))
    return_url = get_return_url(request, default_url)

    error_message = None
    if request.method == "POST":
        form = EditListFighterStatsForm(request.POST, fighter=fighter)
        if form.is_valid():
            # Check if the fighter has a custom statline
            has_custom_statline = hasattr(fighter.content_fighter, "custom_statline")

            if has_custom_statline:
                # Handle custom statline overrides
                statline = fighter.content_fighter.custom_statline

                # Delete existing overrides
                fighter.stat_overrides.all().delete()

                # Create new overrides
                for field_name, value in form.cleaned_data.items():
                    if field_name.startswith("stat_") and value:
                        stat_id = field_name.replace("stat_", "")
                        # Find the stat definition
                        stat_def = statline.statline_type.stats.get(id=stat_id)

                        # Create the override
                        ListFighterStatOverride.objects.create(
                            list_fighter=fighter,
                            content_stat=stat_def,
                            value=value,
                            owner=request.user,
                        )
            else:
                # Handle legacy overrides
                for field_name, value in form.cleaned_data.items():
                    if field_name.endswith("_override"):
                        setattr(fighter, field_name, value or None)

                fighter.save()

            # Log the stat update event
            log_event(
                user=request.user,
                noun=EventNoun.LIST_FIGHTER,
                verb=EventVerb.UPDATE,
                field=EventField.STATS,
                object=fighter,
                request=request,
                fighter_name=fighter.name,
                list_id=str(lst.id),
                list_name=lst.name,
                has_custom_statline=has_custom_statline,
            )

            # Use safe redirect with fallback
            return safe_redirect(request, return_url, fallback_url=default_url)
    else:
        form = EditListFighterStatsForm(fighter=fighter)

    return render(
        request,
        "core/list_fighter_stats_edit.html",
        {
            "form": form,
            "list": lst,
            "fighter": fighter,
            "error_message": error_message,
            "return_url": return_url,
        },
    )


@login_required
@transaction.atomic
def edit_list_fighter_equipment(request, id, fighter_id, is_weapon=False):
    """
    Edit the equipment (weapons or gear) of an existing :model:`core.ListFighter`.

    **Context**

    ``fighter``
        The :model:`core.ListFighter` being edited.
    ``equipment``
        A filtered list of :model:`content.ContentEquipment` items.
    ``categories``
        Available equipment categories.
    ``assigns``
        A list of :class:`.VirtualListFighterEquipmentAssignment` objects.
    ``list``
        The :model:`core.List` that owns this fighter.
    ``error_message``
        None or a string describing a form error.
    ``is_weapon``
        Boolean indicating if we're editing weapons or gear.

    **Template**

    :template:`core/list_fighter_weapons_edit.html` or :template:`core/list_fighter_gear_edit.html`
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )
    view_name = (
        "core:list-fighter-weapons-edit" if is_weapon else "core:list-fighter-gear-edit"
    )
    template_name = (
        "core/list_fighter_weapons_edit.html"
        if is_weapon
        else "core/list_fighter_gear_edit.html"
    )

    error_message = None
    if request.method == "POST":
        instance = ListFighterEquipmentAssignment(list_fighter=fighter)
        form = ListFighterEquipmentAssignmentForm(request.POST, instance=instance)
        if form.is_valid():
            assign: ListFighterEquipmentAssignment = form.save(commit=False)

            try:
                # Save the assignment and m2m relationships
                assign.save()
                form.save_m2m()

                # Call handler to handle business logic (credit spending, actions)
                result = handle_equipment_purchase(
                    user=request.user,
                    lst=lst,
                    fighter=fighter,
                    assignment=assign,
                )

                # Extract results for HTTP-specific operations
                assign = result.assignment
                total_cost = result.total_cost
                description = result.description

                # Log the equipment assignment event
                log_event(
                    user=request.user,
                    noun=EventNoun.EQUIPMENT_ASSIGNMENT,
                    verb=EventVerb.CREATE,
                    object=assign,
                    request=request,
                    fighter_id=str(fighter.id),
                    fighter_name=fighter.name,
                    list_id=str(lst.id),
                    list_name=lst.name,
                    equipment_name=assign.content_equipment.name,
                    equipment_type="weapon" if is_weapon else "gear",
                    cost=total_cost,
                    credits_remaining=lst.credits_current if lst.campaign else None,
                )

                messages.success(request, description)

                # Build query parameters, preserving filters from both POST and GET
                query_dict = {}
                query_dict["flash"] = assign.id

                # From POST
                if request.POST.get("filter"):
                    query_dict["filter"] = request.POST.get("filter")
                if request.POST.get("q"):
                    query_dict["q"] = request.POST.get("q")

                # From GET - category and availability filters
                cat_list = request.GET.getlist("cat")
                if cat_list:
                    # For lists, we need to use QueryDict to properly encode them
                    from django.http import QueryDict

                    qd = QueryDict(mutable=True)
                    for k, v in query_dict.items():
                        qd[k] = v
                    qd.setlist("cat", cat_list)

                    al_list = request.GET.getlist("al")
                    if al_list:
                        qd.setlist("al", al_list)

                    mal = request.GET.get("mal")
                    if mal:
                        qd["mal"] = mal

                    mc = request.GET.get("mc")
                    if mc:
                        qd["mc"] = mc

                    query_params = qd.urlencode()
                else:
                    # No lists, use simple approach
                    if request.GET.get("mal"):
                        query_dict["mal"] = request.GET.get("mal")
                    if request.GET.get("mc"):
                        query_dict["mc"] = request.GET.get("mc")
                    query_params = make_query_params_str(**query_dict)
                return HttpResponseRedirect(
                    reverse(view_name, args=(lst.id, fighter.id))
                    + f"?{query_params}"
                    + f"#{str(fighter.id)}"
                )
            except DjangoValidationError as e:
                # Handler failed (e.g., insufficient credits) - clean up the assignment
                assign.delete()

                # Not enough credits or other validation error
                error_message = messages.validation(request, e)

    # Get the appropriate equipment
    # Create expansion rule inputs for cost calculations
    from gyrinx.content.models import ExpansionRuleInputs

    expansion_inputs = ExpansionRuleInputs(list=lst, fighter=fighter)

    if is_weapon:
        equipment = ContentEquipment.objects.weapons().with_expansion_cost_for_fighter(
            fighter.equipment_list_fighter, expansion_inputs
        )
        search_vector = SearchVector(
            "name",
            "category__name",
            "contentweaponprofile__name",
            "contentweaponprofile__traits__name",
        )
    else:
        equipment = (
            ContentEquipment.objects.non_weapons().with_expansion_cost_for_fighter(
                fighter.equipment_list_fighter, expansion_inputs
            )
        )
        search_vector = SearchVector("name", "category__name")

    # Get categories for this equipment type
    categories = (
        ContentEquipmentCategory.objects.filter(id__in=equipment.values("category_id"))
        .distinct()
        .order_by("name")
    )

    # Filter categories based on fighter category restrictions
    # Batch-fetch all restrictions to avoid N+1 queries
    fighter_category = fighter.get_category()
    from collections import defaultdict

    from gyrinx.content.models import ContentEquipmentCategoryFighterRestriction

    all_restrictions = ContentEquipmentCategoryFighterRestriction.objects.filter(
        equipment_category__in=categories
    ).values("equipment_category_id", "fighter_category")
    restrictions_by_category = defaultdict(list)
    for r in all_restrictions:
        restrictions_by_category[r["equipment_category_id"]].append(
            r["fighter_category"]
        )

    restricted_category_ids = []
    for category in categories:
        restrictions = restrictions_by_category.get(category.id, [])
        # If restrictions exist and fighter category is not in them, it's restricted
        if restrictions and fighter_category not in restrictions:
            restricted_category_ids.append(category.id)

    # Remove restricted categories
    if restricted_category_ids:
        categories = categories.exclude(id__in=restricted_category_ids)
        equipment = equipment.exclude(category_id__in=restricted_category_ids)

    # Filter by category if specified
    cats = (
        [
            cat
            for cat in request.GET.getlist("cat", list())
            if cat and is_valid_uuid(cat)
        ]
        if not is_weapon
        else request.GET.getlist("cat", list())
    )

    if cats and "all" not in cats:
        equipment = equipment.filter(category_id__in=cats)

    # Apply search filter if provided
    if request.GET.get("q"):
        search_query = SearchQuery(request.GET.get("q", ""))
        equipment = (
            equipment.annotate(search=search_vector)
            .filter(search=search_query)
            .distinct("category__name", "name", "id")
        )

    # Check if the house has can_buy_any flag
    house_can_buy_any = lst.content_house.can_buy_any

    # Check if equipment list filter is active
    # Default to equipment-list when filter is not provided (matches template behavior)
    # But if house has can_buy_any and no filter is provided, redirect to filter=all
    if house_can_buy_any and "filter" not in request.GET:
        # Redirect to the same URL with filter=all
        query_dict = request.GET.copy()
        query_dict["filter"] = "all"
        return HttpResponseRedirect(
            reverse(view_name, args=(lst.id, fighter.id)) + f"?{query_dict.urlencode()}"
        )

    filter_value = request.GET.get("filter", "equipment-list")
    is_equipment_list = filter_value == "equipment-list"

    # Apply maximum availability level filter if provided
    mal = (
        int(request.GET.get("mal"))
        if request.GET.get("mal") and is_int(request.GET.get("mal"))
        else None
    )

    # Get equipment list IDs once - used in multiple places
    equipment_list_ids = ContentFighterEquipmentListItem.objects.filter(
        fighter__in=fighter.equipment_list_fighters
    ).values_list("equipment_id", flat=True)

    # Also include equipment from applicable expansions
    from gyrinx.content.models import ContentEquipmentListExpansion

    expansion_equipment = ContentEquipmentListExpansion.get_expansion_equipment(
        expansion_inputs
    )
    expansion_equipment_ids = list(expansion_equipment.values_list("id", flat=True))

    # Combine regular equipment list IDs with expansion equipment IDs
    equipment_list_ids = list(equipment_list_ids) + expansion_equipment_ids

    if is_equipment_list:
        # When equipment list is toggled and no explicit availability filter is provided,
        # show all equipment from the fighter's equipment list regardless of availability
        equipment = equipment.filter(id__in=equipment_list_ids)
        # For profile filtering later, we need to know all rarities are allowed
        als = ["C", "R", "I", "L", "E"]  # All possible rarities

        # Use expansion profiles when equipment list filter is active
        if is_weapon:
            equipment = equipment.with_expansion_profiles_for_fighter(
                fighter.equipment_list_fighter, expansion_inputs
            )
    else:
        # Apply availability filters (either explicit or default)
        als = request.GET.getlist("al", ["C", "R"])
        equipment = equipment.filter(rarity__in=set(als))

        # Still need profiles for weapons when not in equipment list mode
        if is_weapon:
            equipment = equipment.with_profiles_for_fighter(
                fighter.equipment_list_fighter
            )

        if mal:
            # Only filter by rarity_roll for items that aren't Common
            # Common items should always be visible
            equipment = equipment.filter(Q(rarity="C") | Q(rarity_roll__lte=mal))

    # Apply maximum cost filter if provided (works in both filter modes)
    mc = (
        int(request.GET.get("mc"))
        if request.GET.get("mc") and is_int(request.GET.get("mc"))
        else None
    )
    if mc is not None:
        equipment = equipment.filter(cost_for_fighter__lte=mc)

    # If house has can_buy_any, also include equipment from equipment list
    if house_can_buy_any:
        # Combine equipment and equipment_list_items using a single filter with Q
        combined_equipment_qs = ContentEquipment.objects.filter(
            Q(id__in=equipment.values("id")) | Q(id__in=equipment_list_ids)
        )

        if is_weapon:
            equipment = combined_equipment_qs.with_expansion_cost_for_fighter(
                fighter.equipment_list_fighter, expansion_inputs
            ).with_expansion_profiles_for_fighter(
                fighter.equipment_list_fighter, expansion_inputs
            )
        else:
            equipment = combined_equipment_qs.with_expansion_cost_for_fighter(
                fighter.equipment_list_fighter, expansion_inputs
            )

        # Re-apply cost filter after re-annotation
        if mc is not None:
            equipment = equipment.filter(cost_for_fighter__lte=mc)

    # Create assignment objects
    assigns = []
    for item in equipment:
        if is_weapon:
            # Get profiles from all equipment list fighters (legacy and base)
            profiles = []
            for ef in fighter.equipment_list_fighters:
                profiles.extend(item.profiles_for_fighter(ef))

            # Apply profile filtering based on availability
            profiles = [
                profile
                for profile in profiles
                # Keep standard profiles
                if profile.cost == 0
                # They have an Al that matches the filter, and no roll value
                or (not profile.rarity_roll and profile.rarity in als)
                # They have an Al that matches the filter, and a roll
                or (
                    profile.rarity_roll
                    and profile.rarity in als
                    and (
                        # If mal is set, check if profile passes the threshold
                        (mal and profile.rarity_roll <= mal)
                        # If mal is not set, show all profiles with matching rarity
                        or not mal
                    )
                )
            ]

            # If equipment list filter is active, further filter to only profiles on the equipment list
            if is_equipment_list:
                # Get weapon profiles that are specifically on the equipment list
                equipment_list_profiles = (
                    ContentFighterEquipmentListItem.objects.filter(
                        fighter__in=fighter.equipment_list_fighters,
                        equipment=item,
                        weapon_profile__isnull=False,
                    ).values_list("weapon_profile_id", flat=True)
                )

                # Also get weapon profiles from expansions
                from gyrinx.content.models import (
                    ContentEquipmentListExpansion,
                    ContentEquipmentListExpansionItem,
                )

                # Get applicable expansions using existing expansion_inputs
                applicable_expansions = (
                    ContentEquipmentListExpansion.get_applicable_expansions(
                        expansion_inputs
                    )
                )

                # Get weapon profiles from expansion items
                expansion_profiles = ContentEquipmentListExpansionItem.objects.filter(
                    expansion__in=applicable_expansions,
                    equipment=item,
                    weapon_profile__isnull=False,
                ).values_list("weapon_profile_id", flat=True)

                # Combine both sets of profiles
                all_equipment_list_profiles = set(equipment_list_profiles) | set(
                    expansion_profiles
                )

                profiles = [
                    profile
                    for profile in profiles
                    # Keep standard profiles (cost = 0)
                    if profile.cost == 0
                    # Or keep profiles that are specifically on the equipment list
                    or profile.id in all_equipment_list_profiles
                ]

            assigns.append(
                VirtualListFighterEquipmentAssignment(
                    fighter=fighter,
                    equipment=item,
                    profiles=profiles,
                )
            )
        else:
            assigns.append(
                VirtualListFighterEquipmentAssignment(
                    fighter=fighter,
                    equipment=item,
                )
            )

    context = {
        "fighter": fighter,
        "equipment": equipment,
        "categories": categories,
        "assigns": assigns,
        "list": lst,
        "error_message": error_message,
        "is_weapon": is_weapon,
        "is_equipment_list": is_equipment_list,
    }

    # Add weapons-specific context if needed
    if is_weapon:
        context["weapons"] = equipment

    return render(request, template_name, context)


@login_required
@transaction.atomic
def edit_list_fighter_assign_cost(
    request, id, fighter_id, assign_id, back_name, action_name
):
    """
    Edit the cost of an existing :model:`core.ListFighterEquipmentAssignment`.

    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` owning this equipment assignment.
    ``assign``
        The :model:`core.ListFighterEquipmentAssignment` to be edited.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/list_fighter_assign_cost_edit.html`
    """
    lst = get_clean_list_or_404(
        List.objects.with_related_data(), id=id, owner=request.user
    )
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )
    assignment = get_object_or_404(
        ListFighterEquipmentAssignment.objects.with_related_data(),
        pk=assign_id,
        list_fighter=fighter,
    )

    error_message = None
    if request.method == "POST":
        # Capture old value before form.is_valid() modifies the instance
        old_total_cost_override = assignment.total_cost_override

        form = ListFighterEquipmentAssignmentCostForm(request.POST, instance=assignment)
        if form.is_valid():
            # Form's is_valid() already applied new value to assignment
            # Call handler to save and track changes via ListAction
            handle_equipment_cost_override(
                user=request.user,
                lst=lst,
                fighter=fighter,
                assignment=assignment,
                old_total_cost_override=old_total_cost_override,
                new_total_cost_override=assignment.total_cost_override,
            )

            # Log the cost update event
            log_event(
                user=request.user,
                noun=EventNoun.EQUIPMENT_ASSIGNMENT,
                verb=EventVerb.UPDATE,
                object=assignment,
                request=request,
                fighter_id=str(fighter.id),
                fighter_name=fighter.name,
                list_id=str(lst.id),
                list_name=lst.name,
                equipment_name=assignment.content_equipment.name,
                field="total_cost_override",
                new_cost=assignment.total_cost_override,
            )

            return HttpResponseRedirect(reverse(back_name, args=(lst.id, fighter.id)))

    form = ListFighterEquipmentAssignmentCostForm(
        instance=assignment,
    )

    return render(
        request,
        "core/list_fighter_assign_cost_edit.html",
        {
            "list": lst,
            "fighter": fighter,
            "assign": assignment,
            "form": form,
            "error_message": error_message,
            "action_url": action_name,
            "back_url": back_name,
        },
    )


@login_required
@transaction.atomic
def delete_list_fighter_assign(
    request, id, fighter_id, assign_id, back_name, action_name
):
    """
    Remove a :model:`core.ListFighterEquipmentAssignment` from a fighter.

    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` owning this equipment assignment.
    ``assign``
        The :model:`core.ListFighterEquipmentAssignment` to be deleted.

    **Template**

    :template:`core/list_fighter_assign_delete_confirm.html`
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )
    assignment = get_object_or_404(
        ListFighterEquipmentAssignment.objects.with_related_data(),
        pk=assign_id,
        list_fighter=fighter,
    )

    if request.method == "POST":
        # Store equipment name for logging before handler deletes it
        equipment_name = assignment.content_equipment.name

        # Call handler to perform business logic
        handle_equipment_removal(
            user=request.user,
            lst=lst,
            fighter=fighter,
            assignment=assignment,
            request_refund=request.POST.get("refund") == "on",
        )

        # Log the equipment deletion
        log_event(
            user=request.user,
            noun=EventNoun.EQUIPMENT_ASSIGNMENT,
            verb=EventVerb.DELETE,
            object=fighter,  # Log against the fighter since assignment is deleted
            request=request,
            fighter_name=fighter.name,
            list_id=str(lst.id),
            list_name=lst.name,
            equipment_name=equipment_name,
        )

        return HttpResponseRedirect(reverse(back_name, args=(lst.id, fighter.id)))

    return render(
        request,
        "core/list_fighter_assign_delete_confirm.html",
        {
            "list": lst,
            "fighter": fighter,
            "assign": assignment,
            "action_url": action_name,
            "back_url": back_name,
        },
    )


@login_required
@transaction.atomic
def delete_list_fighter_gear_upgrade(
    request, id, fighter_id, assign_id, upgrade_id, back_name, action_name
):
    """
    Remove am upgrade from a :model:`core.ListFighterEquipmentAssignment` for a fighter.

    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` owning this equipment assignment.
    ``assign``
        The :model:`core.ListFighterEquipmentAssignment` to be deleted.
    ``upgrade``
        The :model:`content.ContentEquipmentUpgrade` upgrade to be removed.

    **Template**

    :template:`core/list_fighter_assign_upgrade_delete_confirm.html`
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )
    assignment = get_object_or_404(
        ListFighterEquipmentAssignment.objects.with_related_data(),
        pk=assign_id,
        list_fighter=fighter,
    )
    upgrade = get_object_or_404(
        ContentEquipmentUpgrade,
        pk=upgrade_id,
    )

    default_url = reverse(back_name, args=(lst.id, fighter.id))
    return_url = get_return_url(request, default_url)

    if request.method == "POST":
        # Call handler to perform business logic
        handle_equipment_component_removal(
            user=request.user,
            lst=lst,
            fighter=fighter,
            assignment=assignment,
            component_type="upgrade",
            component=upgrade,
            request_refund=request.POST.get("refund") == "on",
        )

        # Log the upgrade removal
        log_event(
            user=request.user,
            noun=EventNoun.EQUIPMENT_ASSIGNMENT,
            verb=EventVerb.UPDATE,
            object=assignment,
            request=request,
            fighter_name=fighter.name,
            list_id=str(lst.id),
            list_name=lst.name,
            equipment_name=assignment.content_equipment.name,
            upgrade_removed=upgrade.name,
        )

        return safe_redirect(request, return_url, default_url)

    # Calculate upgrade cost for display
    upgrade_cost = assignment._upgrade_cost_with_override(upgrade)

    return render(
        request,
        "core/list_fighter_assign_upgrade_delete_confirm.html",
        {
            "list": lst,
            "fighter": fighter,
            "assign": assignment,
            "upgrade": upgrade,
            "upgrade_cost": upgrade_cost,
            "action_url": action_name,
            "return_url": return_url,
        },
    )


@login_required
@transaction.atomic
def edit_list_fighter_weapon_accessories(request, id, fighter_id, assign_id):
    """
    Managed weapon accessories for a :model:`core.ListFighterEquipmentAssignment`.

    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` owning this equipment assignment.
    ``assign``
        The :model:`core.ListFighterEquipmentAssignment` to be edited.
    ``accessories``
        A list of :model:`content.ContentWeaponAccessory` objects.
    ``error_message``
        None or a string describing a form error.
    ``filter``
        Filter mode - "equipment-list" or "all".
    ``search_query``
        Search query for filtering accessories.

    **Template**

    :template:`core/list_fighter_weapons_accessories_edit.html`

    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )
    assignment = get_object_or_404(
        ListFighterEquipmentAssignment.objects.with_related_data(),
        pk=assign_id,
        list_fighter=fighter,
    )

    error_message = None

    # Handle adding a new accessory
    if request.method == "POST" and "accessory_id" in request.POST:
        accessory_id = request.POST.get("accessory_id")
        accessory = get_object_or_404(ContentWeaponAccessory, pk=accessory_id)

        try:
            # Call handler to handle business logic (credit spending, actions)
            result = handle_accessory_purchase(
                user=request.user,
                lst=lst,
                fighter=fighter,
                assignment=assignment,
                accessory=accessory,
            )

            messages.success(request, result.description)
        except DjangoValidationError as e:
            # Handler failed (e.g., insufficient credits)
            error_message = messages.validation(request, e)

        # Only redirect if there's no error
        if not error_message:
            # Build query parameters to preserve filters
            query_params = {}
            if request.POST.get("filter"):
                query_params["filter"] = request.POST.get("filter")
            if request.POST.get("q"):
                query_params["q"] = request.POST.get("q")
            query_string = f"?{urlencode(query_params)}" if query_params else ""

            # Redirect back to the same page with filters preserved
            return HttpResponseRedirect(
                reverse(
                    "core:list-fighter-weapon-accessories-edit",
                    args=(lst.id, fighter.id, assignment.id),
                )
                + query_string
            )

    # Handle removing accessories via form
    elif request.method == "POST":
        form = ListFighterEquipmentAssignmentAccessoriesForm(
            request.POST, instance=assignment
        )
        if form.is_valid():
            form.save()

        return HttpResponseRedirect(
            reverse("core:list-fighter-weapons-edit", args=(lst.id, fighter.id))
        )

    # Get filter parameters
    filter_mode = request.GET.get("filter", "equipment-list")
    search_query = request.GET.get("q", "")

    # Build the accessories queryset
    if filter_mode == "equipment-list":
        # Get accessories from equipment list
        equipment_list_accessories = (
            ContentFighterEquipmentListWeaponAccessory.objects.filter(
                fighter=fighter.content_fighter
            ).values_list("weapon_accessory_id", flat=True)
        )

        accessories_qs = ContentWeaponAccessory.objects.filter(
            id__in=equipment_list_accessories
        ).with_cost_for_fighter(fighter.content_fighter)
    else:
        # Get all accessories
        accessories_qs = ContentWeaponAccessory.objects.all().with_cost_for_fighter(
            fighter.content_fighter
        )

    # Apply search filter
    if search_query:
        accessories_qs = accessories_qs.filter(name__icontains=search_query)

    # Order by name
    accessories_qs = accessories_qs.order_by("name")

    # Get accessories already on the weapon
    existing_accessory_ids = assignment.weapon_accessories_field.values_list(
        "id", flat=True
    )

    # Prepare accessories for display
    accessories = []
    for accessory in accessories_qs:
        # Calculate the actual cost for this accessory on this weapon assignment
        # TODO: this should probably be refactored to use a method on the assignment named
        #       something finishing `..._display`
        cost_int = assignment.accessory_cost_int(accessory)
        cost_display = f"{cost_int}¢" if cost_int != 0 else ""

        if accessory.id not in existing_accessory_ids:
            accessories.append(
                {
                    "id": accessory.id,
                    "name": accessory.name,
                    "cost_int": cost_int,
                    "cost_display": cost_display,
                }
            )

    form = ListFighterEquipmentAssignmentAccessoriesForm(
        instance=assignment,
    )

    return render(
        request,
        "core/list_fighter_weapons_accessories_edit.html",
        {
            "list": lst,
            "fighter": fighter,
            "form": form,
            "error_message": error_message,
            "assign": VirtualListFighterEquipmentAssignment.from_assignment(assignment),
            "accessories": accessories,
            "filter": filter_mode,
            "search_query": search_query,
            "mode": "edit",
        },
    )


@login_required
@transaction.atomic
def edit_single_weapon(request, id, fighter_id, assign_id):
    """
    Edit weapon profiles for a single :model:`core.ListFighterEquipmentAssignment`.

    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` owning this equipment assignment.
    ``assign``
        The :model:`core.ListFighterEquipmentAssignment` to be edited.
    ``profiles``
        A list of available :model:`content.ContentWeaponProfile` objects.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/list_fighter_weapon_edit.html`

    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )
    assignment = get_object_or_404(
        ListFighterEquipmentAssignment.objects.with_related_data(),
        pk=assign_id,
        list_fighter=fighter,
    )

    error_message = None

    # Handle adding a new profile
    if request.method == "POST" and "profile_id" in request.POST:
        profile_id = request.POST.get("profile_id")
        profile = get_object_or_404(
            ContentWeaponProfile, pk=profile_id, equipment=assignment.content_equipment
        )

        try:
            # Call handler to handle business logic (credit spending, actions)
            result = handle_weapon_profile_purchase(
                user=request.user,
                lst=lst,
                fighter=fighter,
                assignment=assignment,
                profile=profile,
            )

            messages.success(request, result.description)
        except DjangoValidationError as e:
            # Handler failed (e.g., insufficient credits)
            error_message = messages.validation(request, e)

        # Only redirect if there's no error
        if not error_message:
            # Redirect back to the same page
            return HttpResponseRedirect(
                reverse(
                    "core:list-fighter-weapon-edit",
                    args=(lst.id, fighter.id, assignment.id),
                )
            )

    # Get all available profiles for this weapon
    # Exclude standard (free) profiles as they're automatically included
    profiles_qs = (
        ContentWeaponProfile.objects.filter(equipment=assignment.content_equipment)
        .exclude(cost=0)
        .prefetch_related("traits")
        .order_by("cost", "name")
    )

    # Get already assigned profile IDs to filter them out from available profiles
    existing_profile_ids = set(
        assignment.weapon_profiles_field.values_list("id", flat=True)
    )

    # Build list of available profiles
    from gyrinx.content.models import VirtualWeaponProfile

    profiles = []
    for profile in profiles_qs:
        if profile.id not in existing_profile_ids:
            # Calculate the actual cost for this profile on this weapon assignment
            # Wrap the profile in VirtualWeaponProfile as expected by profile_cost_int
            virtual_profile = VirtualWeaponProfile(profile=profile)
            cost_int = assignment.profile_cost_int(virtual_profile)
            cost_display = f"{cost_int}¢" if cost_int != 0 else ""

            # Format traits as a comma-separated string
            traits_list = list(profile.traits.all())
            traits_str = (
                ", ".join([trait.name for trait in traits_list]) if traits_list else ""
            )

            profiles.append(
                {
                    "id": profile.id,
                    "name": profile.name,
                    "cost_int": cost_int,
                    "cost_display": cost_display,
                    # Use correct field names that VirtualWeaponProfile provides
                    "range_short": profile.range_short,
                    "range_long": profile.range_long,
                    "accuracy_short": profile.accuracy_short,
                    "accuracy_long": profile.accuracy_long,
                    "strength": profile.strength,
                    "armour_piercing": profile.armour_piercing,
                    "damage": profile.damage,
                    "ammo": profile.ammo,
                    "traits": traits_str,
                }
            )

    return render(
        request,
        "core/list_fighter_weapon_edit.html",
        {
            "list": lst,
            "fighter": fighter,
            "assign": VirtualListFighterEquipmentAssignment.from_assignment(assignment),
            "profiles": profiles,
            "error_message": error_message,
        },
    )


@login_required
@transaction.atomic
def delete_list_fighter_weapon_profile(request, id, fighter_id, assign_id, profile_id):
    """
    Remove a :model:`content.ContentWeaponProfile` from a fighter :model:`core.ListFighterEquipmentAssignment`.

    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` owning this equipment assignment.
    ``assign``
        The :model:`core.ListFighterEquipmentAssignment` to be edited.
    ``profile``
        The :model:`content.ContentWeaponProfile` to be removed.

    **Template**

    :template:`core/list_fighter_weapon_profile_delete.html`

    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )
    assignment = get_object_or_404(
        ListFighterEquipmentAssignment.objects.with_related_data(),
        pk=assign_id,
        list_fighter=fighter,
    )
    profile = get_object_or_404(
        ContentWeaponProfile,
        pk=profile_id,
    )

    if request.method == "POST":
        # Call handler to perform business logic
        handle_equipment_component_removal(
            user=request.user,
            lst=lst,
            fighter=fighter,
            assignment=assignment,
            component_type="profile",
            component=profile,
            request_refund=request.POST.get("refund") == "on",
        )

        # Redirect back to the weapon edit page
        return HttpResponseRedirect(
            reverse(
                "core:list-fighter-weapon-edit",
                args=(lst.id, fighter.id, assignment.id),
            )
        )

    # Calculate profile cost for template
    virtual_profile = VirtualWeaponProfile(profile=profile)
    profile_cost = assignment.profile_cost_int(virtual_profile)

    return render(
        request,
        "core/list_fighter_weapon_profile_delete.html",
        {
            "list": lst,
            "fighter": fighter,
            "assign": VirtualListFighterEquipmentAssignment.from_assignment(assignment),
            "profile": profile,
            "profile_cost": profile_cost,
        },
    )


@login_required
@transaction.atomic
def delete_list_fighter_weapon_accessory(
    request, id, fighter_id, assign_id, accessory_id
):
    """
    Remove a :model:`content.ContentWeaponAccessory` from a fighter :model:`core.ListFighterEquipmentAssignment`.

    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` owning this equipment assignment.
    ``assign``
        The :model:`core.ListFighterEquipmentAssignment` to be deleted.
    ``accessory``
        The :model:`content.ContentWeaponAccessory` to be removed.

    **Template**

    :template:`core/list_fighter_weapons_accessory_delete.html`
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )
    assignment = get_object_or_404(
        ListFighterEquipmentAssignment.objects.with_related_data(),
        pk=assign_id,
        list_fighter=fighter,
    )
    accessory = get_object_or_404(
        ContentWeaponAccessory,
        pk=accessory_id,
    )

    default_url = (
        reverse("core:list-fighter-weapons-edit", args=(lst.id, fighter.id))
        + f"?flash={assignment.id}#{str(fighter.id)}"
    )
    return_url = get_return_url(request, default_url)

    if request.method == "POST":
        # Call handler to perform business logic
        handle_equipment_component_removal(
            user=request.user,
            lst=lst,
            fighter=fighter,
            assignment=assignment,
            component_type="accessory",
            component=accessory,
            request_refund=request.POST.get("refund") == "on",
        )

        # Log the weapon accessory removal
        log_event(
            user=request.user,
            noun=EventNoun.EQUIPMENT_ASSIGNMENT,
            verb=EventVerb.UPDATE,
            object=assignment,
            request=request,
            fighter_name=fighter.name,
            list_id=str(lst.id),
            list_name=lst.name,
            equipment_name=assignment.content_equipment.name,
            accessory_removed=accessory.name,
        )

        return safe_redirect(request, return_url, default_url)

    # Calculate accessory cost for template
    accessory_cost = assignment.accessory_cost_int(accessory)

    return render(
        request,
        "core/list_fighter_weapons_accessory_delete.html",
        {
            "list": lst,
            "fighter": fighter,
            "assign": assignment,
            "accessory": accessory,
            "accessory_cost": accessory_cost,
            "return_url": return_url,
        },
    )


@login_required
@transaction.atomic
def edit_list_fighter_weapon_upgrade(
    request, id, fighter_id, assign_id, back_name, action_name
):
    """
    Edit the weapon upgrade of an existing :model:`core.ListFighterEquipmentAssignment`.

    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` owning this equipment assignment.
    ``assign``
        The :model:`core.ListFighterEquipmentAssignment` to be edited.
    ``upgrade``
        The :model:`content.ContentEquipmentUpgrade` upgrade to be added.

    **Template**

    :template:`core/list_fighter_assign_upgrade_edit.html`
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )
    assignment = get_object_or_404(
        ListFighterEquipmentAssignment.objects.with_related_data(),
        pk=assign_id,
        list_fighter=fighter,
    )

    error_message = None
    if request.method == "POST":
        form = ListFighterEquipmentAssignmentUpgradeForm(
            request.POST, instance=assignment
        )
        if form.is_valid():
            # Extract new upgrades from form
            new_upgrades = form.cleaned_data["upgrades_field"]

            try:
                # Call handler to handle business logic (credit spending, actions, upgrade update)
                result = handle_equipment_upgrade(
                    user=request.user,
                    lst=lst,
                    fighter=fighter,
                    assignment=assignment,
                    new_upgrades=list(new_upgrades),
                )
                messages.success(request, result.description)
            except DjangoValidationError as e:
                # Handler failed (e.g., insufficient credits)
                error_message = messages.validation(request, e)

            # Only redirect if there's no error
            if not error_message:
                return HttpResponseRedirect(
                    reverse(back_name, args=(lst.id, fighter.id))
                )
    else:
        form = ListFighterEquipmentAssignmentUpgradeForm(instance=assignment)

    return render(
        request,
        "core/list_fighter_assign_upgrade_edit.html",
        {
            "list": lst,
            "fighter": fighter,
            "assign": assignment,
            "action_url": action_name,
            "back_url": back_name,
            "form": form,
            "error_message": error_message,
        },
    )


@login_required
@transaction.atomic
def disable_list_fighter_default_assign(
    request, id, fighter_id, assign_id, action_name, back_name
):
    """
    Disable a default assignment from :model:`content.ContentFighterDefaultAssignment`.

    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` owning this equipment assignment.
    ``assign``
        The :model:`content.ContentFighterDefaultAssignment` to be disabled.

    **Template**

    :template:`core/list_fighter_assign_disable.html`
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )
    assignment = get_object_or_404(
        ContentFighterDefaultAssignment,
        pk=assign_id,
    )

    if request.method == "POST":
        fighter.disabled_default_assignments.add(assignment)
        fighter.save()
        return HttpResponseRedirect(reverse(back_name, args=(lst.id, fighter.id)))

    return render(
        request,
        "core/list_fighter_assign_disable.html",
        {
            "list": lst,
            "fighter": fighter,
            "assign": assignment,
            "action_url": action_name,
            "back_url": back_name,
        },
    )


@login_required
@transaction.atomic
def convert_list_fighter_default_assign(
    request, id, fighter_id, assign_id, action_name, back_name
):
    """
    Convert a default assignment from :model:`content.ContentFighterDefaultAssignment` to a
    :model:`core.ListFighterEquipmentAssignment`.
    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` owning this equipment assignment.
    ``assign``
        The :model:`content.ContentFighterDefaultAssignment` to be converted.
    ``action_url``
        The URL to redirect to after the conversion.
    ``back_url``
        The URL to redirect back to the list fighter.

    **Template**
    :template:`core/list_fighter_assign_convert.html`
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )
    assignment = get_object_or_404(
        ContentFighterDefaultAssignment,
        pk=assign_id,
    )

    if request.method == "POST":
        fighter.convert_default_assignment(assignment)
        return HttpResponseRedirect(reverse(back_name, args=(lst.id, fighter.id)))

    return render(
        request,
        "core/list_fighter_assign_convert.html",
        {
            "list": lst,
            "fighter": fighter,
            "assign": assignment,
            "action_url": action_name,
            "back_url": back_name,
        },
    )


@login_required
def archive_list_fighter(request, id, fighter_id):
    """
    Archive or unarchive a :model:`core.ListFighter`.

    **Context**

    ``fighter``
        The :model:`core.ListFighter` to be archived or unarchived.
    ``list``
        The :model:`core.List` that owns this fighter.

    **Template**

    :template:`core/list_fighter_archive.html`
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )

    if request.method == "POST":
        # Determine archive/unarchive based on POST data
        archive = request.POST.get("archive") == "1"

        # Only process if archiving or if fighter is currently archived (for unarchive)
        if archive or fighter.archived:
            # Call handler to perform business logic
            result = handle_fighter_archive_toggle(
                user=request.user,
                lst=lst,
                fighter=fighter,
                archive=archive,
                request_refund=request.POST.get("refund") == "on",
            )

            # Log the event based on operation
            log_event(
                user=request.user,
                noun=EventNoun.LIST_FIGHTER,
                verb=EventVerb.ARCHIVE if result.archived else EventVerb.RESTORE,
                object=fighter,
                request=request,
                fighter_name=fighter.name,
                list_id=str(lst.id),
                list_name=lst.name,
            )

        return HttpResponseRedirect(
            reverse("core:list", args=(lst.id,)) + f"#{str(fighter.id)}"
        )

    # Calculate fighter cost for template
    fighter_cost = fighter.cost_int()

    return render(
        request,
        "core/list_fighter_archive.html",
        {"fighter": fighter, "list": lst, "fighter_cost": fighter_cost},
    )


@login_required
def kill_list_fighter(request, id, fighter_id):
    """
    Mark a :model:`core.ListFighter` as dead in campaign mode.
    This transfers all equipment to the stash and sets cost to 0.

    **Context**

    ``fighter``
        The :model:`core.ListFighter` to be marked as dead.
    ``list``
        The :model:`core.List` that owns this fighter.

    **Template**

    :template:`core/list_fighter_kill.html`
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )

    # Only allow killing fighters in campaign mode
    if not lst.is_campaign_mode:
        messages.error(request, "Fighters can only be killed in campaign mode.")
        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    # Don't allow killing stash fighters
    if fighter.is_stash:
        messages.error(request, "Cannot kill the stash.")
        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    if request.method == "POST":
        # Handle fighter death (transfers equipment, creates ListAction and CampaignAction)
        result = handle_fighter_kill(
            user=request.user,
            lst=lst,
            fighter=fighter,
        )

        # Log the fighter kill event
        log_event(
            user=request.user,
            noun=EventNoun.LIST_FIGHTER,
            verb=EventVerb.DELETE,
            object=fighter,
            request=request,
            fighter_name=fighter.name,
            list_id=str(lst.id),
            list_name=lst.name,
            action="killed",
        )

        messages.success(request, result.description)
        return HttpResponseRedirect(
            reverse("core:list", args=(lst.id,)) + f"#{str(fighter.id)}"
        )

    return render(
        request,
        "core/list_fighter_kill.html",
        {"fighter": fighter, "list": lst},
    )


@login_required
def resurrect_list_fighter(request, id, fighter_id):
    """
    Change the status of a :model:`core.ListFighter` from dead to alive in campaign mode.
    This sets cost to the original value of the fighter, but does not
    restore equipment transferred to the stash when the fighter was killed.

    **Context**

    ``fighter``
        The dead :model:`core.ListFighter` to be marked as alive.
    ``list``
        The :model:`core.List` that owns this fighter.

    **Template**

    :template:`core/list_fighter_resurrect.html`
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )

    if not lst.is_campaign_mode:
        messages.error(request, "Fighters can only be resurrected in campaign mode.")
        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    # Don't resurrect stash fighters - just in case
    if fighter.is_stash:
        messages.error(request, "Cannot resurrect the stash.")
        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    if request.method == "POST":
        if fighter.injury_state != ListFighter.DEAD:
            messages.error(request, "Only dead fighters can be resurrected.")
            return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

        # Handle resurrection (restores cost, creates ListAction and CampaignAction)
        handle_fighter_resurrect(
            user=request.user,
            fighter=fighter,
        )

        # Log the resurrection event
        log_event(
            user=request.user,
            noun=EventNoun.LIST_FIGHTER,
            verb=EventVerb.ACTIVATE,
            object=fighter,
            request=request,
            fighter_name=fighter.name,
            list_id=str(lst.id),
            list_name=lst.name,
            action="resurrected",
        )

        messages.success(
            request,
            f"{fighter.name} has been resurrected. They can now be re-equipped from the stash.",
        )

        return HttpResponseRedirect(
            reverse("core:list", args=(lst.id,)) + f"#{str(fighter.id)}"
        )

    return render(
        request, "core/list_fighter_resurrect.html", {"fighter": fighter, "list": lst}
    )


@login_required
def delete_list_fighter(request, id, fighter_id):
    """
    Delete a :model:`core.ListFighter`.

    **Context**

    ``fighter``
        The :model:`core.ListFighter` to be deleted.
    ``list``
        The :model:`core.List` that owns this fighter.

    **Template**

    :template:`core/list_fighter_delete.html`
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )

    if request.method == "POST":
        # Store fighter name for logging before handler deletes it
        fighter_name = fighter.name

        # Log the fighter delete event before deletion
        log_event(
            user=request.user,
            noun=EventNoun.LIST_FIGHTER,
            verb=EventVerb.DELETE,
            object=fighter,
            request=request,
            fighter_name=fighter_name,
            list_id=str(lst.id),
            list_name=lst.name,
        )

        # Call handler to perform business logic
        handle_fighter_deletion(
            user=request.user,
            lst=lst,
            fighter=fighter,
            request_refund=request.POST.get("refund") == "on",
        )

        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    # Calculate fighter cost for template
    fighter_cost = fighter.cost_int()

    return render(
        request,
        "core/list_fighter_delete.html",
        {"fighter": fighter, "list": lst, "fighter_cost": fighter_cost},
    )


@xframe_options_exempt
def embed_list_fighter(request, id, fighter_id):
    """
    Display a single :model:`core.ListFighter` object in an embedded view.

    **Context**

    ``fighter``
        The requested :model:`core.ListFighter` object.
    ``list``
        The :model:`core.List` that owns this fighter.

    **Template**

    :template:`core/list_fighter_embed.html`
    """
    lst = get_clean_list_or_404(List, id=id)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )

    # Log the embed view event
    log_event(
        user=request.user
        if hasattr(request, "user") and request.user.is_authenticated
        else None,
        noun=EventNoun.LIST_FIGHTER,
        verb=EventVerb.VIEW,
        object=fighter,
        request=request,
        list_id=str(lst.id),
        list_name=lst.name,
        fighter_id=str(fighter.id),
        fighter_name=fighter.name,
        embed=True,
    )

    return render(
        request,
        "core/list_fighter_embed.html",
        {"fighter": fighter, "list": lst},
    )


class ListArchivedFightersView(generic.ListView):
    """
    Display a page with archived :model:`core.ListFighter` objects within a given :model:`core.List`.

    **Context**

    ``list``
        The requested :model:`core.List` object (retrieved by ID).

    **Template**

    :template:`core/list_archived_fighters.html`
    """

    template_name = "core/list_archived_fighters.html"
    context_object_name = "list"

    def get_queryset(self):
        """
        Retrieve the :model:`core.List` by its `id`, ensuring it's owned by the current user.
        """
        return get_object_or_404(List, id=self.kwargs["id"], owner=self.request.user)


@login_required
def list_fighter_injuries_edit(request, id, fighter_id):
    """
    Edit injuries for a :model:`core.ListFighter` in campaign mode.

    **Context**

    ``fighter``
        The :model:`core.ListFighter` whose injuries are being managed.
    ``list``
        The :model:`core.List` that owns this fighter.

    **Template**

    :template:`core/list_fighter_injuries_edit.html`
    """

    lst = get_clean_list_or_404(
        List.objects.with_related_data(), id=id, owner=request.user
    )
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )

    # Check campaign mode
    if lst.status != List.CAMPAIGN_MODE:
        messages.error(
            request, "Injuries can only be managed for fighters in campaign mode."
        )
        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    return render(
        request,
        "core/list_fighter_injuries_edit.html",
        {
            "list": lst,
            "fighter": fighter,
        },
    )


@login_required
def list_fighter_state_edit(request, id, fighter_id):
    """
    Edit the injury state of a :model:`core.ListFighter` in campaign mode.

    **Context**

    ``form``
        An EditFighterStateForm for changing the fighter's state.
    ``fighter``
        The :model:`core.ListFighter` whose state is being changed.
    ``list``
        The :model:`core.List` that owns this fighter.

    **Template**

    :template:`core/list_fighter_state_edit.html`
    """

    from gyrinx.core.models.campaign import CampaignAction

    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )

    # Check campaign mode
    if lst.status != List.CAMPAIGN_MODE:
        messages.error(request, "Fighter state can only be managed in campaign mode.")
        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    if request.method == "POST":
        form = EditFighterStateForm(request.POST, fighter=fighter)
        if form.is_valid():
            old_state = fighter.get_injury_state_display()
            new_state = form.cleaned_data["fighter_state"]

            # Only update if state actually changed
            if fighter.injury_state != new_state:
                # If changing to dead state, redirect to kill confirmation instead
                if new_state == ListFighter.DEAD:
                    # Don't save the state change here - let the kill view handle it
                    return HttpResponseRedirect(
                        reverse("core:list-fighter-kill", args=(lst.id, fighter.id))
                    )
                # If resurrecting from dead to active, redirect to resurrect confirmation
                elif (
                    new_state == ListFighter.ACTIVE
                    and fighter.injury_state == ListFighter.DEAD
                ):
                    # Don't save the state change here - let the resurrect view handle it
                    return HttpResponseRedirect(
                        reverse(
                            "core:list-fighter-resurrect", args=(lst.id, fighter.id)
                        )
                    )

                with transaction.atomic():
                    fighter.injury_state = new_state
                    fighter.save()

                    new_state_display = dict(ListFighter.INJURY_STATE_CHOICES)[
                        new_state
                    ]

                    # Log to campaign action
                    if lst.campaign:
                        description = f"State Change: {fighter.name} changed from {old_state} to {new_state_display}"
                        if form.cleaned_data.get("reason"):
                            description += f" - {form.cleaned_data['reason']}"

                        CampaignAction.objects.create(
                            user=request.user,
                            owner=request.user,
                            campaign=lst.campaign,
                            list=lst,
                            description=description,
                            outcome=f"{fighter.name} is now {new_state_display}",
                        )

                messages.success(
                    request, f"Updated {fighter.name}'s state to {new_state_display}"
                )
            else:
                messages.info(request, "Fighter state was not changed.")

            return HttpResponseRedirect(
                reverse("core:list-fighter-injuries-edit", args=(lst.id, fighter.id))
            )
    else:
        form = EditFighterStateForm(fighter=fighter)

    return render(
        request,
        "core/list_fighter_state_edit.html",
        {
            "form": form,
            "list": lst,
            "fighter": fighter,
        },
    )


@login_required
def mark_fighter_captured(request, id, fighter_id):
    """
    Mark a fighter as captured by another gang in the campaign.

    **Context**

    ``fighter``
        The :model:`core.ListFighter` being captured.
    ``list``
        The :model:`core.List` that owns this fighter.
    ``capturing_lists``
        Other gangs in the campaign that can capture this fighter.
    ``campaign``
        The :model:`core.Campaign` the lists belong to.

    **Template**

    :template:`core/list_fighter_mark_captured.html`
    """

    from gyrinx.core.handlers.fighter.capture import handle_fighter_capture

    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )

    # Check campaign mode
    if lst.status != List.CAMPAIGN_MODE:
        messages.error(request, "Fighters can only be captured in campaign mode.")
        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    # Check if fighter is already captured or sold
    if fighter.is_captured or fighter.is_sold_to_guilders:
        messages.error(request, "This fighter is already captured or sold.")
        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    # Check if fighter is dead
    if fighter.injury_state == ListFighter.DEAD:
        messages.error(request, "Dead fighters cannot be captured.")
        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    # Get the campaign
    campaign = lst.campaign
    if not campaign:
        messages.error(request, "This list is not part of a campaign.")
        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    # Get other lists in the campaign that could capture this fighter
    capturing_lists = (
        campaign.campaign_lists.filter(status=List.CAMPAIGN_MODE)
        .exclude(id=lst.id)
        .order_by("name")
    )

    if not capturing_lists.exists():
        messages.error(
            request, "No other gangs in the campaign to capture this fighter."
        )
        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    if request.method == "POST":
        capturing_list_id = request.POST.get("capturing_list")
        if capturing_list_id:
            capturing_list = get_object_or_404(
                List, id=capturing_list_id, campaign=campaign
            )

            # Call the capture handler
            result = handle_fighter_capture(
                user=request.user,
                fighter=fighter,
                capturing_list=capturing_list,
            )

            # Show messages for removed equipment
            for assignment_id, equipment_cost in result.equipment_removed:
                messages.info(
                    request,
                    f"Linked equipment removed due to capture ({equipment_cost}¢).",
                )

            # Log the capture event
            log_event(
                user=request.user,
                noun=EventNoun.LIST_FIGHTER,
                verb=EventVerb.UPDATE,
                object=fighter,
                request=request,
                fighter_name=fighter.name,
                list_id=str(lst.id),
                list_name=lst.name,
                action="captured",
                capturing_list_name=capturing_list.name,
                capturing_list_id=str(capturing_list.id),
            )

            messages.success(
                request,
                f"{fighter.name} has been marked as captured by {capturing_list.name}.",
            )
            return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    return render(
        request,
        "core/list_fighter_mark_captured.html",
        {
            "fighter": fighter,
            "list": lst,
            "capturing_lists": capturing_lists,
            "campaign": campaign,
        },
    )


@login_required
def list_fighter_add_injury(request, id, fighter_id):
    """
    Add an injury to a :model:`core.ListFighter` in campaign mode.

    **Context**

    ``form``
        An AddInjuryForm for selecting the injury to add.
    ``fighter``
        The :model:`core.ListFighter` being injured.
    ``list``
        The :model:`core.List` that owns this fighter.

    **Template**

    :template:`core/list_fighter_add_injury.html`
    """

    from gyrinx.core.models.campaign import CampaignAction

    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )

    # Check campaign mode
    if lst.status != List.CAMPAIGN_MODE:
        messages.error(
            request, "Injuries can only be added to fighters in campaign mode."
        )
        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    if request.method == "POST":
        form = AddInjuryForm(request.POST, fighter=fighter)
        if form.is_valid():
            with transaction.atomic():
                injury = ListFighterInjury.objects.create_with_user(
                    user=request.user,
                    fighter=fighter,
                    injury=form.cleaned_data["injury"],
                    notes=form.cleaned_data.get("notes", ""),
                    owner=request.user,
                )

                # Update fighter state
                fighter.injury_state = form.cleaned_data["fighter_state"]
                fighter.save()

                # Log to campaign action
                if lst.campaign:
                    # Use the correct injury/damage term from the fighter's terminology
                    description = f"{fighter.term_injury_singular}: {fighter.name} suffered {injury.injury.name}"
                    if form.cleaned_data.get("notes"):
                        description += f" - {form.cleaned_data['notes']}"

                    # Update outcome to show fighter state
                    fighter_state_display = dict(ListFighter.INJURY_STATE_CHOICES)[
                        fighter.injury_state
                    ]
                    outcome = f"{fighter.name} was put into {fighter_state_display}"

                    CampaignAction.objects.create(
                        user=request.user,
                        owner=request.user,
                        campaign=lst.campaign,
                        list=lst,
                        description=description,
                        outcome=outcome,
                    )

                # Log the injury event
                log_event(
                    user=request.user,
                    noun=EventNoun.LIST_FIGHTER,
                    verb=EventVerb.UPDATE,
                    object=fighter,
                    request=request,
                    fighter_name=fighter.name,
                    list_id=str(lst.id),
                    list_name=lst.name,
                    action="injury_added",
                    injury_name=injury.injury.name,
                    injury_state=fighter.injury_state,
                )

            messages.success(
                request, f"Added injury '{injury.injury.name}' to {fighter.name}"
            )

            # If fighter state is dead, redirect to kill confirmation
            if form.cleaned_data["fighter_state"] == ListFighter.DEAD:
                return HttpResponseRedirect(
                    reverse("core:list-fighter-kill", args=(lst.id, fighter.id))
                )

            return HttpResponseRedirect(
                reverse("core:list-fighter-injuries-edit", args=(lst.id, fighter.id))
            )
    else:
        form = AddInjuryForm(fighter=fighter)

    return render(
        request,
        "core/list_fighter_add_injury.html",
        {
            "form": form,
            "list": lst,
            "fighter": fighter,
        },
    )


@login_required
def list_fighter_remove_injury(request, id, fighter_id, injury_id):
    """
    Remove an injury from a :model:`core.ListFighter` in campaign mode.

    **Context**

    ``injury``
        The :model:`core.ListFighterInjury` to be removed.
    ``fighter``
        The :model:`core.ListFighter` being healed.
    ``list``
        The :model:`core.List` that owns this fighter.

    **Template**

    :template:`core/list_fighter_remove_injury.html`
    """

    from gyrinx.core.models.campaign import CampaignAction

    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )
    injury = get_object_or_404(ListFighterInjury, id=injury_id, fighter=fighter)

    if request.method == "POST":
        with transaction.atomic():
            injury_name = injury.injury.name
            injury.delete()

            # Clear the prefetch cache to get accurate count
            fighter._prefetched_objects_cache = {}

            # If fighter has no more injuries, reset state to active
            if fighter.injuries.count() == 0:
                fighter.injury_state = ListFighter.ACTIVE
                fighter.save()
                outcome = "Fighter became available"
            else:
                outcome = "Injury removed"

            # Log to campaign action
            if lst.campaign:
                # Use the fighter's recovery terminology
                recovery_term = fighter.term_recovery_singular
                CampaignAction.objects.create(
                    user=request.user,
                    owner=request.user,
                    campaign=lst.campaign,
                    list=lst,
                    description=f"{recovery_term}: {fighter.name} recovered from {injury_name}",
                    outcome=outcome,
                )

            # Log the injury removal event
            log_event(
                user=request.user,
                noun=EventNoun.LIST_FIGHTER,
                verb=EventVerb.UPDATE,
                object=fighter,
                request=request,
                fighter_name=fighter.name,
                list_id=str(lst.id),
                list_name=lst.name,
                action="injury_removed",
                injury_name=injury_name,
                injury_state=fighter.injury_state,
            )

        messages.success(request, f"Removed injury '{injury_name}' from {fighter.name}")
        return HttpResponseRedirect(
            reverse("core:list-fighter-injuries-edit", args=(lst.id, fighter.id))
        )

    return render(
        request,
        "core/list_fighter_remove_injury.html",
        {
            "injury": injury,
            "fighter": fighter,
            "list": lst,
        },
    )


@login_required
def edit_list_fighter_xp(request, id, fighter_id):
    """
    Modify XP for a :model:`core.ListFighter` in campaign mode.

    **Context**

    ``form``
        An EditFighterXPForm for modifying fighter XP.
    ``fighter``
        The :model:`core.ListFighter` whose XP is being modified.
    ``list``
        The :model:`core.List` that owns this fighter.

    **Template**

    :template:`core/list_fighter_xp_edit.html`
    """

    from gyrinx.core.forms.list import EditFighterXPForm
    from gyrinx.core.models.campaign import CampaignAction

    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter, id=fighter_id, list=lst, archived_at__isnull=True
    )

    if request.method == "POST":
        form = EditFighterXPForm(request.POST, fighter=fighter)
        if form.is_valid():
            operation = form.cleaned_data["operation"]
            amount = form.cleaned_data["amount"]
            description = form.cleaned_data.get("description", "")

            # Validate the operation
            if operation == "spend" and amount > fighter.xp_current:
                form.add_error(
                    "amount",
                    f"Cannot spend more XP than available ({fighter.xp_current})",
                )
            elif operation == "reduce" and amount > fighter.xp_current:
                form.add_error(
                    "amount",
                    f"Cannot reduce XP below zero (current: {fighter.xp_current})",
                )
            elif operation == "reduce" and amount > fighter.xp_total:
                form.add_error(
                    "amount",
                    f"Cannot reduce total XP below zero (total: {fighter.xp_total})",
                )
            else:
                with transaction.atomic():
                    # Apply the XP change
                    if operation == "add":
                        fighter.xp_current += amount
                        fighter.xp_total += amount
                        action_desc = f"Added {amount} XP for {fighter.name}"
                    elif operation == "spend":
                        fighter.xp_current -= amount
                        action_desc = f"Spent {amount} XP for {fighter.name}"
                    elif operation == "reduce":
                        fighter.xp_current -= amount
                        fighter.xp_total -= amount
                        action_desc = f"Reduced {amount} XP for {fighter.name}"

                    fighter.save_with_user(user=request.user)

                    # Add description if provided
                    if description:
                        action_desc += f" - {description}"

                    # Log to campaign action
                    if lst.campaign:
                        outcome = f"Current: {fighter.xp_current} XP, Total: {fighter.xp_total} XP"
                        CampaignAction.objects.create(
                            user=request.user,
                            owner=request.user,
                            campaign=lst.campaign,
                            list=lst,
                            description=action_desc,
                            outcome=outcome,
                        )

                messages.success(request, f"XP updated for {fighter.name}")
                return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))
    else:
        form = EditFighterXPForm(fighter=fighter)

    return render(
        request,
        "core/list_fighter_xp_edit.html",
        {
            "form": form,
            "list": lst,
            "fighter": fighter,
        },
    )


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


# Fighter Advancement Views
def can_fighter_roll_dice_for_advancement(fighter):
    """Check if a fighter can roll dice for advancement (GANGERs and EXOTIC_BEASTs can)."""
    category = fighter.get_category()
    return category in [
        FighterCategoryChoices.GANGER.value,
        FighterCategoryChoices.EXOTIC_BEAST.value,
    ]


@login_required
def list_fighter_advancements(request, id, fighter_id):
    """
    Display all advancements for a :model:`core.ListFighter`.

    **Context**

    ``fighter``
        The :model:`core.ListFighter` whose advancements are displayed.
    ``list``
        The :model:`core.List` that owns this fighter.
    ``advancements``
        QuerySet of :model:`core.ListFighterAdvancement` for this fighter.

    **Template**

    :template:`core/list_fighter_advancements.html`
    """

    lst = get_clean_list_or_404(List, id=id)
    fighter = get_object_or_404(
        ListFighter, id=fighter_id, list=lst, archived_at__isnull=True
    )

    advancements = ListFighterAdvancement.objects.filter(
        fighter=fighter,
        archived=False,
    ).select_related("skill", "campaign_action")

    return render(
        request,
        "core/list_fighter_advancements.html",
        {
            "list": lst,
            "fighter": fighter,
            "advancements": advancements,
        },
    )


@login_required
def delete_list_fighter_advancement(request, id, fighter_id, advancement_id):
    """
    Delete (archive) a :model:`core.ListFighterAdvancement`.

    This reverses the effects of the advancement:
    - Restores XP to the fighter
    - Reduces rating/stash by cost_increase
    - For stat advancements: stat change disappears (mod system) or recalculates override
    - For skill advancements: removes skill and recalculates category_override
    - For equipment advancements: warns user to remove equipment manually
    - For other advancements: just archives (no side effects)

    **Context**

    ``fighter``
        The :model:`core.ListFighter` whose advancement is being deleted.
    ``list``
        The :model:`core.List` that owns this fighter.
    ``advancement``
        The :model:`core.ListFighterAdvancement` to be deleted.

    **Template**

    :template:`core/list_fighter_advancement_delete.html`
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter, id=fighter_id, list=lst, archived_at__isnull=True
    )
    advancement = get_object_or_404(
        ListFighterAdvancement, id=advancement_id, fighter=fighter, archived=False
    )

    if request.method == "POST":
        try:
            result = handle_fighter_advancement_deletion(
                user=request.user,
                fighter=fighter,
                advancement=advancement,
            )

            # Show warnings if any
            for warning in result.warnings:
                messages.warning(request, warning)

            log_event(
                user=request.user,
                noun=EventNoun.LIST_FIGHTER,
                verb=EventVerb.UPDATE,
                object=fighter,
                request=request,
                fighter_name=fighter.name,
                list_id=str(lst.id),
                list_name=lst.name,
                advancement_type=advancement.advancement_type,
            )

            messages.success(
                request,
                f"Advancement removed: {result.advancement_description}. "
                f"XP restored: {result.xp_restored}.",
            )
        except DjangoValidationError as e:
            messages.error(request, str(e))

        return HttpResponseRedirect(
            reverse("core:list-fighter-advancements", args=(lst.id, fighter.id))
        )

    return render(
        request,
        "core/list_fighter_advancement_delete.html",
        {
            "list": lst,
            "fighter": fighter,
            "advancement": advancement,
        },
    )


@login_required
def list_fighter_advancement_start(request, id, fighter_id):
    """
    Redirect to the appropriate advancement flow entry point.
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter, id=fighter_id, list=lst, archived_at__isnull=True
    )

    # Redirect to dice choice
    return HttpResponseRedirect(
        reverse("core:list-fighter-advancement-dice-choice", args=(lst.id, fighter.id))
    )


@login_required
def list_fighter_advancement_dice_choice(request, id, fighter_id):
    """
    Choose whether to roll 2d6 for advancement.

    **Context**

    ``form``
        An AdvancementDiceChoiceForm.
    ``fighter``
        The :model:`core.ListFighter` purchasing the advancement.
    ``list``
        The :model:`core.List` that owns this fighter.

    **Template**

    :template:`core/list_fighter_advancement_dice_choice.html`
    """

    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter, id=fighter_id, list=lst, archived_at__isnull=True
    )

    # TODO: This should be removed once ListActions are implemented, so that dice-rolls for advancements
    # are possible even outside of campaign mode.
    if lst.status != List.CAMPAIGN_MODE:
        url = reverse("core:list-fighter-advancement-type", args=(lst.id, fighter.id))
        return HttpResponseRedirect(url)

    # Check if fighter can roll dice for advancement
    if not can_fighter_roll_dice_for_advancement(fighter):
        url = reverse("core:list-fighter-advancement-type", args=(lst.id, fighter.id))
        return HttpResponseRedirect(url)

    if request.method == "POST":
        form = AdvancementDiceChoiceForm(request.POST)
        if form.is_valid():
            roll_dice = form.cleaned_data["roll_dice"]

            if roll_dice:
                with transaction.atomic():
                    # Roll 2d6 and create campaign action
                    dice1 = random.randint(1, 6)
                    dice2 = random.randint(1, 6)
                    total = dice1 + dice2

                    # Create campaign action for the roll if in campaign mode
                    campaign_action = None
                    if lst.status == List.CAMPAIGN_MODE and lst.campaign:
                        campaign_action = CampaignAction.objects.create(
                            user=request.user,
                            owner=request.user,
                            campaign=lst.campaign,
                            list=lst,
                            description=f"Rolling for advancement to {fighter.name}",
                            dice_count=2,
                            dice_results=[dice1, dice2],
                            dice_total=total,
                        )

                # Redirect to type selection with campaign action
                url = reverse(
                    "core:list-fighter-advancement-type", args=(lst.id, fighter.id)
                )
                if campaign_action:
                    return HttpResponseRedirect(
                        f"{url}?campaign_action_id={campaign_action.id}"
                    )
                else:
                    return HttpResponseRedirect(url)
            else:
                # Redirect to type selection without campaign action
                return HttpResponseRedirect(
                    reverse(
                        "core:list-fighter-advancement-type", args=(lst.id, fighter.id)
                    )
                )
    else:
        form = AdvancementDiceChoiceForm()

    return render(
        request,
        "core/list_fighter_advancement_dice_choice.html",
        {
            "form": form,
            "fighter": fighter,
            "list": lst,
            "can_roll_dice": can_fighter_roll_dice_for_advancement(fighter),
            "fighter_category": fighter.get_category_label(),
        },
    )


def filter_equipment_assignments_for_duplicates(equipment_advancement, fighter):
    """
    Filter equipment advancement assignments to exclude those with upgrades
    that the fighter already has on their equipment.

    Args:
        equipment_advancement: ContentAdvancementEquipment instance
        fighter: ListFighter instance

    Returns:
        QuerySet of ContentAdvancementAssignment objects that don't have duplicate upgrades
    """
    from gyrinx.core.models import ListFighterEquipmentAssignment

    # Get all assignments from the advancement
    available_assignments = equipment_advancement.assignments.all()

    # Get all upgrade IDs from the fighter's existing equipment assignments
    existing_upgrade_ids = set(
        ListFighterEquipmentAssignment.objects.filter(
            list_fighter=fighter, archived=False
        ).values_list("upgrades_field", flat=True)
    )
    # Remove None values if any
    existing_upgrade_ids.discard(None)

    # Filter out assignments that have any upgrade matching existing upgrades
    if existing_upgrade_ids:
        # Exclude assignments that have any of the existing upgrades
        available_assignments = available_assignments.exclude(
            upgrades_field__in=existing_upgrade_ids
        ).distinct()

    return available_assignments


class AdvancementBaseParams(BaseModel):
    # UUID of the campaign action if dice were rolled
    campaign_action_id: Optional[uuid.UUID] = None


class AdvancementFlowParams(AdvancementBaseParams):
    # Type of advancement being selected (e.g., "stat_strength", "skill_primary_random")
    advancement_choice: str
    # Spend XP cost for this advancement
    xp_cost: int = 0
    # Fighter cost increase from this advancement
    cost_increase: int = 0
    # Free text description for "other" advancement types
    description: Optional[str] = None

    @field_validator("advancement_choice")
    @classmethod
    def validate_advancement_choice(cls, value: str) -> str:
        if value not in AdvancementTypeForm.all_advancement_choices().keys():
            raise ValueError("Invalid advancement type choice.")
        return value

    def is_stat_advancement(self) -> bool:
        """
        Check if this is a stat advancement.
        """
        return self.advancement_choice.startswith("stat_")

    def is_skill_advancement(self) -> bool:
        """
        Check if this is a skill advancement.
        """
        return self.advancement_choice in [
            "skill_primary_chosen",
            "skill_secondary_chosen",
            "skill_primary_random",
            "skill_secondary_random",
            "skill_promote_specialist",
            "skill_any_random",
        ]

    def is_equipment_advancement(self) -> bool:
        """
        Check if this is an equipment advancement.
        """
        return self.advancement_choice.startswith("equipment_")

    def is_equipment_random_advancement(self) -> bool:
        """
        Check if this is a random equipment advancement.
        """
        return self.advancement_choice.startswith("equipment_random_")

    def is_equipment_chosen_advancement(self) -> bool:
        """
        Check if this is a chosen equipment advancement.
        """
        return self.advancement_choice.startswith("equipment_chosen_")

    def get_equipment_advancement_id(self) -> str:
        """
        Extract the equipment advancement ID from the choice.
        """
        if self.is_equipment_advancement():
            # Format is "equipment_[random|chosen]_<uuid>"
            parts = self.advancement_choice.split("_", 2)
            if len(parts) >= 3:
                return parts[2]
        raise ValueError("Not an equipment advancement choice.")

    def is_other_advancement(self) -> bool:
        """
        Check if this is an 'other' free text advancement.
        """
        return self.advancement_choice == "other"

    def is_chosen_skill_advancement(self) -> bool:
        """
        Check if this is a chosen skill advancement.
        """
        return self.advancement_choice in [
            "skill_primary_chosen",
            "skill_secondary_chosen",
        ]

    def is_random_skill_advancement(self) -> bool:
        """
        Check if this is a random skill advancement.
        """
        return self.advancement_choice in [
            "skill_primary_random",
            "skill_secondary_random",
            "skill_promote_specialist",
            "skill_any_random",
        ]

    def is_promote_advancement(self) -> bool:
        """
        Check if this is a specialist promotion advancement.
        """
        return self.advancement_choice in [
            "skill_promote_specialist",
            "skill_promote_champion",
        ]

    def skill_category_from_choice(self) -> Literal["primary", "secondary", "any"]:
        """
        Extract the skill category from the advancement choice.
        """
        if self.is_skill_advancement():
            if self.advancement_choice in [
                "skill_primary_chosen",
                "skill_primary_random",
                "skill_promote_specialist",
            ]:
                return "primary"
            elif self.advancement_choice in [
                "skill_secondary_chosen",
                "skill_secondary_random",
            ]:
                return "secondary"
            elif self.advancement_choice == "skill_any_random":
                return "any"

        raise ValueError("Not a skill advancement choice.")

    def stat_from_choice(self) -> str:
        """
        Extract the stat from the advancement choice.
        """
        if self.is_stat_advancement():
            return self.advancement_choice.split("_", 1)[1]

        raise ValueError("Not a stat advancement choice.")

    def description_from_choice(self) -> str:
        """
        Get the description for the advancement based on the choice.
        """
        if self.is_stat_advancement():
            return AdvancementTypeForm.all_stat_choices().get(
                self.advancement_choice, "Unknown"
            )

        if self.is_equipment_advancement():
            return AdvancementTypeForm.all_equipment_choices().get(
                self.advancement_choice, "Unknown"
            )

        # For other advancement types, use the full list
        return AdvancementTypeForm.all_advancement_choices().get(
            self.advancement_choice, "Unknown"
        )


@login_required
def list_fighter_advancement_type(request, id, fighter_id):
    """
    Select the type of advancement and costs.

    **Context**

    ``form``
        An AdvancementTypeForm.
    ``fighter``
        The :model:`core.ListFighter` purchasing the advancement.
    ``list``
        The :model:`core.List` that owns this fighter.
    ``campaign_action``
        Optional CampaignAction if dice were rolled.

    **Template**

    :template:`core/list_fighter_advancement_type.html`
    """

    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter, id=fighter_id, list=lst, archived_at__isnull=True
    )

    is_campaign_mode = lst.status == List.CAMPAIGN_MODE

    params = AdvancementBaseParams.model_validate(request.GET.dict())
    # Get campaign action if provided
    campaign_action = None
    if params.campaign_action_id:
        campaign_action = get_object_or_404(
            CampaignAction, id=params.campaign_action_id
        )

    if request.method == "POST":
        form = AdvancementTypeForm(request.POST, fighter=fighter)
        if form.is_valid():
            next_params = AdvancementFlowParams.model_validate(form.cleaned_data)

            # Check if this is a stat advancement - go directly to confirm
            if next_params.is_stat_advancement():
                url = reverse(
                    "core:list-fighter-advancement-confirm", args=(lst.id, fighter.id)
                )
                return HttpResponseRedirect(
                    f"{url}?{urlencode(next_params.model_dump(mode='json', exclude_none=True))}"
                )
            elif next_params.is_other_advancement():
                # For "other" advancements, go to the other view
                url = reverse(
                    "core:list-fighter-advancement-other", args=(lst.id, fighter.id)
                )
                return HttpResponseRedirect(
                    f"{url}?{urlencode(next_params.model_dump(mode='json', exclude_none=True))}"
                )
            elif (
                next_params.is_equipment_advancement()
                and "_random_" in next_params.advancement_choice
            ):
                # For random equipment advancements, go straight to confirm
                url = reverse(
                    "core:list-fighter-advancement-confirm", args=(lst.id, fighter.id)
                )
                return HttpResponseRedirect(
                    f"{url}?{urlencode(next_params.model_dump(mode='json', exclude_none=True))}"
                )
            else:
                # For skills and chosen equipment, still need selection step
                url = reverse(
                    "core:list-fighter-advancement-select", args=(lst.id, fighter.id)
                )
                return HttpResponseRedirect(
                    f"{url}?{urlencode(next_params.model_dump(mode='json', exclude_none=True))}"
                )
    else:
        initial = {
            **params.model_dump(mode="json", exclude_none=True),
            **AdvancementTypeForm.get_initial_for_action(campaign_action),
        }
        form = AdvancementTypeForm(initial=initial, fighter=fighter)

    return render(
        request,
        "core/list_fighter_advancement_type.html",
        {
            "form": form,
            "fighter": fighter,
            "list": lst,
            "campaign_action": campaign_action,
            "is_campaign_mode": is_campaign_mode,
            "steps": 3 if is_campaign_mode else 2,
            "current_step": 2 if is_campaign_mode else 1,
            "progress": 66 if is_campaign_mode else 50,
            "advancement_configs_json": json.dumps(form.get_all_configs_json()),
        },
    )


@login_required
def list_fighter_advancement_confirm(request, id, fighter_id):
    """
    Confirm and create the advancement.

    **Context**

    ``fighter``
        The :model:`core.ListFighter` purchasing the advancement.
    ``list``
        The :model:`core.List` that owns this fighter.
    ``advancement_details``
        Dictionary containing details about the advancement to be created.

    **Template**

    :template:`core/list_fighter_advancement_confirm.html`
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter, id=fighter_id, list=lst, archived_at__isnull=True
    )

    is_campaign_mode = lst.status == List.CAMPAIGN_MODE

    # Get and sanitize parameters from query string
    try:
        params = AdvancementFlowParams.model_validate(request.GET.dict())
        # Allow stat, other, and random equipment advancements at confirm stage
        is_random_equipment = (
            params.is_equipment_advancement()
            and "_random_" in params.advancement_choice
        )
        if not (
            params.is_stat_advancement()
            or params.is_other_advancement()
            or is_random_equipment
        ):
            raise ValueError(
                "Only stat, other, or random equipment advancements allowed at the confirm stage"
            )

        if params.is_stat_advancement():
            stat = params.stat_from_choice()
            stat_desc = params.description_from_choice()
        elif params.is_other_advancement():
            stat = None
            stat_desc = params.description
        elif is_random_equipment:
            # For random equipment, prepare the details
            stat = None
            stat_desc = params.description_from_choice()
    except ValueError as e:
        messages.error(request, f"Invalid advancement: {e}.")
        return HttpResponseRedirect(
            reverse("core:list-fighter-advancement-type", args=(lst.id, fighter.id))
        )

    if request.method == "POST":
        # Prepare type-specific parameters for the handler
        selected_assignment = None
        equipment_description = None

        if is_random_equipment:
            # For random equipment, select the assignment before calling handler
            try:
                advancement_id = params.get_equipment_advancement_id()
                equipment_advancement = ContentAdvancementEquipment.objects.get(
                    id=advancement_id
                )

                # Randomly select assignment, filtering out duplicates
                available_assignments = filter_equipment_assignments_for_duplicates(
                    equipment_advancement, fighter
                )
                if not available_assignments.exists():
                    error_msg = (
                        f"No available options from {equipment_advancement.name}. "
                    )
                    raise ValueError(error_msg)

                selected_assignment = available_assignments.order_by("?").first()
                equipment_description = (
                    f"Random {equipment_advancement.name}: {selected_assignment}"
                )
            except (ValueError, ContentAdvancementEquipment.DoesNotExist) as e:
                messages.error(request, f"Invalid equipment advancement: {e}")
                return HttpResponseRedirect(
                    reverse(
                        "core:list-fighter-advancement-type",
                        args=(lst.id, fighter.id),
                    )
                )

        # Call the handler
        try:
            if params.is_stat_advancement():
                result = handle_fighter_advancement(
                    user=request.user,
                    fighter=fighter,
                    advancement_type=ListFighterAdvancement.ADVANCEMENT_STAT,
                    xp_cost=params.xp_cost,
                    cost_increase=params.cost_increase,
                    advancement_choice=params.advancement_choice,
                    stat_increased=stat,
                    campaign_action_id=params.campaign_action_id,
                )
            elif params.is_other_advancement():
                result = handle_fighter_advancement(
                    user=request.user,
                    fighter=fighter,
                    advancement_type=ListFighterAdvancement.ADVANCEMENT_OTHER,
                    xp_cost=params.xp_cost,
                    cost_increase=params.cost_increase,
                    advancement_choice=params.advancement_choice,
                    description=stat_desc,
                    campaign_action_id=params.campaign_action_id,
                )
            elif is_random_equipment:
                result = handle_fighter_advancement(
                    user=request.user,
                    fighter=fighter,
                    advancement_type=ListFighterAdvancement.ADVANCEMENT_EQUIPMENT,
                    xp_cost=params.xp_cost,
                    cost_increase=params.cost_increase,
                    advancement_choice=params.advancement_choice,
                    equipment_assignment=selected_assignment,
                    description=equipment_description,
                    campaign_action_id=params.campaign_action_id,
                )
        except DjangoValidationError as e:
            messages.validation(request, e)
            return HttpResponseRedirect(
                reverse("core:list-fighter-advancement-type", args=(lst.id, fighter.id))
            )

        # Handle idempotent case (already applied)
        if result is None:
            messages.info(request, "Advancement already applied.")
            return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

        # Log the advancement event
        log_event(
            user=request.user,
            noun=EventNoun.LIST_FIGHTER,
            verb=EventVerb.UPDATE,
            object=fighter,
            request=request,
            fighter_name=fighter.name,
            list_id=str(lst.id),
            list_name=lst.name,
            action="advancement_applied",
            advancement_type=result.advancement.advancement_type,
            advancement_detail=stat_desc,
            xp_cost=params.xp_cost,
            cost_increase=params.cost_increase,
        )

        messages.success(
            request,
            f"Advanced: {fighter.name} - {result.outcome}",
        )

        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    steps = 3
    if not is_campaign_mode and not params.is_other_advancement():
        steps = 2

    # Prepare context based on advancement type
    context = {
        "fighter": fighter,
        "list": lst,
        "details": {
            **params.model_dump(),
            "stat": stat,
            "description": stat_desc,
        },
        "is_campaign_mode": is_campaign_mode,
        "steps": steps,
        "current_step": steps,
    }

    # Add equipment-specific context for random equipment
    if is_random_equipment:
        context["advancement_type"] = "equipment"
        context["is_random"] = True
        # Get the equipment advancement name for display
        try:
            advancement_id = params.get_equipment_advancement_id()
            equipment_advancement = ContentAdvancementEquipment.objects.get(
                id=advancement_id
            )
            context["advancement_name"] = equipment_advancement.name
        except (ValueError, ContentAdvancementEquipment.DoesNotExist):
            context["advancement_name"] = "Equipment"

    return render(
        request,
        "core/list_fighter_advancement_confirm.html",
        context,
    )


def apply_skill_advancement(
    request: HttpRequest,
    lst: List,
    fighter: ListFighter,
    skill: ContentSkill,
    params: AdvancementFlowParams,
) -> ListFighterAdvancement | None:
    """
    Apply a skill advancement to a fighter using the handler.

    Returns the advancement if created, or None if already applied (idempotent)
    or if a validation error occurred.
    """
    try:
        result = handle_fighter_advancement(
            user=request.user,
            fighter=fighter,
            advancement_type=ListFighterAdvancement.ADVANCEMENT_SKILL,
            xp_cost=params.xp_cost,
            cost_increase=params.cost_increase,
            advancement_choice=params.advancement_choice,
            skill=skill,
            campaign_action_id=params.campaign_action_id,
        )
    except DjangoValidationError as e:
        messages.validation(request, e)
        return None

    if result is None:
        # Idempotent case - already applied
        messages.info(request, "Advancement already applied.")
        return None

    # Log the skill advancement event
    log_event(
        user=request.user,
        noun=EventNoun.LIST_FIGHTER,
        verb=EventVerb.UPDATE,
        object=fighter,
        request=request,
        fighter_name=fighter.name,
        list_id=str(lst.id),
        list_name=lst.name,
        action="skill_advancement_applied",
        skill_name=skill.name,
        xp_cost=params.xp_cost,
        cost_increase=params.cost_increase,
    )

    return result.advancement


@login_required
def list_fighter_advancement_select(request, id, fighter_id):
    """
    Select specific stat or skill based on advancement type.

    **Context**

    ``form``
        StatSelectionForm, SkillSelectionForm, or RandomSkillForm based on type.
    ``fighter``
        The :model:`core.ListFighter` purchasing the advancement.
    ``list``
        The :model:`core.List` that owns this fighter.
    ``advancement_type``
        The type of advancement being selected.

    **Template**

    :template:`core/list_fighter_advancement_select.html`
    """

    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter, id=fighter_id, list=lst, archived_at__isnull=True
    )

    is_campaign_mode = lst.status == List.CAMPAIGN_MODE

    # Get and sanitize parameters from query string, and make sure only skill or equipment advancements
    # reach this stage. Then build the details object.
    try:
        params = AdvancementFlowParams.model_validate(request.GET.dict())
        if not (params.is_skill_advancement() or params.is_equipment_advancement()):
            raise ValueError(
                "Only skill or equipment advancements allowed at the target stage"
            )

        skill_type = (
            params.skill_category_from_choice()
            if params.is_skill_advancement()
            else None
        )
    except ValidationError as e:
        messages.error(request, f"Invalid advancement: {e}.")
        return HttpResponseRedirect(
            reverse("core:list-fighter-advancement-type", args=(lst.id, fighter.id))
        )

    if params.is_equipment_advancement():
        # Handle chosen equipment advancement
        # Note: Random equipment advancements are redirected to confirm view from type view
        from gyrinx.core.forms.advancement import EquipmentAssignmentSelectionForm

        # Get the equipment advancement
        try:
            advancement_id = params.get_equipment_advancement_id()
            advancement = ContentAdvancementEquipment.objects.get(id=advancement_id)
        except (ValueError, ContentAdvancementEquipment.DoesNotExist):
            messages.error(request, "Invalid equipment advancement.")
            return HttpResponseRedirect(
                reverse("core:list-fighter-advancement-type", args=(lst.id, fighter.id))
            )

        # Chosen equipment selection
        if request.method == "POST":
            form = EquipmentAssignmentSelectionForm(
                request.POST, advancement=advancement, fighter=fighter
            )
            if form.is_valid():
                assignment = form.cleaned_data["assignment"]

                # Use the handler to create the advancement
                try:
                    result = handle_fighter_advancement(
                        user=request.user,
                        fighter=fighter,
                        advancement_type=ListFighterAdvancement.ADVANCEMENT_EQUIPMENT,
                        xp_cost=params.xp_cost,
                        cost_increase=params.cost_increase,
                        advancement_choice=params.advancement_choice,
                        equipment_assignment=assignment,
                        description=f"Chosen {advancement.name}: {assignment}",
                        campaign_action_id=params.campaign_action_id,
                    )
                except DjangoValidationError as e:
                    messages.validation(request, e)
                    return HttpResponseRedirect(
                        reverse(
                            "core:list-fighter-advancement-type",
                            args=(lst.id, fighter.id),
                        )
                    )

                if result is None:
                    # Idempotent case - already applied
                    messages.info(request, "Advancement already applied.")
                    return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

                # Log the equipment advancement event
                log_event(
                    user=request.user,
                    noun=EventNoun.LIST_FIGHTER,
                    verb=EventVerb.UPDATE,
                    object=fighter,
                    request=request,
                    fighter_name=fighter.name,
                    list_id=str(lst.id),
                    list_name=lst.name,
                    action="equipment_advancement_applied",
                    equipment_name=str(assignment),
                    xp_cost=params.xp_cost,
                    cost_increase=params.cost_increase,
                )

                messages.success(
                    request,
                    f"Advanced: {fighter.name} has gained {assignment}",
                )

                return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))
        else:
            form = EquipmentAssignmentSelectionForm(
                advancement=advancement, fighter=fighter
            )

    elif params.is_chosen_skill_advancement():
        # Chosen skill
        if request.method == "POST":
            form = SkillSelectionForm(
                request.POST, fighter=fighter, skill_type=skill_type
            )
            if form.is_valid():
                skill = form.cleaned_data["skill"]

                advancement = apply_skill_advancement(
                    request,
                    lst,
                    fighter,
                    skill,
                    params,
                )

                if advancement:
                    messages.success(
                        request,
                        f"Advanced: {fighter.name} has gained {skill.name} skill",
                    )

                return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))
        else:
            form = SkillSelectionForm(fighter=fighter, skill_type=skill_type)

    elif params.is_random_skill_advancement():
        if request.method == "POST":
            form = SkillCategorySelectionForm(
                request.POST, fighter=fighter, skill_type=skill_type
            )
            if form.is_valid():
                category = form.cleaned_data["category"]

                # Auto-select a random skill from the category
                existing_skills = fighter.skills.all()
                available_skills = ContentSkill.objects.filter(
                    category=category
                ).exclude(id__in=existing_skills.values_list("id", flat=True))

                if available_skills.exists():
                    # Pick a random skill from the available ones
                    random_skill = available_skills.order_by("?").first()

                    advancement = apply_skill_advancement(
                        request,
                        lst,
                        fighter,
                        random_skill,
                        params,
                    )

                    if advancement:
                        messages.success(
                            request,
                            f"Advanced: {fighter.name} has gained {random_skill.name} skill",
                        )

                    return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))
                else:
                    # No available skills - show error
                    form.add_error(None, "No available skills in this category.")
        else:
            form = SkillCategorySelectionForm(fighter=fighter, skill_type=skill_type)

    else:
        messages.error(
            request,
            "Sorry, something went really wrong with the advancement. Try again.",
        )
        return HttpResponseRedirect(
            reverse("core:list-fighter-advancement-type", args=(lst.id, fighter.id))
        )

    # Prepare context based on advancement type
    context = {
        "form": form,
        "fighter": fighter,
        "list": lst,
        "is_campaign_mode": is_campaign_mode,
        "steps": 3 if is_campaign_mode else 2,
        "current_step": 3 if is_campaign_mode else 2,
    }

    if params.is_equipment_advancement():
        context.update(
            {
                "advancement_type": "equipment",
                "is_random": False,  # Random equipment goes to confirm, not here
                "advancement_name": advancement.name
                if "advancement" in locals()
                else None,
            }
        )
    else:
        context.update(
            {
                "advancement_type": "skill",
                "skill_type": skill_type,
                "is_random": params.is_random_skill_advancement(),
            }
        )

    return render(
        request,
        "core/list_fighter_advancement_select.html",
        context,
    )


@login_required
def list_fighter_advancement_other(request, id, fighter_id):
    """
    Enter a free text description for an 'other' advancement.

    **Context**

    ``form``
        An OtherAdvancementForm.
    ``fighter``
        The :model:`core.ListFighter` purchasing the advancement.
    ``list``
        The :model:`core.List` that owns this fighter.
    ``params``
        The AdvancementFlowParams from previous steps.

    **Template**

    :template:`core/list_fighter_advancement_other.html`
    """

    from gyrinx.core.forms.advancement import OtherAdvancementForm

    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter, id=fighter_id, list=lst, archived_at__isnull=True
    )

    # Get parameters from query string
    try:
        params = AdvancementFlowParams.model_validate(request.GET.dict())
        if not params.is_other_advancement():
            raise ValueError("Only 'other' advancements allowed at this stage")
    except ValueError as e:
        messages.error(request, f"Invalid advancement: {e}.")
        return HttpResponseRedirect(
            reverse("core:list-fighter-advancement-type", args=(lst.id, fighter.id))
        )

    if request.method == "POST":
        form = OtherAdvancementForm(request.POST)
        if form.is_valid():
            # Add the description to params and proceed to confirmation
            params.description = form.cleaned_data["description"]
            url = reverse(
                "core:list-fighter-advancement-confirm", args=(lst.id, fighter.id)
            )
            return HttpResponseRedirect(
                f"{url}?{urlencode(params.model_dump(mode='json', exclude_none=True))}"
            )
    else:
        form = OtherAdvancementForm()

    return render(
        request,
        "core/list_fighter_advancement_other.html",
        {
            "form": form,
            "fighter": fighter,
            "list": lst,
            "params": params,
            "is_campaign_mode": lst.status == List.CAMPAIGN_MODE,
        },
    )


@login_required
@transaction.atomic
def reassign_list_fighter_equipment(
    request, id, fighter_id, assign_id, is_weapon, back_name
):
    """
    Reassign a :model:`core.ListFighterEquipmentAssignment` to another fighter.

    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` currently owning this equipment assignment.
    ``assign``
        The :model:`core.ListFighterEquipmentAssignment` to be reassigned.
    ``target_fighters``
        Available fighters to reassign to, including stash fighter.
    ``is_weapon``
        Whether this is a weapon assignment.

    **Template**

    :template:`core/list_fighter_assign_reassign.html`
    """
    from gyrinx.core.forms.list import EquipmentReassignForm

    lst = get_clean_list_or_404(
        List.objects.with_related_data(), id=id, owner=request.user
    )
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )
    assignment = get_object_or_404(
        ListFighterEquipmentAssignment.objects.with_related_data(),
        pk=assign_id,
        list_fighter=fighter,
    )

    # Prevent reassigning default assignments
    if assignment.from_default_assignment:
        messages.error(request, "Default equipment cannot be reassigned.")
        return HttpResponseRedirect(reverse(back_name, args=(lst.id, fighter.id)))

    # Get available fighters (exclude current fighter, include stash)
    target_fighters = lst.listfighter_set.filter(archived=False).exclude(id=fighter.id)

    if request.method == "POST":
        form = EquipmentReassignForm(request.POST, fighters=target_fighters)
        if form.is_valid():
            target_fighter = form.cleaned_data["target_fighter"]

            with transaction.atomic():
                # Handle the reassignment (performs update and creates ListAction/CampaignAction)
                result = handle_equipment_reassignment(
                    user=request.user,
                    lst=lst,
                    from_fighter=fighter,
                    to_fighter=target_fighter,
                    assignment=assignment,
                )

                # Log the equipment reassignment
                log_event(
                    user=request.user,
                    noun=EventNoun.EQUIPMENT_ASSIGNMENT,
                    verb=EventVerb.UPDATE,
                    object=result.assignment,
                    request=request,
                    from_fighter_name=result.from_fighter.name,
                    to_fighter_name=result.to_fighter.name,
                    equipment_name=result.assignment.content_equipment.name,
                    list_id=str(lst.id),
                    list_name=lst.name,
                    action="reassigned",
                )

            messages.success(
                request,
                f"{result.assignment.content_equipment.name} reassigned to {result.to_fighter.name}.",
            )
            return HttpResponseRedirect(reverse(back_name, args=(lst.id, fighter.id)))
    else:
        form = EquipmentReassignForm(fighters=target_fighters)

    return render(
        request,
        "core/list_fighter_assign_reassign.html",
        {
            "list": lst,
            "fighter": fighter,
            "assign": assignment,
            "form": form,
            "is_weapon": is_weapon,
            "back_url": back_name,
        },
    )


@login_required
@transaction.atomic
def sell_list_fighter_equipment(request, id, fighter_id, assign_id):
    """
    Sell equipment from a stash fighter with dice roll mechanics.

    This is a three-step flow:
    1. Selection table - choose what to sell and pricing method
    2. Dice roll & campaign action - calculate prices and create action
    3. Summary - show results

    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` (must be stash) owning this equipment assignment.
    ``assign``
        The :model:`core.ListFighterEquipmentAssignment` to be sold.

    **Template**

    :template:`core/list_fighter_equipment_sell.html`
    """
    from gyrinx.core.forms.list import EquipmentSellSelectionForm

    lst = get_clean_list_or_404(
        List.objects.with_related_data(), id=id, owner=request.user
    )
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
    )

    # For summary step, assignment might not exist (already deleted)
    step = request.GET.get("step", "selection")
    if step == "summary":
        assignment = None
    else:
        assignment = get_object_or_404(
            ListFighterEquipmentAssignment.objects.select_related(
                "content_equipment", "list_fighter"
            ).prefetch_related(
                "weapon_profiles_field", "weapon_accessories_field", "upgrades_field"
            ),
            pk=assign_id,
            list_fighter=fighter,
        )

    # Only allow selling from stash fighters in campaign mode
    if not fighter.content_fighter.is_stash:
        messages.error(request, "Equipment can only be sold from the stash.")
        return HttpResponseRedirect(
            reverse("core:list-fighter-gear-edit", args=(lst.id, fighter.id))
        )

    if lst.status != List.CAMPAIGN_MODE:
        messages.error(request, "Equipment can only be sold in campaign mode.")
        return HttpResponseRedirect(
            reverse("core:list-fighter-gear-edit", args=(lst.id, fighter.id))
        )

    # Parse URL parameters to determine what's being sold (skip for summary)
    if step != "summary":
        sell_assign = request.GET.get("sell_assign") == str(assignment.id)
        sell_profiles = request.GET.getlist("sell_profile", [])
        sell_accessories = request.GET.getlist("sell_accessory", [])

    # Calculate what's being sold (skip for summary)
    items_to_sell = []

    if step != "summary" and sell_assign:
        # Selling entire assignment (equipment + upgrades)
        base_cost = assignment.content_equipment.cost_int()
        print(f"Base cost for {assignment.content_equipment.name}: {base_cost}")
        for upgrade in assignment.upgrades_field.all():
            print(f"Adding upgrade cost: {upgrade.cost_int_cached} for {upgrade.name}")
            base_cost += upgrade.cost_int_cached

        items_to_sell.append(
            {
                "type": "equipment",
                "name": assignment.content_equipment.name,
                "upgrades": list(assignment.upgrades_field.all()),
                "base_cost": base_cost,
                "total_cost": base_cost,  # Total cost including upgrades
                "assignment": assignment,
            }
        )

        # Add all profiles
        for profile in assignment.weapon_profiles_field.all():
            items_to_sell.append(
                {
                    "type": "profile",
                    "name": f"- {profile.name}",
                    "base_cost": profile.cost,
                    "total_cost": profile.cost,  # No upgrades for profiles
                    "profile": profile,
                }
            )

        # Add all accessories
        for accessory in assignment.weapon_accessories_field.all():
            items_to_sell.append(
                {
                    "type": "accessory",
                    "name": accessory.name,
                    "base_cost": accessory.cost,
                    "total_cost": accessory.cost,  # No upgrades for accessories
                    "accessory": accessory,
                }
            )
    elif step != "summary":
        # Selling individual components
        for profile_id in sell_profiles:
            profile = assignment.weapon_profiles_field.filter(id=profile_id).first()
            if profile:
                items_to_sell.append(
                    {
                        "type": "profile",
                        "name": profile.name,
                        "base_cost": profile.cost,
                        "total_cost": profile.cost,  # No upgrades for profiles
                        "profile": profile,
                    }
                )

        for accessory_id in sell_accessories:
            accessory = assignment.weapon_accessories_field.filter(
                id=accessory_id
            ).first()
            if accessory:
                items_to_sell.append(
                    {
                        "type": "accessory",
                        "name": accessory.name,
                        "base_cost": accessory.cost,
                        "total_cost": accessory.cost,  # No upgrades for accessories
                        "accessory": accessory,
                    }
                )

    # Handle the form submission
    if request.method == "POST":
        step = request.POST.get("step", "selection")

        if step == "selection":
            # Step 1: Process selection form
            forms = []
            for i, item in enumerate(items_to_sell):
                form = EquipmentSellSelectionForm(request.POST, prefix=str(i))
                forms.append((item, form))

            if all(form.is_valid() for _, form in forms):
                # Store form data in session for next step
                sell_data = []
                for item, form in forms:
                    price_method = form.cleaned_data["price_method"]
                    manual_price = form.cleaned_data.get("manual_price")

                    sell_data.append(
                        {
                            "name": item["name"],
                            "type": item["type"],
                            "base_cost": item["base_cost"],
                            "total_cost": item.get("total_cost", item["base_cost"]),
                            "price_method": price_method,
                            "manual_price": manual_price,
                        }
                    )

                request.session["sell_data"] = sell_data
                request.session["sell_assign_id"] = str(assignment.id)
                request.session["sell_assign"] = sell_assign
                request.session["sell_profiles"] = sell_profiles
                request.session["sell_accessories"] = sell_accessories

                # Redirect to confirmation step
                return HttpResponseRedirect(
                    reverse(
                        "core:list-fighter-equipment-sell",
                        args=(lst.id, fighter.id, assignment.id),
                    )
                    + "?step=confirm"
                )

        elif step == "confirm":
            # Step 2: Process confirmation and create campaign action
            sell_data = request.session.get("sell_data", [])

            if sell_data:
                # Calculate prices and roll dice
                total_dice = 0
                dice_rolls = []
                total_credits = 0
                sale_items = []

                for item_data in sell_data:
                    if item_data["price_method"] == "dice":
                        # Roll D6 for this item
                        roll = random.randint(1, 6)
                        dice_rolls.append(roll)
                        total_dice += 1

                        # Calculate sale price: total cost - (roll × 10), minimum 5¢
                        sale_price = max(
                            5,
                            item_data.get("total_cost", item_data["base_cost"])
                            - (roll * 10),
                        )
                    else:
                        # Use manual price
                        sale_price = item_data["manual_price"]
                        roll = None

                    total_credits += sale_price
                    sale_items.append(
                        SaleItemDetail(
                            name=item_data["name"],
                            cost=item_data.get("total_cost", item_data["base_cost"]),
                            sale_price=sale_price,
                            dice_roll=roll,
                        )
                    )

                # Gather profiles and accessories to remove
                sell_assign = request.session.get("sell_assign")
                profiles_to_remove = []
                accessories_to_remove = []

                if not sell_assign:
                    for profile_id in request.session.get("sell_profiles", []):
                        profile = assignment.weapon_profiles_field.filter(
                            id=profile_id
                        ).first()
                        if profile:
                            profiles_to_remove.append(profile)

                    for accessory_id in request.session.get("sell_accessories", []):
                        accessory = assignment.weapon_accessories_field.filter(
                            id=accessory_id
                        ).first()
                        if accessory:
                            accessories_to_remove.append(accessory)

                # Call the handler
                try:
                    result = handle_equipment_sale(
                        user=request.user,
                        lst=lst,
                        fighter=fighter,
                        assignment=assignment,
                        sell_assignment=sell_assign,
                        profiles_to_remove=profiles_to_remove,
                        accessories_to_remove=accessories_to_remove,
                        sale_items=sale_items,
                        dice_count=total_dice,
                        dice_rolls=dice_rolls,
                    )
                except DjangoValidationError as e:
                    messages.validation(request, e)
                    return HttpResponseRedirect(
                        reverse(
                            "core:list-fighter-equipment-sell",
                            args=(lst.id, fighter.id, assignment.id),
                        )
                        + "?step=selection"
                    )

                # Log the equipment sale event
                log_event(
                    user=request.user,
                    noun=EventNoun.LIST,
                    verb=EventVerb.UPDATE,
                    object=lst,
                    request=request,
                    list_id=str(lst.id),
                    list_name=lst.name,
                    action="equipment_sold",
                    credits_gained=result.total_sale_credits,
                    items_sold=len(sale_items),
                    sale_summary=result.description,
                )

                # Store results in session for summary (convert to dicts for JSON serialization)
                request.session["sale_results"] = {
                    "total_credits": result.total_sale_credits,
                    "sale_details": [
                        {
                            "name": item.name,
                            "total_cost": item.cost,  # Template expects total_cost
                            "sale_price": item.sale_price,
                            "dice_roll": item.dice_roll,
                        }
                        for item in sale_items
                    ],
                    "dice_rolls": dice_rolls,
                }

                # Clear sell data
                request.session.pop("sell_data", None)
                request.session.pop("sell_assign_id", None)
                request.session.pop("sell_assign", None)
                request.session.pop("sell_profiles", None)
                request.session.pop("sell_accessories", None)

                # Redirect to summary
                return HttpResponseRedirect(
                    reverse(
                        "core:list-fighter-equipment-sell",
                        args=(lst.id, fighter.id, assign_id),
                    )
                    + "?step=summary"
                )

    # Determine which step we're on
    step = request.GET.get("step", "selection")

    if step == "selection":
        # Step 1: Show selection form
        forms = []
        for i, item in enumerate(items_to_sell):
            form = EquipmentSellSelectionForm(prefix=str(i))
            forms.append((item, form))

        context = {
            "list": lst,
            "fighter": fighter,
            "assign": assignment,
            "forms": forms,
            "step": "selection",
        }

    elif step == "confirm":
        # Step 2: Show confirmation
        sell_data = request.session.get("sell_data", [])

        context = {
            "list": lst,
            "fighter": fighter,
            "assign": assignment,
            "sell_data": sell_data,
            "step": "confirm",
        }

    elif step == "summary":
        # Step 3: Show summary
        sale_results = request.session.get("sale_results", {})

        # Clear results from session
        if "sale_results" in request.session:
            del request.session["sale_results"]

        context = {
            "list": lst,
            "fighter": fighter,
            "sale_results": sale_results,
            "step": "summary",
        }

    else:
        # Invalid step, redirect to selection
        return HttpResponseRedirect(
            reverse(
                "core:list-fighter-equipment-sell",
                args=(lst.id, fighter.id, assignment.id),
            )
        )

    return render(request, "core/list_fighter_equipment_sell.html", context)


@login_required
def edit_list_attribute(request: HttpRequest, id: uuid.UUID, attribute_id: uuid.UUID):
    """
    Edit attributes for a list.
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)

    # Check if list is archived
    if lst.archived:
        messages.error(request, "Cannot modify attributes for an archived list.")
        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    # Get the attribute
    from gyrinx.content.models import ContentAttribute

    attribute = get_object_or_404(ContentAttribute, id=attribute_id)

    # Check if attribute is available to this house
    if (
        attribute.restricted_to.exists()
        and lst.content_house not in attribute.restricted_to.all()
    ):
        messages.error(
            request, f"{attribute.name} is not available to {lst.content_house.name}."
        )
        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    if request.method == "POST":
        form = ListAttributeForm(
            request.POST, list_obj=lst, attribute=attribute, request=request
        )
        if form.is_valid():
            form.save()

            # Log the attribute update
            log_event(
                user=request.user,
                noun=EventNoun.LIST,
                verb=EventVerb.UPDATE,
                object=lst,
                request=request,
                list_id=str(lst.id),
                list_name=lst.name,
                action="attribute_updated",
                attribute_name=attribute.name,
            )

            messages.success(request, f"{attribute.name} updated successfully.")
            return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))
    else:
        form = ListAttributeForm(list_obj=lst, attribute=attribute, request=request)

    context = {
        "list": lst,
        "attribute": attribute,
        "form": form,
    }

    return render(request, "core/list_attribute_edit.html", context)


@login_required
def edit_list_fighter_rules(request, id, fighter_id):
    """
    Edit the rules of an existing :model:`core.ListFighter`.

    **Context**

    ``fighter``
        The :model:`core.ListFighter` being edited.
    ``list``
        The :model:`core.List` that owns this fighter.
    ``default_rules``
        Rules from the ContentFighter with their disabled status.
    ``custom_rules``
        Custom rules added to the fighter.
    ``available_rules``
        All ContentRules available for adding.

    **Template**

    :template:`core/list_fighter_rules_edit.html`
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )

    # Get query parameters
    search_query = request.GET.get("q", "").strip()

    # Get default rules from ContentFighter (uses prefetched data)
    default_rules = fighter.content_fighter.rules.all()
    # Use prefetched disabled_rules instead of values_list query
    disabled_rule_ids = {r.id for r in fighter.disabled_rules.all()}

    # Build default rules with status
    default_rules_display = []
    for rule in default_rules:
        default_rules_display.append(
            {
                "rule": rule,
                "is_disabled": rule.id in disabled_rule_ids,
            }
        )

    # Get custom rules
    custom_rules = fighter.custom_rules.all()

    # Get all available rules for search
    available_rules: QuerySetOf[ContentRule] = ContentRule.objects.all()

    if search_query:
        available_rules = available_rules.filter(Q(name__icontains=search_query))

    # Exclude those already in custom rules
    available_rules = available_rules.exclude(
        id__in=custom_rules.values_list("id", flat=True)
    )

    # Sort alphabetically
    available_rules = available_rules.order_by("name")

    # Paginate the results
    paginator = Paginator(available_rules, 20)  # Show 20 rules per page
    page_number = request.GET.get("page", 1)

    # Validate page number and redirect if necessary
    try:
        page_number = int(page_number)
        if page_number < 1:
            page_number = 1
    except (TypeError, ValueError):
        page_number = 1

    # If the requested page is out of range due to search, redirect to page 1
    if page_number > paginator.num_pages and paginator.num_pages > 0:
        # Build redirect URL with search query preserved
        url = reverse("core:list-fighter-rules-edit", args=(lst.id, fighter.id))
        params = {}
        if search_query:
            params["q"] = search_query
        if params:
            url = f"{url}?{urlencode(params)}"
        return redirect(url)

    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "core/list_fighter_rules_edit.html",
        {
            "list": lst,
            "fighter": fighter,
            "default_rules_display": default_rules_display,
            "custom_rules": custom_rules,
            "available_rules": available_rules,
            "page_obj": page_obj,
            "search_query": search_query,
        },
    )


@login_required
def toggle_list_fighter_rule(request, id, fighter_id, rule_id):
    """
    Toggle (enable/disable) a default rule for a :model:`core.ListFighter`.
    """
    if request.method != "POST":
        raise Http404()

    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )
    rule = get_object_or_404(ContentRule, id=rule_id)

    # Ensure this is a default rule for the fighter
    if not fighter.content_fighter.rules.filter(id=rule_id).exists():
        messages.error(request, "This rule is not a default rule for this fighter.")
        return HttpResponseRedirect(
            reverse("core:list-fighter-rules-edit", args=(lst.id, fighter.id))
        )

    # Toggle the disabled status
    if fighter.disabled_rules.filter(id=rule_id).exists():
        fighter.disabled_rules.remove(rule)
        action = "enabled"
    else:
        fighter.disabled_rules.add(rule)
        action = "disabled"

    # Log the rule toggle event
    log_event(
        user=request.user,
        noun=EventNoun.LIST_FIGHTER,
        verb=EventVerb.UPDATE,
        object=fighter,
        request=request,
        fighter_name=fighter.name,
        list_id=str(lst.id),
        list_name=lst.name,
        field="rules",
        action=f"{action}_rule",
        rule_name=rule.name,
    )

    messages.success(request, f"{rule.name} {action}")
    return HttpResponseRedirect(
        reverse("core:list-fighter-rules-edit", args=(lst.id, fighter.id))
    )


@login_required
def toggle_list_fighter_skill(request, id, fighter_id, skill_id):
    """
    Toggle (enable/disable) a default skill for a :model:`core.ListFighter`.
    """
    if request.method != "POST":
        raise Http404()

    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )
    skill = get_object_or_404(ContentSkill, id=skill_id)

    # Ensure this is a default skill for the fighter
    if not fighter.content_fighter.skills.filter(id=skill_id).exists():
        messages.error(request, "This skill is not a default skill for this fighter.")
        return HttpResponseRedirect(
            reverse("core:list-fighter-skills-edit", args=(lst.id, fighter.id))
        )

    # Toggle the disabled status
    if fighter.disabled_skills.filter(id=skill_id).exists():
        fighter.disabled_skills.remove(skill)
        action = "enabled"
    else:
        fighter.disabled_skills.add(skill)
        action = "disabled"

    # Log the skill toggle event
    log_event(
        user=request.user,
        noun=EventNoun.LIST_FIGHTER,
        verb=EventVerb.UPDATE,
        object=fighter,
        request=request,
        fighter_name=fighter.name,
        list_id=str(lst.id),
        list_name=lst.name,
        field="skills",
        action=f"{action}_skill",
        skill_name=skill.name,
    )

    messages.success(request, f"{skill.name} {action}")
    return HttpResponseRedirect(
        reverse("core:list-fighter-skills-edit", args=(lst.id, fighter.id))
    )


@login_required
def add_list_fighter_rule(request, id, fighter_id):
    """
    Add a custom rule to a :model:`core.ListFighter`.
    """
    if request.method != "POST":
        raise Http404()

    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )

    rule_id = request.POST.get("rule_id")
    if rule_id and is_valid_uuid(rule_id):
        rule = get_object_or_404(ContentRule, id=rule_id)
        fighter.custom_rules.add(rule)

        # Log the rule addition event
        log_event(
            user=request.user,
            noun=EventNoun.LIST_FIGHTER,
            verb=EventVerb.UPDATE,
            object=fighter,
            request=request,
            fighter_name=fighter.name,
            list_id=str(lst.id),
            list_name=lst.name,
            field="rules",
            action="add_rule",
            rule_name=rule.name,
            rules_count=fighter.custom_rules.count(),
        )

        messages.success(request, f"Added {rule.name}")
    elif rule_id:
        messages.error(request, "Invalid rule ID provided.")

    return HttpResponseRedirect(
        reverse("core:list-fighter-rules-edit", args=(lst.id, fighter.id))
    )


@login_required
def remove_list_fighter_rule(request, id, fighter_id, rule_id):
    """
    Remove a custom rule from a :model:`core.ListFighter`.
    """
    if request.method != "POST":
        raise Http404()

    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )

    rule = get_object_or_404(ContentRule, id=rule_id)
    fighter.custom_rules.remove(rule)

    # Log the rule removal event
    log_event(
        user=request.user,
        noun=EventNoun.LIST_FIGHTER,
        verb=EventVerb.UPDATE,
        object=fighter,
        request=request,
        fighter_name=fighter.name,
        list_id=str(lst.id),
        list_name=lst.name,
        field="rules",
        action="remove_rule",
        rule_name=rule.name,
        rules_count=fighter.custom_rules.count(),
    )

    messages.success(request, f"Removed {rule.name}")
    return HttpResponseRedirect(
        reverse("core:list-fighter-rules-edit", args=(lst.id, fighter.id))
    )


@login_required
def list_invitations(request, id):
    """
    Display invitations for a list.

    Shows all pending campaign invitations for a list that the user owns.

    **Context**

    ``list``
        The :model:`core.List` whose invitations are being displayed.
    ``invitations``
        Pending :model:`core.CampaignInvitation` objects.

    **Template**

    :template:`core/list/list_invitations.html`
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)

    # Get pending invitations for this list
    from gyrinx.core.models.invitation import CampaignInvitation

    invitations = CampaignInvitation.objects.filter(
        list=lst, status=CampaignInvitation.PENDING
    ).select_related("campaign", "campaign__owner")

    return render(
        request,
        "core/list/list_invitations.html",
        {
            "list": lst,
            "invitations": invitations,
        },
    )


@login_required
@transaction.atomic
def accept_invitation(request, id, invitation_id):
    """
    Accept a campaign invitation.

    Allows a list owner to accept an invitation to join a campaign.

    **Context**

    ``list``
        The :model:`core.List` being invited.
    ``invitation``
        The :model:`core.CampaignInvitation` being accepted.

    **Template**

    None - redirects after processing.
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)

    from gyrinx.core.models.invitation import CampaignInvitation

    invitation = get_object_or_404(
        CampaignInvitation,
        id=invitation_id,
        list=lst,
        status=CampaignInvitation.PENDING,
    )

    # Check if the campaign is completed
    if invitation.campaign.is_post_campaign:
        messages.error(
            request, "This campaign has ended. You cannot join a completed campaign."
        )
        return HttpResponseRedirect(reverse("core:list-invitations", args=(lst.id,)))

    # Accept the invitation
    if invitation.accept():
        # Log the acceptance event
        log_event(
            user=request.user,
            noun=EventNoun.CAMPAIGN_INVITATION,
            verb=EventVerb.APPROVE,
            object=invitation,
            request=request,
            campaign_id=str(invitation.campaign.id),
            campaign_name=invitation.campaign.name,
            list_id=str(lst.id),
            list_name=lst.name,
            action="invitation_accepted",
        )

        messages.success(
            request, f"You have joined the campaign '{invitation.campaign.name}'."
        )
    else:
        messages.error(request, "Unable to accept the invitation.")

    return HttpResponseRedirect(reverse("core:list-invitations", args=(lst.id,)))


@login_required
@transaction.atomic
def decline_invitation(request, id, invitation_id):
    """
    Decline a campaign invitation.

    Allows a list owner to decline an invitation to join a campaign.

    **Context**

    ``list``
        The :model:`core.List` being invited.
    ``invitation``
        The :model:`core.CampaignInvitation` being declined.

    **Template**

    None - redirects after processing.
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)

    from gyrinx.core.models.invitation import CampaignInvitation

    invitation = get_object_or_404(
        CampaignInvitation,
        id=invitation_id,
        list=lst,
        status=CampaignInvitation.PENDING,
    )

    # Decline the invitation
    if invitation.decline():
        # Log the decline event
        log_event(
            user=request.user,
            noun=EventNoun.CAMPAIGN_INVITATION,
            verb=EventVerb.REJECT,
            object=invitation,
            request=request,
            campaign_id=str(invitation.campaign.id),
            campaign_name=invitation.campaign.name,
            list_id=str(lst.id),
            list_name=lst.name,
            action="invitation_declined",
        )

        messages.info(
            request,
            f"You have declined the invitation to '{invitation.campaign.name}'.",
        )
    else:
        messages.error(request, "Unable to decline the invitation.")

    return HttpResponseRedirect(reverse("core:list-invitations", args=(lst.id,)))
