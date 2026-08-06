"""Audiences this edition adds to the platform's notification broadcast page.

"Users with a list" and "Participants of a campaign" are both statements about
edition data, so they are declared here and registered into
``gyrinx.site.registry`` rather than hard-coded into the platform's form.

Imported by ``n23.core.admin`` — Django imports that during
``admin.autodiscover()``, so both audiences are in the dropdown before any
request is served. Drop the import from ``n23/core/admin/__init__.py`` and the
options silently disappear from the page.
"""

from django import forms
from django.contrib.auth import get_user_model

from gyrinx.site.registry import BroadcastAudience, register_broadcast_audience
from n23.core.models.campaign import Campaign

__all__ = []

User = get_user_model()


def _users_with_a_list(cleaned_data):
    return User.objects.filter(list__isnull=False).distinct()


def _campaign_participants(cleaned_data):
    """List owners in the campaign, plus the arbitrator."""
    campaign = cleaned_data["campaign"]
    ids = set(campaign.lists.values_list("owner_id", flat=True))
    if campaign.owner_id:
        ids.add(campaign.owner_id)
    ids.discard(None)
    return User.objects.filter(pk__in=ids)


def _campaign_field():
    return forms.ModelChoiceField(
        queryset=Campaign.objects.all(),
        required=False,
        help_text="Required when audience is 'Participants of a campaign'.",
    )


register_broadcast_audience(
    BroadcastAudience(
        key="with_list",
        label="Users with a list",
        recipients=_users_with_a_list,
    )
)
register_broadcast_audience(
    BroadcastAudience(
        key="campaign",
        label="Participants of a campaign",
        recipients=_campaign_participants,
        field_name="campaign",
        field=_campaign_field,
        field_required_error="Choose a campaign for this audience.",
    )
)
