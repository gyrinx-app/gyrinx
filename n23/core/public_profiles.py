"""N23 records visible on a shared public account page."""

from django.db.models import Count, Exists, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce
from django.urls import reverse

from gyrinx.accounts.public_profiles import (
    ProfileEntry,
    ProfileGangSheet,
    ProfileSection,
    ProfileSource,
    register_profile_source,
)
from n23.core.models import ListFighter
from n23.core.models.campaign import Campaign
from n23.core.models.list import List
from n23.core.models.pack import CustomContentPack


def sections(person, request):
    viewer = request.user
    own = viewer.is_authenticated and viewer.pk == person.pk
    living = (
        ListFighter.objects.filter(
            list=OuterRef("pk"), archived=False, content_fighter__is_stash=False
        )
        .exclude(injury_state="dead")
        .order_by()
        .values("list")
        .annotate(count=Count("pk"))
        .values("count")
    )
    gangs = (
        List.objects.filter(
            owner=person,
            archived=False,
            status__in=(List.LIST_BUILDING, List.CAMPAIGN_MODE),
        )
        .select_related("content_house", "campaign")
        .annotate(
            model_count=Coalesce(Subquery(living), 0),
        )
        .order_by("name", "pk")
    )
    if not own:
        gangs = gangs.filter(public=True)
        if viewer.is_authenticated:
            gangs = gangs.annotate(
                viewer_has_campaign_access=Exists(
                    Campaign.objects.filter(
                        Q(lists__owner=viewer) | Q(admins=viewer),
                        pk=OuterRef("campaign_id"),
                    )
                )
            )
    lists, campaign_gangs = [], []
    from n23.core.templatetags.color_tags import house_icon

    icons = {}
    for gang in gangs:
        campaign = gang.campaign
        show_campaign = (
            campaign
            and not campaign.archived
            and (
                own
                or campaign.public
                or getattr(gang, "viewer_has_campaign_access", False)
                or viewer.is_authenticated
                and campaign.owner_id == viewer.pk
            )
        )
        if gang.content_house_id not in icons:
            icons[gang.content_house_id] = str(house_icon(gang.content_house))
        entry = ProfileEntry(
            name=gang.name,
            is_gang=True,
            colour=gang.theme_color,
            icon=icons[gang.content_house_id],
            modified=gang.modified,
            sheet=ProfileGangSheet(
                gang.model_count,
                gang.rating_current,
                gang.credits_current,
                gang.stash_current,
                gang.wealth_current,
            ),
            href=reverse("core:list", args=[gang.pk]),
            detail=gang.content_house_name
            + (" · Unlisted" if own and not gang.public else ""),
            state=campaign.name if show_campaign else "",
            detail_href=reverse("core:campaign", args=[campaign.pk])
            if show_campaign
            else "",
        )
        if gang.status == List.CAMPAIGN_MODE:
            campaign_gangs.append(entry)
        elif gang.status == List.LIST_BUILDING:
            lists.append(entry)
    campaigns = Campaign.objects.filter(owner=person, archived=False)
    packs = CustomContentPack.objects.filter(owner=person, archived=False)
    if not own:
        campaigns = campaigns.filter(public=True)
        packs = packs.filter(listed=True)
    campaigns = campaigns.annotate(
        star_count=Count("starred_by", distinct=True)
    ).order_by("name", "pk")
    campaign_entries = tuple(
        ProfileEntry(
            campaign.name,
            reverse("core:campaign", args=[campaign.pk]),
            stars=campaign.star_count,
            state=campaign.get_status_display(),
        )
        for campaign in campaigns
    )
    pack_entries = tuple(
        ProfileEntry(
            pack.name,
            reverse("core:pack", args=[pack.pk]),
            state="Listed" if pack.listed else "Unlisted",
        )
        for pack in packs.order_by("name", "pk")
    )
    return (
        ProfileSection(
            "Campaign Gangs", tuple(campaign_gangs), "No campaign gangs yet."
        ),
        ProfileSection(
            "Campaigns",
            campaign_entries,
            "No campaigns yet.",
            reverse("core:campaigns-new") if own else "",
        ),
        ProfileSection(
            "Lists",
            tuple(lists),
            "No lists yet.",
            reverse("core:lists-new") if own else "",
        ),
        ProfileSection(
            "Content Packs",
            pack_entries,
            "No content packs yet.",
            reverse("core:packs-new") if own else "",
        ),
    )


register_profile_source(ProfileSource("n23", sections))
