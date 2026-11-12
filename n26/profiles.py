"""N26's reader for the platform-owned public account page.

Non-archived gang names, types and wealth are public. Campaigns require a
signed-in reader, matching their detail pages.
"""

from django.db.models import Count, OuterRef, Subquery
from django.db.models.functions import Coalesce
from django.urls import reverse

from gyrinx.accounts.public_profiles import (
    ProfileAction,
    ProfileEntry,
    ProfileGangSheet,
    ProfileSection,
    ProfileSource,
    register_profile_source,
)
from gyrinx.accounts.public_profiles import (
    profile_person as profile_person,
)
from gyrinx.accounts.public_profiles import (
    profile_redirect as profile_redirect,
)
from n26.core.models import Campaign, CampaignMembership, Gang, Miniature
from n26.core.status import Status

__all__ = ["profile_person", "profile_redirect"]


def sections(person, request):
    viewer = request.user
    campaigns_by_gang = {}
    if viewer.is_authenticated:
        campaigns_by_gang = {
            membership.gang_id: membership.campaign
            for membership in CampaignMembership.objects.filter(
                gang__owner=person,
                left__isnull=True,
                campaign__in=Campaign.objects.involving(viewer).filter(archived=False),
            )
            .select_related("campaign")
            .order_by("pk")
        }
    artwork = {}

    def gang_icon(gang):
        if gang.gang_type_id not in artwork:
            artwork[gang.gang_type_id] = gang.gang_type.artwork
        return artwork[gang.gang_type_id]

    living = (
        Miniature.objects.filter(
            membership__gang=OuterRef("pk"), membership__archived=False
        )
        .exclude(status=Status.DEAD)
        .order_by()
        .values("membership__gang")
        .annotate(count=Count("pk"))
        .values("count")
    )
    entries = tuple(
        ProfileEntry(
            gang.name,
            reverse("n26-gang", args=[gang.pk]),
            detail=gang.gang_type.name,
            is_gang=True,
            colour=gang.colour,
            icon=gang_icon(gang),
            modified=gang.modified,
            sheet=ProfileGangSheet(
                gang.model_count,
                gang.rating,
                gang.credits,
                gang.stash_rating,
                gang.wealth,
                gang.credits_unlimited,
            ),
            state=campaigns_by_gang[gang.pk].name
            if gang.pk in campaigns_by_gang
            else "",
            detail_href=reverse("n26-campaign", args=[campaigns_by_gang[gang.pk].pk])
            if gang.pk in campaigns_by_gang
            else "",
        )
        for gang in Gang.objects.filter(owner=person, archived=False)
        .select_related("gang_type", "stash")
        .annotate(model_count=Coalesce(Subquery(living), 0))
        .order_by("name", "pk")
    )
    own = viewer.is_authenticated and viewer.pk == person.pk
    result = [
        ProfileSection(
            "Gangs",
            entries,
            "No gangs to show.",
            reverse("n26-create-gang") if own else "",
        ),
    ]
    if viewer.is_authenticated:
        campaigns = tuple(
            ProfileEntry(
                campaign.name,
                reverse("n26-campaign", args=[campaign.pk]),
                detail=campaign.campaign_type.name,
                state=campaign.get_status_display(),
            )
            for campaign in Campaign.objects.involving(person)
            .filter(archived=False)
            .select_related("campaign_type")
            .order_by("name", "pk")
        )
        result.append(
            ProfileSection(
                "Campaigns",
                campaigns,
                "No campaigns to show.",
                reverse("n26-create-campaign") if own else "",
            )
        )
    return tuple(result)


def actions(person, request) -> tuple[ProfileAction, ...]:
    from n26.core.views.profiles import _owned_campaigns

    viewer = request.user
    if (
        viewer.is_authenticated
        and viewer.pk != person.pk
        and _owned_campaigns(viewer, person).exists()
    ):
        return (
            ProfileAction(
                "Invite to N26 campaign",
                reverse("n26-invite-user", args=[person.username]),
            ),
        )
    return ()


register_profile_source(ProfileSource("n26", sections, actions))
