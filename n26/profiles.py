"""N26's reader for the platform-owned public account page.

Non-archived gang names, types and wealth are public. Campaigns require a
signed-in reader with the campaigns feature, matching their detail pages.
"""

from django.urls import reverse

from gyrinx.accounts.public_profiles import (
    ProfileAction,
    ProfileEntry,
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
from n26.core.models import Campaign, Gang
from n26.flags import CAMPAIGNS, enabled


def sections(person, viewer):
    entries = tuple(
        ProfileEntry(
            gang.name,
            reverse("n26-gang", args=[gang.pk]),
            detail=gang.gang_type.name,
            amount=f"{gang.wealth:,}¢",
        )
        for gang in Gang.objects.filter(owner=person, archived=False)
        .select_related("gang_type", "stash")
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
    if viewer.is_authenticated and enabled(CAMPAIGNS, viewer):
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


def actions(person, viewer):
    from n26.core.views.profiles import _owned_campaigns

    if (
        viewer.is_authenticated
        and viewer.pk != person.pk
        and enabled(CAMPAIGNS, viewer)
        and _owned_campaigns(viewer, person).exists()
    ):
        return (
            ProfileAction(
                "Invite to campaign", reverse("n26-invite-user", args=[person.username])
            ),
        )
    return ()


register_profile_source(ProfileSource("n26", sections, actions))
