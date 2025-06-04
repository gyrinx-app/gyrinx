from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.postgres.search import SearchVector
from django.db import models
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views import generic

from gyrinx.core.forms.campaign import (
    CampaignActionForm,
    CampaignActionOutcomeForm,
    EditCampaignForm,
    NewCampaignForm,
)
from gyrinx.core.models.campaign import Campaign, CampaignAction
from gyrinx.core.models.list import List


class Campaigns(generic.ListView):
    template_name = "core/campaign/campaigns.html"
    context_object_name = "campaigns"

    def get_queryset(self):
        return Campaign.objects.filter(public=True)


class CampaignDetailView(generic.DetailView):
    """
    Display a single :model:`core.Campaign` object.

    **Context**

    ``campaign``
        The requested :model:`core.Campaign` object.

    **Template**

    :template:`core/campaign/campaign.html`
    """

    template_name = "core/campaign/campaign.html"
    context_object_name = "campaign"

    def get_object(self):
        """
        Retrieve the :model:`core.Campaign` by its `id`.
        """
        return get_object_or_404(Campaign, id=self.kwargs["id"])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Check if user can log actions (owner or has a list in campaign, and campaign is in progress)
        user = self.request.user
        if user.is_authenticated:
            campaign = self.object
            context["can_log_actions"] = campaign.is_in_progress and (
                campaign.owner == user or campaign.lists.filter(owner=user).exists()
            )
        else:
            context["can_log_actions"] = False
        return context


@login_required
def campaign_add_lists(request, id):
    """
    Add lists to a campaign.

    Allows the campaign owner to search for and add lists to their campaign.
    Only available for campaigns in pre-campaign or in-progress status.

    **Context**

    ``campaign``
        The :model:`core.Campaign` being edited.
    ``lists``
        Available :model:`core.List` objects that can be added.
    ``added_list``
        The most recently added list (if any).
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/campaign/campaign_add_lists.html`
    """
    campaign = get_object_or_404(Campaign, id=id, owner=request.user)

    # Check if campaign is in a state where lists can be added
    if campaign.is_post_campaign:
        messages.error(request, "Cannot add lists to a completed campaign.")
        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))
    added_list = None
    error_message = None

    if request.method == "POST":
        list_id = request.POST.get("list_id")
        if list_id:
            try:
                list_to_add = List.objects.get(id=list_id)
                # Check if user can add this list (either owner or public)
                if list_to_add.owner == request.user or list_to_add.public:
                    campaign.lists.add(list_to_add)
                    added_list = list_to_add
                    # Redirect to the same page with the search params preserved
                    query_params = []
                    if request.GET.get("q"):
                        query_params.append(f"q={request.GET.get('q')}")
                    if request.GET.get("owner"):
                        query_params.append(f"owner={request.GET.get('owner')}")
                    query_str = "&".join(query_params)
                    return HttpResponseRedirect(
                        reverse("core:campaign-add-lists", args=(campaign.id,))
                        + (f"?{query_str}" if query_str else "")
                        + "#added"
                    )
                else:
                    error_message = "You can only add your own lists or public lists."
            except List.DoesNotExist:
                error_message = "List not found."

    # Get lists that can be added (user's own lists or public lists)
    # Start with all lists the user can see
    lists = List.objects.filter(
        models.Q(owner=request.user) | models.Q(public=True)
    ).exclude(
        # Exclude lists already in the campaign
        id__in=campaign.lists.values_list("id", flat=True)
    )

    # Apply search filter if provided
    if request.GET.get("q"):
        lists = lists.annotate(
            search=SearchVector("name", "content_house__name", "owner__username")
        ).filter(search=request.GET.get("q"))

    # Filter by owner type
    owner_filter = request.GET.get("owner", "all")
    if owner_filter == "mine":
        lists = lists.filter(owner=request.user)
    elif owner_filter == "others":
        # Only show public lists from other users
        lists = lists.filter(public=True).exclude(owner=request.user)

    # Order by name
    lists = lists.order_by("name")

    # Check if we just added a list
    if request.GET.get("added") and not added_list:
        # Try to get the most recently added list
        latest_list = campaign.lists.order_by("-id").first()
        if latest_list:
            added_list = latest_list

    return render(
        request,
        "core/campaign/campaign_add_lists.html",
        {
            "campaign": campaign,
            "lists": lists,
            "added_list": added_list,
            "error_message": error_message,
        },
    )


@login_required
def new_campaign(request):
    """
    Create a new :model:`core.Campaign` owned by the current user.

    **Context**

    ``form``
        A NewCampaignForm for entering the name and details of the new campaign.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/campaign/campaign_new.html`
    """
    error_message = None
    if request.method == "POST":
        form = NewCampaignForm(request.POST)
        if form.is_valid():
            campaign = form.save(commit=False)
            campaign.owner = request.user
            campaign.save()
            return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))
    else:
        form = NewCampaignForm(
            initial={
                "name": request.GET.get("name", ""),
            }
        )

    return render(
        request,
        "core/campaign/campaign_new.html",
        {"form": form, "error_message": error_message},
    )


@login_required
def edit_campaign(request, id):
    """
    Edit an existing :model:`core.Campaign` owned by the current user.

    **Context**

    ``form``
        A EditCampaignForm for editing the campaign's details.
    ``campaign``
        The :model:`core.Campaign` being edited.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/campaign/campaign_edit.html`
    """
    campaign = get_object_or_404(Campaign, id=id, owner=request.user)

    error_message = None
    if request.method == "POST":
        form = EditCampaignForm(request.POST, instance=campaign)
        if form.is_valid():
            updated_campaign = form.save(commit=False)
            updated_campaign.save()
            return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))
    else:
        form = EditCampaignForm(instance=campaign)

    return render(
        request,
        "core/campaign/campaign_edit.html",
        {"form": form, "campaign": campaign, "error_message": error_message},
    )


@login_required
def campaign_log_action(request, id):
    """
    Log a new action for a campaign.

    **Context**

    ``campaign``
        The :model:`core.Campaign` the action is being logged for.
    ``form``
        A CampaignActionForm for entering the action details.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/campaign/campaign_log_action.html`
    """
    campaign = get_object_or_404(Campaign, id=id)

    # Check if user is part of the campaign (owner or has a list in it) and campaign is in progress
    user_lists_in_campaign = campaign.lists.filter(owner=request.user).exists()
    if not campaign.is_in_progress or (
        campaign.owner != request.user and not user_lists_in_campaign
    ):
        messages.error(request, "You cannot log actions for this campaign.")
        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))

    error_message = None
    if request.method == "POST":
        form = CampaignActionForm(request.POST)
        if form.is_valid():
            action = form.save(commit=False)
            action.campaign = campaign
            action.user = request.user
            action.save()

            # Redirect to outcome edit page
            return HttpResponseRedirect(
                reverse("core:campaign-action-outcome", args=(campaign.id, action.id))
            )
    else:
        form = CampaignActionForm()

    return render(
        request,
        "core/campaign/campaign_log_action.html",
        {"form": form, "campaign": campaign, "error_message": error_message},
    )


@login_required
def campaign_action_outcome(request, id, action_id):
    """
    Edit the outcome of a campaign action.

    **Context**

    ``campaign``
        The :model:`core.Campaign` the action belongs to.
    ``action``
        The :model:`core.CampaignAction` being edited.
    ``form``
        A CampaignActionOutcomeForm for editing the outcome.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/campaign/campaign_action_outcome.html`
    """
    campaign = get_object_or_404(Campaign, id=id)
    action = get_object_or_404(CampaignAction, id=action_id, campaign=campaign)

    # Check if user can edit this action (only the creator)
    if action.user != request.user:
        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))

    error_message = None
    if request.method == "POST":
        form = CampaignActionOutcomeForm(request.POST, instance=action)
        if form.is_valid():
            form.save()

            # Check which button was clicked
            if "save_and_new" in request.POST:
                # Redirect to create another action
                return HttpResponseRedirect(
                    reverse("core:campaign-action-new", args=(campaign.id,))
                )
            else:
                # Default: redirect to campaign
                return HttpResponseRedirect(
                    reverse("core:campaign", args=(campaign.id,))
                )
    else:
        form = CampaignActionOutcomeForm(instance=action)

    return render(
        request,
        "core/campaign/campaign_action_outcome.html",
        {
            "form": form,
            "campaign": campaign,
            "action": action,
            "error_message": error_message,
        },
    )


class CampaignActionList(generic.ListView):
    """
    Display all actions for a campaign.

    **Context**

    ``campaign``
        The :model:`core.Campaign` whose actions are being displayed.
    ``object_list``
        The list of :model:`core.CampaignAction` objects.

    **Template**

    :template:`core/campaign/campaign_actions.html`
    """

    template_name = "core/campaign/campaign_actions.html"
    context_object_name = "actions"
    paginate_by = 50

    def get_queryset(self):
        self.campaign = get_object_or_404(Campaign, id=self.kwargs["id"])
        return self.campaign.actions.select_related("user").order_by("-created")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["campaign"] = self.campaign
        # Check if user can log actions (owner or has a list in campaign, and campaign is in progress)
        user = self.request.user
        if user.is_authenticated:
            context["can_log_actions"] = self.campaign.is_in_progress and (
                self.campaign.owner == user
                or self.campaign.lists.filter(owner=user).exists()
            )
        else:
            context["can_log_actions"] = False
        return context


@login_required
def start_campaign(request, id):
    """
    Start a campaign (transition from pre-campaign to in-progress).

    Only the campaign owner can start a campaign.

    **Context**

    ``campaign``
        The :model:`core.Campaign` to be started.

    **Template**

    :template:`core/campaign/campaign_start.html`
    """
    campaign = get_object_or_404(Campaign, id=id, owner=request.user)

    if request.method == "POST":
        if campaign.start_campaign():
            messages.success(request, "Campaign has been started!")
        else:
            if not campaign.lists.exists():
                messages.error(request, "Cannot start campaign without any lists.")
            else:
                messages.error(request, "Campaign cannot be started.")
        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))

    # For GET request, show confirmation page
    if not campaign.can_start_campaign():
        messages.error(request, "This campaign cannot be started.")
        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))

    return render(
        request,
        "core/campaign/campaign_start.html",
        {"campaign": campaign},
    )


@login_required
def end_campaign(request, id):
    """
    End a campaign (transition from in-progress to post-campaign).

    Only the campaign owner can end a campaign.

    **Context**

    ``campaign``
        The :model:`core.Campaign` to be ended.

    **Template**

    :template:`core/campaign/campaign_end.html`
    """
    campaign = get_object_or_404(Campaign, id=id, owner=request.user)

    if request.method == "POST":
        if campaign.end_campaign():
            messages.success(request, "Campaign has been ended!")
        else:
            messages.error(request, "Campaign cannot be ended.")
        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))

    # For GET request, show confirmation page
    if not campaign.can_end_campaign():
        messages.error(request, "This campaign cannot be ended.")
        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))

    return render(
        request,
        "core/campaign/campaign_end.html",
        {"campaign": campaign},
    )
