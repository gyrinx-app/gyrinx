"""N23 records visible on a shared public account page."""

from django.db.models import Count, Exists, OuterRef
from django.urls import reverse

from gyrinx.accounts.public_profiles import (
    ProfileEntry,
    ProfileSection,
    ProfileSource,
    register_profile_source,
)
from n23.core.models.campaign import Campaign
from n23.core.models.list import List
from n23.core.models.pack import CustomContentPack


def sections(person, request):
    viewer = request.user
    own = viewer.is_authenticated and viewer.pk == person.pk
    gangs = (
        List.objects.filter(
            owner=person,
            archived=False,
            status__in=(List.LIST_BUILDING, List.CAMPAIGN_MODE),
        )
        .select_related("content_house", "campaign")
        .annotate(star_count=Count("starred_by", distinct=True))
        .order_by("name", "pk")
    )
    if not own:
        gangs = gangs.filter(public=True)
        if viewer.is_authenticated:
            gangs = gangs.annotate(
                viewer_participates=Exists(
                    Campaign.objects.filter(
                        pk=OuterRef("campaign_id"), lists__owner=viewer
                    )
                )
            )
    public, unlisted, campaign_gangs = [], [], []
    for gang in gangs:
        campaign = gang.campaign
        show_campaign = (
            campaign
            and not campaign.archived
            and (
                own
                or campaign.public
                or getattr(gang, "viewer_participates", False)
                or viewer.is_authenticated
                and campaign.owner_id == viewer.pk
            )
        )
        entry = ProfileEntry(
            name=gang.name,
            href=reverse("core:list", args=[gang.pk]),
            detail=gang.content_house_name,
            stars=gang.star_count,
            amount=f"{gang.wealth_current:,}¢"
            if gang.status == List.LIST_BUILDING
            else "",
            state=campaign.name if show_campaign else "",
            detail_href=reverse("core:campaign", args=[campaign.pk])
            if show_campaign
            else "",
        )
        if gang.status == List.CAMPAIGN_MODE:
            campaign_gangs.append(entry)
        elif gang.status == List.LIST_BUILDING:
            (public if gang.public else unlisted).append(entry)
    campaigns = Campaign.objects.filter(owner=person, archived=False)
    packs = CustomContentPack.objects.filter(owner=person, archived=False)
    if not own:
        campaigns = campaigns.filter(public=True)
        packs = packs.filter(listed=True)
    campaigns = campaigns.annotate(
        star_count=Count("starred_by", distinct=True)
    ).order_by("name", "pk")
    result = []
    if public or own:
        result.append(
            ProfileSection(
                "Public gangs",
                tuple(public),
                "No public gangs yet.",
                reverse("core:lists-new") if own else "",
            )
        )
    if unlisted:
        result.append(
            ProfileSection("Unlisted", tuple(unlisted), "No unlisted gangs yet.")
        )
    if campaign_gangs or own:
        result.append(
            ProfileSection(
                "Campaign gangs", tuple(campaign_gangs), "No campaign gangs yet."
            )
        )
    campaign_entries = tuple(
        ProfileEntry(
            campaign.name,
            reverse("core:campaign", args=[campaign.pk]),
            stars=campaign.star_count,
            state=campaign.get_status_display(),
        )
        for campaign in campaigns
    )
    if campaign_entries or own:
        result.append(
            ProfileSection(
                "Campaigns",
                campaign_entries,
                "No campaigns yet.",
                reverse("core:campaigns-new") if own else "",
            )
        )
    pack_entries = tuple(
        ProfileEntry(
            pack.name,
            reverse("core:pack", args=[pack.pk]),
            state="Listed" if pack.listed else "Unlisted",
        )
        for pack in packs.order_by("name", "pk")
    )
    if pack_entries or own:
        result.append(
            ProfileSection(
                "Content packs",
                pack_entries,
                "No content packs yet.",
                reverse("core:packs-new") if own else "",
            )
        )
    return tuple(result)


register_profile_source(ProfileSource("n23", sections))
