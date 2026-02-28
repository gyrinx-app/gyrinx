"""Campaign pack management views."""

from django.contrib.auth.decorators import login_required
from django.db import models
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from gyrinx import messages
from gyrinx.core.models.campaign import Campaign
from gyrinx.core.models.pack import CustomContentPack
from gyrinx.core.views.auth import group_membership_required


@login_required
@group_membership_required(["Custom Content"])
def campaign_packs(request, id):
    """
    Manage content packs for a campaign.

    Accessible to the campaign owner and any user with a gang in the campaign.
    The owner sees add/remove pack controls; all members see "Add to..."
    dropdowns to subscribe their gangs to the allowed packs.

    **Context**

    ``campaign``
        The :model:`core.Campaign` whose packs are being managed.
    ``campaign_packs``
        Packs currently allowed in this campaign, each annotated with
        ``unsubscribed_user_lists`` (the user's campaign gangs not yet
        subscribed to that pack).
    ``available_packs``
        Packs that can be added (owner only).
    ``is_owner``
        Whether current user owns the campaign.
    ``user_campaign_lists``
        The current user's gangs that belong to this campaign.

    **Template**

    :template:`core/campaign/campaign_packs.html`
    """
    campaign = get_object_or_404(Campaign, id=id)
    user = request.user
    is_owner = campaign.owner == user
    is_member = campaign.lists.filter(owner=user).exists()

    if not is_owner and not is_member:
        raise Http404

    campaign_packs_qs = campaign.packs.select_related("owner").order_by("name")

    # User's gangs in this campaign, for the "Add to..." dropdown.
    user_campaign_lists = (
        campaign.lists.filter(owner=user, archived=False)
        .select_related("content_house")
        .prefetch_related("packs")
        .order_by("name")
    )

    # For each pack, compute which of the user's campaign gangs are not yet
    # subscribed so the template can render the dropdown items.
    subscribed_by_pack = {}
    for lst in user_campaign_lists:
        for pack_id in lst.packs.values_list("id", flat=True):
            subscribed_by_pack.setdefault(pack_id, set()).add(lst.id)

    packs_with_lists = []
    for pack in campaign_packs_qs:
        subscribed_ids = subscribed_by_pack.get(pack.id, set())
        pack.unsubscribed_user_lists = [
            lst for lst in user_campaign_lists if lst.id not in subscribed_ids
        ]
        packs_with_lists.append(pack)

    # Owner-only: available packs to add to the campaign.
    available_packs = None
    search_query = ""
    if is_owner:
        available_packs = (
            CustomContentPack.objects.filter(
                models.Q(owner=user) | models.Q(listed=True),
                archived=False,
            )
            .exclude(id__in=campaign_packs_qs.values_list("id", flat=True))
            .select_related("owner")
            .order_by("name")
        )

        search_query = request.GET.get("q", "").strip()
        if search_query:
            available_packs = available_packs.filter(name__icontains=search_query)

    return render(
        request,
        "core/campaign/campaign_packs.html",
        {
            "campaign": campaign,
            "campaign_packs": packs_with_lists,
            "available_packs": available_packs,
            "is_owner": is_owner,
            "user_campaign_lists": user_campaign_lists,
            "search_query": search_query,
        },
    )


@login_required
@group_membership_required(["Custom Content"])
def campaign_pack_add(request, id, pack_id):
    """Add a pack to the campaign's allowed packs."""
    if request.method != "POST":
        return HttpResponseRedirect(reverse("core:campaign-packs", args=(id,)))

    campaign = get_object_or_404(Campaign, id=id, owner=request.user)
    pack = get_object_or_404(CustomContentPack, id=pack_id, archived=False)

    if campaign.archived:
        messages.error(request, "Cannot modify packs for an archived Campaign.")
        return HttpResponseRedirect(reverse("core:campaign-packs", args=(campaign.id,)))

    if not pack.listed and pack.owner != request.user:
        messages.error(request, "You don't have access to this pack.")
        return HttpResponseRedirect(reverse("core:campaign-packs", args=(campaign.id,)))

    campaign.packs.add(pack)
    messages.success(request, f"Added {pack.name} to Campaign.")

    return HttpResponseRedirect(reverse("core:campaign-packs", args=(campaign.id,)))


@login_required
@group_membership_required(["Custom Content"])
def campaign_pack_remove(request, id, pack_id):
    """Remove a pack from the campaign's allowed packs."""
    campaign = get_object_or_404(Campaign, id=id, owner=request.user)
    pack = get_object_or_404(CustomContentPack, id=pack_id)

    if campaign.archived:
        messages.error(request, "Cannot modify packs for an archived Campaign.")
        return HttpResponseRedirect(reverse("core:campaign-packs", args=(campaign.id,)))

    if request.method == "POST":
        campaign.packs.remove(pack)
        messages.success(request, f"Removed {pack.name} from Campaign.")
        return HttpResponseRedirect(reverse("core:campaign-packs", args=(campaign.id,)))

    return render(
        request,
        "core/campaign/campaign_pack_remove.html",
        {
            "campaign": campaign,
            "pack": pack,
        },
    )
