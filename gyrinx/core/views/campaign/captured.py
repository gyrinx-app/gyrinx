"""Captured fighter management views."""

import logging

from django.contrib.auth.decorators import login_required
from django.db import models
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from gyrinx import messages
from gyrinx.core.handlers.fighter.capture import handle_fighter_return_to_owner
from gyrinx.core.models.campaign import Campaign
from gyrinx.core.models.events import EventNoun, EventVerb, log_event
from gyrinx.core.models.list import CapturedFighter
from gyrinx.core.utils import get_return_url, safe_redirect
from gyrinx.tracker import track

# Constants for transaction limits
MAX_CREDITS = 10000

MAX_RANSOM_CREDITS = 10000

logger = logging.getLogger(__name__)


@login_required
def campaign_captured_fighters(request, id):
    """
    View all fighters captured by lists in this campaign.

    **Context**

    ``campaign``
        The :model:`core.Campaign` whose captured fighters are being viewed.
    ``captured_fighters``
        QuerySet of :model:`core.CapturedFighter` objects.

    **Template**

    :template:`core/campaign/campaign_captured_fighters.html`
    """
    campaign = get_object_or_404(Campaign.objects.prefetch_related("lists"), id=id)

    # Check if user owns the campaign or any list in it
    user_owns_list = any(
        list.owner_id == request.user.id for list in campaign.lists.all()
    )
    if campaign.owner != request.user and not user_owns_list:
        messages.error(
            request,
            "You don't have permission to view this campaign's captured fighters.",
        )
        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))

    # Get all captured fighters for lists in this campaign
    captured_fighters = (
        CapturedFighter.objects.filter(
            models.Q(capturing_list__campaigns=campaign)
            | models.Q(fighter__list__campaigns=campaign)
        )
        .select_related(
            "fighter", "fighter__list", "fighter__content_fighter", "capturing_list"
        )
        .order_by("-captured_at")
    )

    # Log viewing captured fighters
    log_event(
        user=request.user,
        noun=EventNoun.CAMPAIGN,
        verb=EventVerb.VIEW,
        object=campaign,
        request=request,
        page="captured_fighters",
        campaign_id=str(campaign.id),
        campaign_name=campaign.name,
        captured_fighters_count=captured_fighters.count(),
    )

    return render(
        request,
        "core/campaign/campaign_captured_fighters.html",
        {
            "campaign": campaign,
            "captured_fighters": captured_fighters,
        },
    )


@login_required
def fighter_sell_to_guilders(request, id, fighter_id):
    """
    Sell a captured fighter to the guilders.

    **Context**

    ``campaign``
        The :model:`core.Campaign` the fighter belongs to.
    ``captured_fighter``
        The :model:`core.CapturedFighter` being sold.

    **Template**

    :template:`core/campaign/fighter_sell_to_guilders.html`
    """
    from gyrinx.core.handlers.fighter.capture import handle_fighter_sell_to_guilders

    campaign = get_object_or_404(Campaign, id=id)

    # Get the captured fighter - must be in this campaign and not sold
    captured_fighter = get_object_or_404(
        CapturedFighter,
        fighter_id=fighter_id,
        capturing_list__campaign=campaign,
        sold_to_guilders=False,
    )

    # Check permissions: must be capturing list owner OR campaign owner
    if (
        request.user != captured_fighter.capturing_list.owner
        and request.user != campaign.owner
    ):
        raise Http404()

    # Get return URL for back/cancel navigation
    default_url = reverse("core:campaign-captured-fighters", args=(campaign.id,))
    return_url = get_return_url(request, default_url)

    if request.method == "POST":
        credits = request.POST.get("credits", 0)
        try:
            credits = int(credits) if credits else 0
            if credits < 0:
                raise ValueError("Credits cannot be negative")
            if credits > MAX_CREDITS:
                raise ValueError(f"Credits cannot exceed {MAX_CREDITS:,}")
        except ValueError as e:
            # Use the error message directly since we control the ValueError messages
            messages.error(request, str(e))
            # Redirect safely back to the form
            return safe_redirect(
                request,
                request.path,
                fallback_url=default_url,
            )

        # Call the handler
        result = handle_fighter_sell_to_guilders(
            user=request.user,
            captured_fighter=captured_fighter,
            sale_price=credits,
        )

        # Log the fighter sale event
        log_event(
            user=request.user,
            noun=EventNoun.LIST_FIGHTER,
            verb=EventVerb.UPDATE,
            object=result.fighter,
            request=request,
            campaign_id=str(campaign.id),
            campaign_name=campaign.name,
            action="sold_to_guilders",
            fighter_name=result.fighter.name,
            original_list=result.fighter.list.name,
            capturing_list=result.capturing_list.name,
            credits=credits,
        )

        track("campaign_fighter_sold", campaign_id=str(campaign.id))

        messages.success(
            request, f"{result.fighter.name} has been sold to the guilders."
        )
        return safe_redirect(request, return_url, fallback_url=default_url)

    return render(
        request,
        "core/campaign/fighter_sell_to_guilders.html",
        {
            "campaign": campaign,
            "captured_fighter": captured_fighter,
            "return_url": return_url,
        },
    )


@login_required
def fighter_return_to_owner(request, id, fighter_id):
    """
    Return a captured fighter to their original gang.

    **Context**

    ``campaign``
        The :model:`core.Campaign` the fighter belongs to.
    ``captured_fighter``
        The :model:`core.CapturedFighter` being returned.

    **Template**

    :template:`core/campaign/fighter_return_to_owner.html`
    """

    campaign = get_object_or_404(Campaign, id=id)

    # Get the captured fighter - must be in this campaign and not sold
    captured_fighter = get_object_or_404(
        CapturedFighter,
        fighter_id=fighter_id,
        capturing_list__campaign=campaign,
        sold_to_guilders=False,
    )

    # Check permissions: must be capturing list owner OR campaign owner OR captured fighter owner
    if (
        request.user != captured_fighter.capturing_list.owner
        and request.user != campaign.owner
        and request.user != captured_fighter.fighter.list.owner
    ):
        raise Http404()

    # Get return URL for back/cancel navigation
    default_url = reverse("core:campaign-captured-fighters", args=(campaign.id,))
    return_url = get_return_url(request, default_url)

    if request.method == "POST":
        ransom = request.POST.get("ransom", 0)
        try:
            ransom = int(ransom) if ransom else 0
            if ransom < 0:
                raise ValueError("Ransom cannot be negative")
            if ransom > MAX_RANSOM_CREDITS:
                raise ValueError(f"Ransom cannot exceed {MAX_RANSOM_CREDITS:,}")
        except ValueError as e:
            # Use the error message directly since we control the ValueError messages
            messages.error(request, str(e))
            # Redirect safely back to the form
            return safe_redirect(
                request,
                request.path,
                fallback_url=default_url,
            )

        # Store fighter info before handler (fighter object may be modified)
        fighter = captured_fighter.fighter
        original_list = fighter.list
        capturing_list = captured_fighter.capturing_list
        fighter_name = fighter.name

        try:
            # Call the handler
            result = handle_fighter_return_to_owner(
                user=request.user,
                captured_fighter=captured_fighter,
                ransom_amount=ransom,
            )

            # Log the fighter return event
            log_event(
                user=request.user,
                noun=EventNoun.LIST_FIGHTER,
                verb=EventVerb.UPDATE,
                object=result.fighter,
                request=request,
                campaign_id=str(campaign.id),
                campaign_name=campaign.name,
                action="returned_to_owner",
                fighter_name=fighter_name,
                original_list=original_list.name,
                capturing_list=capturing_list.name,
                ransom=ransom,
            )
            track("campaign_fighter_ransomed", campaign_id=str(campaign.id))

            messages.success(
                request, f"{fighter_name} has been returned to {original_list.name}."
            )
            return safe_redirect(request, return_url, fallback_url=default_url)

        except ValidationError as e:
            messages.validation(request, e)
            return safe_redirect(
                request,
                request.path,
                fallback_url=default_url,
            )

    return render(
        request,
        "core/campaign/fighter_return_to_owner.html",
        {
            "campaign": campaign,
            "captured_fighter": captured_fighter,
            "return_url": return_url,
        },
    )


@login_required
def fighter_release(request, id, fighter_id):
    """
    Release a captured fighter without ransom or sale.

    **Context**

    ``campaign``
        The :model:`core.Campaign` the fighter belongs to.
    ``captured_fighter``
        The :model:`core.CapturedFighter` being released.

    **Template**

    :template:`core/campaign/fighter_release.html`
    """
    from gyrinx.core.handlers.fighter.capture import handle_fighter_release

    campaign = get_object_or_404(Campaign, id=id)

    # Get the captured fighter - must be in this campaign and not sold
    captured_fighter = get_object_or_404(
        CapturedFighter,
        fighter_id=fighter_id,
        capturing_list__campaign=campaign,
        sold_to_guilders=False,
    )

    # Check permissions: must be capturing list owner OR campaign owner OR captured fighter owner
    if (
        request.user != captured_fighter.capturing_list.owner
        and request.user != campaign.owner
        and request.user != captured_fighter.fighter.list.owner
    ):
        raise Http404()

    # Get return URL for back/cancel navigation
    default_url = reverse("core:campaign-captured-fighters", args=(campaign.id,))
    return_url = get_return_url(request, default_url)

    if request.method == "POST":
        # Store info before handler (capture record will be deleted)
        fighter = captured_fighter.fighter
        original_list = fighter.list
        capturing_list = captured_fighter.capturing_list
        fighter_name = fighter.name

        # Call the handler
        result = handle_fighter_release(
            user=request.user,
            captured_fighter=captured_fighter,
        )

        # Log the fighter release event
        log_event(
            user=request.user,
            noun=EventNoun.LIST_FIGHTER,
            verb=EventVerb.UPDATE,
            object=result.fighter,
            request=request,
            campaign_id=str(campaign.id),
            campaign_name=campaign.name,
            fighter_name=fighter_name,
            action="released",
            capturing_list=capturing_list.name,
            original_list=original_list.name,
        )
        track("campaign_fighter_released", campaign_id=str(campaign.id))

        messages.success(
            request,
            f"{fighter_name} has been released back to {original_list.name}.",
        )

        return safe_redirect(request, return_url, fallback_url=default_url)

    return render(
        request,
        "core/campaign/fighter_release.html",
        {
            "campaign": campaign,
            "captured_fighter": captured_fighter,
            "return_url": return_url,
        },
    )
