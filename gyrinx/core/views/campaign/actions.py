"""Campaign action logging views."""

from datetime import timedelta
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.contrib.postgres.search import SearchQuery, SearchVector
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views import generic

from gyrinx import messages
from gyrinx.core.forms.campaign import CampaignActionForm, CampaignActionOutcomeForm
from gyrinx.core.models.campaign import Campaign, CampaignAction
from gyrinx.core.models.events import EventNoun, EventVerb, log_event
from gyrinx.core.utils import get_return_url, safe_redirect
from gyrinx.models import is_int, is_valid_uuid
from gyrinx.tracker import track


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
        None or a string describing a form error, set if form submission fails.
    ``return_url``
        A URL to return to after logging the action (for navigation after form submission).

    **Template**

    :template:`core/campaign/campaign_log_action.html`
    """
    campaign = get_object_or_404(Campaign, id=id)

    # Check if user is part of the campaign (owner or has a list in it) and campaign is in progress and not archived
    user_lists_in_campaign = campaign.lists.filter(owner=request.user).exists()
    if (
        not campaign.is_in_progress
        or campaign.archived
        or (campaign.owner != request.user and not user_lists_in_campaign)
    ):
        messages.error(request, "You cannot log actions for this campaign.")
        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))

    # Get return URL for back/cancel navigation
    default_url = reverse("core:campaign", args=(campaign.id,))
    return_url = get_return_url(request, default_url)

    error_message = None
    if request.method == "POST":
        form = CampaignActionForm(request.POST, campaign=campaign, user=request.user)
        if form.is_valid():
            action = form.save(commit=False)
            action.campaign = campaign
            action.user = request.user
            action.save()

            # Log the campaign action event
            log_event(
                user=request.user,
                noun=EventNoun.CAMPAIGN_ACTION,
                verb=EventVerb.CREATE,
                object=action,
                request=request,
                campaign_id=str(campaign.id),
                campaign_name=campaign.name,
                description=action.description,
            )

            track(
                "campaign_action_logged",
                campaign_id=str(campaign.id),
                has_dice=bool(action.dice_count),
            )

            # Redirect to outcome edit page, passing along return_url
            outcome_url = reverse(
                "core:campaign-action-outcome", args=(campaign.id, action.id)
            )
            redirect_url = f"{outcome_url}?{urlencode({'return_url': return_url})}"
            return safe_redirect(request, redirect_url, fallback_url=default_url)
    else:
        # Pre-populate gang/list if provided
        gang = request.GET.get("gang")
        initial = {}
        if gang:
            initial["list"] = gang

        form = CampaignActionForm(campaign=campaign, user=request.user, initial=initial)

    return render(
        request,
        "core/campaign/campaign_log_action.html",
        {
            "form": form,
            "campaign": campaign,
            "error_message": error_message,
            "return_url": return_url,
        },
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
        None or a string describing a form error, set if form submission fails.
    ``return_url``
        A URL to return to after editing the outcome (for navigation after form submission).

    **Template**

    :template:`core/campaign/campaign_action_outcome.html`
    """
    campaign = get_object_or_404(Campaign, id=id)
    action = get_object_or_404(CampaignAction, id=action_id, campaign=campaign)

    # Check if user can edit this action (only the creator)
    if action.user != request.user:
        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))

    # Get return URL for back/cancel navigation
    default_url = reverse("core:campaign", args=(campaign.id,))
    return_url = get_return_url(request, default_url)

    error_message = None
    if request.method == "POST":
        form = CampaignActionOutcomeForm(request.POST, instance=action)
        if form.is_valid():
            form.save()

            # Log the action outcome update
            log_event(
                user=request.user,
                noun=EventNoun.CAMPAIGN_ACTION,
                verb=EventVerb.UPDATE,
                object=action,
                request=request,
                campaign_id=str(campaign.id),
                campaign_name=campaign.name,
                outcome=action.outcome,
            )

            # Check which button was clicked
            if "save_and_new" in request.POST:
                # Redirect to create another action, preserving return_url
                new_action_url = reverse(
                    "core:campaign-action-new", args=(campaign.id,)
                )
                redirect_url = (
                    f"{new_action_url}?{urlencode({'return_url': return_url})}"
                )
                return safe_redirect(request, redirect_url, fallback_url=default_url)
            else:
                # Default: redirect to return URL
                return safe_redirect(request, return_url, fallback_url=default_url)
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
            "return_url": return_url,
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

        # Start with all campaign actions with list and battle relationships
        actions = self.campaign.actions.select_related(
            "user", "list", "battle"
        ).order_by("-created")

        # Apply text search filter if provided
        search_query = self.request.GET.get("q", "").strip()
        if search_query:
            actions = actions.annotate(
                search=SearchVector("description", "outcome", "user__username")
            ).filter(search=SearchQuery(search_query))

        # Apply gang filter if provided
        gang_id = self.request.GET.get("gang")
        if gang_id and is_valid_uuid(gang_id):
            # Filter actions by the specific list/gang
            actions = actions.filter(list_id=gang_id)

        # Apply author filter if provided (user IDs are integers, not UUIDs)
        author_id = self.request.GET.get("author")
        if author_id and is_int(author_id):
            actions = actions.filter(user__id=author_id)

        # Apply battle filter if provided
        battle_id = self.request.GET.get("battle")
        if battle_id and is_valid_uuid(battle_id):
            # Filter actions by the specific battle
            actions = actions.filter(battle_id=battle_id)

        # Apply timeframe filter if provided
        timeframe = self.request.GET.get("timeframe", "all")
        if timeframe != "all":
            now = timezone.now()
            if timeframe == "24h":
                actions = actions.filter(created__gte=now - timedelta(hours=24))
            elif timeframe == "7d":
                actions = actions.filter(created__gte=now - timedelta(days=7))
            elif timeframe == "30d":
                actions = actions.filter(created__gte=now - timedelta(days=30))

        return actions

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["campaign"] = self.campaign

        # Get all lists/gangs in the campaign for the gang filter
        context["campaign_lists"] = self.campaign.lists.select_related(
            "owner", "content_house"
        ).order_by("name")

        # Get all users who have performed actions for the author filter
        context["action_authors"] = (
            self.campaign.actions.values_list("user__id", "user__username")
            .distinct()
            .order_by("user__username")
        )

        # Get all battles in the campaign for the battle filter
        context["campaign_battles"] = (
            self.campaign.battles.select_related("owner")
            .prefetch_related("participants", "winners")
            .order_by("-date", "-created")
        )

        # Check if user can log actions (owner or has a list in campaign, and campaign is in progress and not archived)
        user = self.request.user
        if user.is_authenticated:
            context["can_log_actions"] = (
                self.campaign.is_in_progress
                and not self.campaign.archived
                and (
                    self.campaign.owner == user
                    or self.campaign.lists.filter(owner=user).exists()
                )
            )
        else:
            context["can_log_actions"] = False
        return context
